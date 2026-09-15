package unicum.markers
{
   import flash.display.Loader;
   import flash.events.ErrorEvent;
   import flash.events.Event;
   import flash.events.IOErrorEvent;
   import flash.events.SecurityErrorEvent;
   import flash.events.TimerEvent;
   import flash.events.UncaughtErrorEvent;
   import flash.external.ExternalInterface;
   import flash.net.URLRequest;
   import flash.system.ApplicationDomain;
   import flash.system.LoaderContext;
   import flash.utils.Dictionary;
   import flash.utils.Timer;

   // Added to the client's own battleVehicleMarkersApp.swf by
   // tools/build_as3.py, with UnicumMarkersApp, its new root.
   //
   // The engine's markers canvas only makes markers from classes defined in
   // that movie. Ours extend the client's marker symbol classes, which only
   // exist once the app has loaded battleVehicleMarkers.swf; declared any
   // earlier they fail to verify. So they come in a SWF of their own, loaded
   // into the movie's domain right after the client's libraries:
   //
   //   unicum.markers.classes.swf  UnicumVehicleMarker, UnicumComp7VehicleMarker
   //                               and NameMarkerAddon; the app registers with
   //                               Python only once they are in, or have failed
   //                               to come within CLASSES_WAIT_MS
   //   unicum.markers.swf          NameMarkerView, in a child domain, loaded
   //                               again when it changes: hot reload
   //
   // Python hears each outcome through READY_CALLBACK, and writes it to
   // game.log.
   public class MarkersBoot
   {
      public static const CLASSES:String = "unicum.markers.classes.swf";

      public static const LIBRARY:String = "unicum.markers.swf";

      public static const VIEW_CLASS:String = "unicum.NameMarkerView";

      public static const READY_CALLBACK:String = "unicum.markers.ready";

      // Longest the client's markers wait for ours: past it, the app
      // registers and the client makes its own.
      private static const CLASSES_WAIT_MS:int = 3000;

      public static var view:Class = null;

      // NameMarkerAddon -> true; typed loosely, as that class comes later.
      public static var addons:Dictionary = new Dictionary(true);

      private static var _classes:Loader = null;

      private static var _loader:Loader = null;

      private static var _loading:Loader = null;

      public function MarkersBoot()
      {
         super();
      }

      // Load our marker classes into the movie's domain, then call done once,
      // whether they loaded, failed, or took too long: the client's markers
      // need it either way.
      public static function loadClasses(done:Function) : void
      {
         var called:Boolean = false;
         var timer:Timer = new Timer(CLASSES_WAIT_MS, 1);
         var loader:Loader = new Loader();
         var finish:Function = function(outcome:String) : void
         {
            if(called)
            {
               return;
            }
            called = true;
            timer.stop();
            report(outcome);
            done();
         };
         var onInit:Function = function(event:Event) : void
         {
            finish("classes");
         };
         var onFailure:Function = function(event:Event) : void
         {
            finish("cannot load " + CLASSES + ": " + (event is ErrorEvent ? ErrorEvent(event).text : event.type));
         };
         var onUncaught:Function = function(event:UncaughtErrorEvent) : void
         {
            event.preventDefault();
            finish("error in " + CLASSES + ": " + event.error);
         };
         timer.addEventListener(TimerEvent.TIMER_COMPLETE, function(event:TimerEvent) : void
         {
            finish("no " + CLASSES + " after " + CLASSES_WAIT_MS + " ms");
         });
         loader.contentLoaderInfo.addEventListener(Event.INIT, onInit);
         loader.contentLoaderInfo.addEventListener(IOErrorEvent.IO_ERROR, onFailure);
         loader.contentLoaderInfo.addEventListener(SecurityErrorEvent.SECURITY_ERROR, onFailure);
         loader.uncaughtErrorEvents.addEventListener(UncaughtErrorEvent.UNCAUGHT_ERROR, onUncaught);
         _classes = loader;
         timer.start();
         try
         {
            loader.load(new URLRequest(CLASSES), new LoaderContext(false, ApplicationDomain.currentDomain));
         }
         catch(e:Error)
         {
            finish("cannot load " + CLASSES + ": " + e.message);
         }
      }

      public static function ensureLoaded() : void
      {
         if(view == null && _loading == null)
         {
            load();
         }
      }

      public static function load() : void
      {
         if(_loading != null)
         {
            forget(_loading);
         }
         var loader:Loader = new Loader();
         loader.contentLoaderInfo.addEventListener(Event.INIT, onViewInit);
         loader.contentLoaderInfo.addEventListener(IOErrorEvent.IO_ERROR, onViewError);
         loader.contentLoaderInfo.addEventListener(SecurityErrorEvent.SECURITY_ERROR, onViewError);
         _loading = loader;
         try
         {
            loader.load(new URLRequest(LIBRARY), new LoaderContext(false, new ApplicationDomain(ApplicationDomain.currentDomain)));
         }
         catch(e:Error)
         {
            forget(loader);
            _loading = null;
            report("cannot load " + LIBRARY + ": " + e.message);
         }
      }

      private static function forget(loader:Loader) : void
      {
         loader.contentLoaderInfo.removeEventListener(Event.INIT, onViewInit);
         loader.contentLoaderInfo.removeEventListener(IOErrorEvent.IO_ERROR, onViewError);
         loader.contentLoaderInfo.removeEventListener(SecurityErrorEvent.SECURITY_ERROR, onViewError);
         try
         {
            loader.unloadAndStop(false);
         }
         catch(e:Error)
         {
         }
      }

      private static function onViewInit(event:Event) : void
      {
         var loader:Loader = event.currentTarget.loader as Loader;
         if(loader != _loading)
         {
            return;
         }
         var domain:ApplicationDomain = loader.contentLoaderInfo.applicationDomain;
         view = domain.hasDefinition(VIEW_CLASS) ? domain.getDefinition(VIEW_CLASS) as Class : null;
         if(_loader != null)
         {
            forget(_loader);
         }
         _loader = loader;
         _loading = null;
         for(var addon:Object in addons)
         {
            addon.rebuild();
         }
         report(view != null ? "view" : "no " + VIEW_CLASS);
      }

      private static function onViewError(event:ErrorEvent) : void
      {
         var loader:Loader = event.currentTarget.loader as Loader;
         if(loader == _loading)
         {
            forget(loader);
            _loading = null;
         }
         report("cannot load " + LIBRARY + ": " + event.text);
      }

      public static function report(message:String) : void
      {
         try
         {
            if(ExternalInterface.available)
            {
               ExternalInterface.call(READY_CALLBACK, message);
            }
         }
         catch(e:Error)
         {
         }
      }
   }
}
