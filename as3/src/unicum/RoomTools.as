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
   //   ratingHtmlByPlayer  "dbID<tab>badge markup" a line, for the column
   //                   beside the room's own Rating. Apart from the numbers
   //                   above because it cannot share their encoding: a badge
   //                   is `<IMG SRC="img://...png" .../>` and carries both a
   //                   comma and a colon. Empty when the column is not drawn.
   //   flagsHtmlByPlayer   "dbID<tab>flag markup" a line, for the flags
   //                   column; same encoding, same reason
   //   ratingHeader    what that column is called, the rating's own name
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

      public var ratingHeader:String = "";

      private var _ratingByPlayer:String = "";

      private var _ratingHtmlByPlayer:String = "";

      private var _flagsHtmlByPlayer:String = "";

      private var _badges:Object = {};

      private var _flags:Object = {};

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

      public function get ratingHtmlByPlayer() : String
      {
         return this._ratingHtmlByPlayer;
      }

      public function set ratingHtmlByPlayer(value:String) : void
      {
         if(value == this._ratingHtmlByPlayer)
         {
            return;
         }
         this._ratingHtmlByPlayer = value;
         this._badges = {};
         for each(var line:String in (value || "").split("\n"))
         {
            var cut:int = line.indexOf("\t");
            if(cut > 0)
            {
               this._badges[line.substring(0, cut)] = line.substring(cut + 1);
            }
         }
      }

      public function get flagsHtmlByPlayer() : String
      {
         return this._flagsHtmlByPlayer;
      }

      // The same encoding as the badges above, for the same reason: a flag
      // is an <IMG> too. Drawn as a column rather than left on the name,
      // where it sat wherever the name happened to end.
      public function set flagsHtmlByPlayer(value:String) : void
      {
         if(value == this._flagsHtmlByPlayer)
         {
            return;
         }
         this._flagsHtmlByPlayer = value;
         this._flags = {};
         for each(var line:String in (value || "").split("\n"))
         {
            var cut:int = line.indexOf("\t");
            if(cut > 0)
            {
               this._flags[line.substring(0, cut)] = line.substring(cut + 1);
            }
         }
      }

      // What every members list found, for Python to log. "none" when no
      // list has been found at all, which is its own answer.
      public function report() : String
      {
         if(this._sections.length == 0)
         {
            return "no members list found";
         }
         var out:Array = [];
         for each(var section:MembersSection in this._sections)
         {
            out.push(section.report());
         }
         return out.join(" | ");
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
            section.update(this.roomEnabled, this.sortMode, this.sortLabels, this._scores,
                           this.averageHtml, this._badges, this.ratingHeader, this._flags);
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
