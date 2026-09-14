package unicum
{
   import flash.events.Event;
   import net.wg.gui.components.windows.Window;
   import net.wg.gui.lobby.window.ProfileWindow;
   import net.wg.infrastructure.base.AbstractView;

   // Lets the profile window's title render HTML, so the Python half of the
   // mod can put a flag image in it.
   //
   // Window has a titleUseHtml switch that the vehicle info, buy and chat
   // windows turn on and the profile window never does, and Python cannot
   // reach the Window from the view to flip it. This view does nothing else:
   // it has no DAAPI calls and no display, and deciding what the title says
   // stays in Python, where it hot reloads. Loaded once, into the lobby's
   // service layer, by src/unicum/titles.py.
   //
   // Titles are plain player names and clan tags, which have no characters
   // HTML would read differently, so switching the mode changes nothing about
   // a title the mod has not marked.
   public class TitleHtml extends AbstractView
   {
      // The Window is added before its content is attached, so a window is
      // checked again on the following frames until it has one.
      private static const MAX_FRAMES:int = 120;

      private var _pending:Vector.<Window> = new Vector.<Window>();

      private var _frames:int = 0;

      public function TitleHtml()
      {
         super();
      }

      override protected function configUI() : void
      {
         super.configUI();
         mouseEnabled = false;
         mouseChildren = false;
         // Capture phase on the stage sees every window, whichever layer
         // container it is added to.
         App.stage.addEventListener(Event.ADDED, this.onAdded, true, 0, true);
      }

      override protected function onDispose() : void
      {
         App.stage.removeEventListener(Event.ADDED, this.onAdded, true);
         removeEventListener(Event.ENTER_FRAME, this.onFrame);
         this._pending.length = 0;
         super.onDispose();
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
         addEventListener(Event.ENTER_FRAME, this.onFrame);
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
            removeEventListener(Event.ENTER_FRAME, this.onFrame);
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
