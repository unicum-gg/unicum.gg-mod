package unicum.markers
{
   import flash.display.DisplayObject;
   import flash.display.Sprite;
   import flash.events.Event;
   import flash.text.TextField;

   // What our marker classes add to the client's vehicle marker: the latest
   // NameMarkerView from unicum.markers.swf, right of the marker's own player
   // name, and every call Python makes for it. The view is rebuilt when that
   // SWF is loaded again (see MarkersBoot.as), and the calls replayed.
   //
   // It reads where the name is drawn from the marker itself, every frame, so
   // it follows whatever the marker shows: ALT, settings, a shortened name.
   public class NameMarkerAddon
   {
      private var _marker:Sprite;

      private var _view:DisplayObject = null;

      private var _calls:Object = {};

      private var _disposed:Boolean = false;

      public function NameMarkerAddon(marker:Sprite)
      {
         super();
         this._marker = marker;
         MarkersBoot.addons[this] = true;
         MarkersBoot.ensureLoaded();
         this.rebuild();
      }

      public function dispose() : void
      {
         if(this._disposed)
         {
            return;
         }
         this._disposed = true;
         delete MarkersBoot.addons[this];
         this.removeView();
         this._calls = {};
         this._marker = null;
      }

      public function call(name:String, args:Array) : void
      {
         if(this._disposed)
         {
            return;
         }
         this._calls[name] = args;
         this.forward(name, args);
      }

      public function rebuild() : void
      {
         this.removeView();
         if(this._disposed || MarkersBoot.view == null)
         {
            return;
         }
         this._view = new MarkersBoot.view() as DisplayObject;
         if(this._view == null)
         {
            return;
         }
         this._marker.addChild(this._view);
         this._view.addEventListener(Event.ENTER_FRAME, this.onFrame);
         this.forward("setAnchor", [this.nameField()]);
         for(var name:String in this._calls)
         {
            this.forward(name, this._calls[name]);
         }
      }

      private function nameField() : TextField
      {
         try
         {
            return Object(this._marker)["playerNameField"] as TextField;
         }
         catch(e:Error)
         {
         }
         return null;
      }

      private function onFrame(event:Event) : void
      {
         this.forward("layout", []);
      }

      private function removeView() : void
      {
         if(this._view != null)
         {
            this._view.removeEventListener(Event.ENTER_FRAME, this.onFrame);
            if(this._view.parent != null)
            {
               this._view.parent.removeChild(this._view);
            }
            this._view = null;
         }
      }

      private function forward(name:String, args:Array) : void
      {
         if(this._view == null)
         {
            return;
         }
         try
         {
            var method:Function = Object(this._view)[name] as Function;
            if(method != null)
            {
               method.apply(this._view, args);
            }
         }
         catch(e:Error)
         {
         }
      }
   }
}
