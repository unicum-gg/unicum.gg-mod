package unicum
{
   import flash.display.DisplayObject;
   import flash.display.Loader;
   import flash.events.Event;
   import flash.events.IOErrorEvent;
   import flash.events.SecurityErrorEvent;
   import flash.net.URLRequest;
   import flash.system.ApplicationDomain;
   import flash.system.LoaderContext;
   import flash.text.TextField;
   import flash.text.TextFieldAutoSize;
   import net.wg.gui.lobby.settings.SettingsBaseView;
   import net.wg.gui.lobby.settings.vo.base.SettingsDataVo;

   // The unicum.gg tab of the game's own settings window, lobby and battle
   // alike (SettingsTabs.as puts it there). The window creates it by its class
   // name, as it does its own tabs, and treats it as one: a SettingsBaseView,
   // with no data of the window's, since the mod's settings are its own.
   //
   // A shell that does not change: what the tab shows is drawn by
   // unicum.settings.SettingsTabView, in unicum.settings.swf, loaded each time
   // the tab is made into a domain of its own. An app keeps the first
   // definition it loads of a class, so code loaded into its own domain is
   // the only kind a new build replaces without the app being built again:
   // the settings window opened again shows the tab's latest code.
   //
   // What the view is given: the page (src/unicum/settings_window.py,
   // native_page), `send` for a line to Python, and `memory`, kept while
   // windows open and close and the view is loaded again.
   public class SettingsTab extends SettingsBaseView
   {
      // The class name the window's view stack creates this tab by.
      public static const LINKAGE:String = "unicum.SettingsTab";

      private static const LIBRARY:String = "unicum.settings.swf";

      private static const VIEW_CLASS:String = "unicum.settings.SettingsTabView";

      private static var _page:String = "";

      private static var _live:Array = [];

      // Lines for Python: "var\tkind\tvalue", taken by LobbyView or TeamNamesHtml.
      public static var out:Array = [];

      // Frames left for SettingsTabs to keep this tab showing: applying makes
      // the window put its own tab back up (SettingsWindow.initializeCommonData
      // shows the tab its _currentTab names), and this one was what the player
      // was looking at.
      public static var holding:int = 0;

      private static var _memory:Object = {};

      private var _loader:Loader;

      private var _view:Object;

      public function SettingsTab()
      {
         super();
      }

      public static function set page(value:String) : void
      {
         if(value == _page)
         {
            return;
         }
         _page = value;
         for each(var tab:SettingsTab in _live)
         {
            tab.notify();
         }
      }

      public function get page() : String
      {
         return _page;
      }

      public function get memory() : Object
      {
         return _memory;
      }

      public function send(line:String) : void
      {
         out.push(line);
      }

      // Called when the view commits: the window is about to rebuild itself.
      public function hold() : void
      {
         holding = 10;
      }

      override protected function configUI() : void
      {
         super.configUI();
         _live.push(this);
         this._loader = new Loader();
         this._loader.contentLoaderInfo.addEventListener(Event.INIT, this.onLoaded);
         this._loader.contentLoaderInfo.addEventListener(IOErrorEvent.IO_ERROR, this.onFailed);
         this._loader.contentLoaderInfo.addEventListener(SecurityErrorEvent.SECURITY_ERROR, this.onFailed);
         try
         {
            this._loader.load(new URLRequest(LIBRARY), new LoaderContext(false, new ApplicationDomain(ApplicationDomain.currentDomain)));
         }
         catch(e:Error)
         {
            this.say("unicum.gg: the settings could not load (" + e.message + ")");
         }
      }

      private function onLoaded(event:Event) : void
      {
         try
         {
            var view:Class = this._loader.contentLoaderInfo.applicationDomain.getDefinition(VIEW_CLASS) as Class;
            this._view = new view();
            addChild(DisplayObject(this._view));
            this._view.start(this);
         }
         catch(e:Error)
         {
            this.say("unicum.gg: the settings could not start (" + e.message + ")");
         }
      }

      private function onFailed(event:Event) : void
      {
         this.say("unicum.gg: the settings could not load (" + event.type + ")");
      }

      private function say(text:String) : void
      {
         var field:TextField = new TextField();
         field.autoSize = TextFieldAutoSize.LEFT;
         field.selectable = false;
         field.htmlText = "<font face='$FieldFont' size='14' color='#C4C1B5'>" + text + "</font>";
         field.x = 20;
         field.y = 20;
         addChild(field);
      }

      private function notify() : void
      {
         if(this._view != null)
         {
            try
            {
               this._view.update();
            }
            catch(e:Error)
            {
            }
         }
      }

      override protected function onDispose() : void
      {
         var index:int = _live.indexOf(this);
         if(index >= 0)
         {
            _live.splice(index, 1);
         }
         if(this._view != null)
         {
            try
            {
               this._view.stop();
            }
            catch(e:Error)
            {
            }
            this._view = null;
         }
         if(this._loader != null)
         {
            this._loader.contentLoaderInfo.removeEventListener(Event.INIT, this.onLoaded);
            this._loader.contentLoaderInfo.removeEventListener(IOErrorEvent.IO_ERROR, this.onFailed);
            this._loader.contentLoaderInfo.removeEventListener(SecurityErrorEvent.SECURITY_ERROR, this.onFailed);
            try
            {
               this._loader.unloadAndStop(false);
            }
            catch(e:Error)
            {
            }
            this._loader = null;
         }
         super.onDispose();
      }

      // The window has no data for this tab: nothing of its to show.
      override protected function setData(param1:SettingsDataVo) : void
      {
      }
   }
}
