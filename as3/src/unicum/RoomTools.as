package unicum
{
   import flash.display.DisplayObjectContainer;
   import flash.display.Sprite;
   import flash.events.Event;
   import flash.utils.Dictionary;

   // The skirmish room's members list: sort dropdown, sorted rows and average
   // rating, drawn by MembersSection. Part of LobbyView, which forwards this
   // state to Python through the GFx proxy:
   //
   //   sortMode        the chosen order; Python saves it, and writes the saved
   //                   one back while it is empty (src/unicum/room_sort.py)
   //   sortLabels      the dropdown's entries, newline separated, the client's
   //                   own translations for the orders it has (room_sort.py)
   //   ratingByPlayer  "dbID:rating,..." for the score order (src/unicum/lobby.py)
   //   averageHtml     the average's badge markup, empty when no room is open
   //   roomEnabled     false when the settings switch the skirmish room off
   //
   // A members list is found by its fields, not its class: a window arrives
   // as one display object with everything already inside, so each added
   // object is searched down to MAX_DEPTH, once.
   public class RoomTools
   {
      private static const MAX_DEPTH:int = 16;

      public var sortMode:String = "";

      public var sortLabels:String = "";

      public var averageHtml:String = "";

      public var roomEnabled:Boolean = true;

      private var _ratingByPlayer:String = "";

      private var _scores:Object = {};

      private var _host:Sprite;

      private var _sections:Vector.<MembersSection> = new Vector.<MembersSection>();

      private var _searched:Dictionary = new Dictionary(true);

      public function RoomTools(host:Sprite)
      {
         this._host = host;
         App.stage.addEventListener(Event.ADDED, this.onAdded, true, 0, true);
         host.addEventListener(Event.ENTER_FRAME, this.onFrame);
         App.stage.addEventListener(Event.RENDER, this.onRender);
         // A room already open when this view loads, after a hot reload.
         this.search(App.stage, 0);
      }

      public function get ratingByPlayer() : String
      {
         return this._ratingByPlayer;
      }

      public function set ratingByPlayer(value:String) : void
      {
         if(value == this._ratingByPlayer)
         {
            return;
         }
         this._ratingByPlayer = value;
         this._scores = {};
         for each(var pair:String in (value || "").split(","))
         {
            var parts:Array = pair.split(":");
            if(parts.length == 2)
            {
               this._scores[parts[0]] = Number(parts[1]);
            }
         }
      }

      public function dispose() : void
      {
         App.stage.removeEventListener(Event.ADDED, this.onAdded, true);
         this._host.removeEventListener(Event.ENTER_FRAME, this.onFrame);
         App.stage.removeEventListener(Event.RENDER, this.onRender);
         // Put the room back as the client drew it, so a reloaded view
         // starts from there.
         for each(var section:MembersSection in this._sections)
         {
            section.dispose();
         }
         this._sections.length = 0;
         this._searched = new Dictionary(true);
      }

      private function onAdded(event:Event) : void
      {
         this.search(event.target, 0);
      }

      private function search(target:Object, depth:int) : void
      {
         if(target == null || this._searched[target])
         {
            return;
         }
         this._searched[target] = true;
         if(MembersSection.accepts(target))
         {
            this._sections.push(new MembersSection(Sprite(target), this.onPick));
            return;
         }
         var container:DisplayObjectContainer = target as DisplayObjectContainer;
         if(container == null || depth >= MAX_DEPTH)
         {
            return;
         }
         for(var i:int = 0; i < container.numChildren; i++)
         {
            this.search(container.getChildAt(i), depth + 1);
         }
      }

      private function onPick(mode:String) : void
      {
         this.sortMode = mode;
      }

      private function onRender(event:Event) : void
      {
         for each(var section:MembersSection in this._sections)
         {
            if(section.section != null && section.section.stage != null)
            {
               section.reorder();
            }
         }
      }

      private function onFrame(event:Event) : void
      {
         for(var i:int = this._sections.length - 1; i >= 0; i--)
         {
            var section:MembersSection = this._sections[i];
            // Closed with its window: forget it, so the same list shown
            // again is searched again.
            if(section.section.stage == null)
            {
               delete this._searched[section.section];
               section.dispose();
               this._sections.splice(i, 1);
               continue;
            }
            section.update(this.roomEnabled, this.sortMode, this.sortLabels, this._scores, this.averageHtml);
         }
         // The rows are placed again in the render phase, which comes after
         // the client has laid them out for this frame.
         if(this._sections.length > 0)
         {
            App.stage.invalidate();
         }
      }
   }
}
