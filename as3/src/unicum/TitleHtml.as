package unicum
{
   import flash.display.Sprite;
   import flash.events.Event;
   import net.wg.gui.components.windows.Window;
   import net.wg.gui.lobby.window.ProfileWindow;

   // Lets the profile window's title render HTML, so the Python half of the
   // mod can put a flag image in it. Part of LobbyView.
   //
   // Window has a titleUseHtml switch that the vehicle info, buy and chat
   // windows turn on and the profile window never does, and Python cannot
   // reach the Window from the view to flip it. Deciding what the title says
   // stays in Python, where it hot reloads.
   //
   // Titles are plain player names and clan tags, which have no characters
   // HTML would read differently, so switching the mode changes nothing about
   // a title the mod has not marked.
   public class TitleHtml
   {
      // The Window is added before its content is attached, so a window is
      // checked again on the following frames until it has one.
      private static const MAX_FRAMES:int = 120;

      private var _host:Sprite;

      private var _pending:Vector.<Window> = new Vector.<Window>();

      private var _frames:int = 0;

      public function TitleHtml(host:Sprite)
      {
         this._host = host;
         // Capture phase on the stage sees every window, whichever layer
         // container it is added to.
         App.stage.addEventListener(Event.ADDED, this.onAdded, true, 0, true);
      }

      public function dispose() : void
      {
         App.stage.removeEventListener(Event.ADDED, this.onAdded, true);
         this._host.removeEventListener(Event.ENTER_FRAME, this.onFrame);
         this._pending.length = 0;
      }

      private function onAdded(event:Event) : void
      {
         var window:Window = event.target as Window;
         if(window == null || this.settle(window))
         {
            return;
         }
         this._pending.push(window);
         this._frames = 0;
         this._host.addEventListener(Event.ENTER_FRAME, this.onFrame);
      }

      private function onFrame(event:Event) : void
      {
         for(var i:int = this._pending.length - 1; i >= 0; i--)
         {
            if(this.settle(this._pending[i]))
            {
               this._pending.splice(i, 1);
            }
         }
         if(this._pending.length == 0 || ++this._frames > MAX_FRAMES)
         {
            this._pending.length = 0;
            this._host.removeEventListener(Event.ENTER_FRAME, this.onFrame);
         }
      }

      // True once the window's content is known, whatever it turned out to be.
      private function settle(window:Window) : Boolean
      {
         if(window.wrapperContent == null)
         {
            return false;
         }
         if(window.wrapperContent is ProfileWindow)
         {
            window.titleUseHtml = true;
         }
         return true;
      }
   }
}
