package unicum
{
   import flash.display.DisplayObject;
   import flash.display.Sprite;
   import flash.geom.Point;
   import flash.text.TextField;
   import flash.text.TextFieldAutoSize;
   import flash.text.TextLineMetrics;
   import net.wg.gui.components.controls.DropdownMenu;
   import scaleform.clik.data.DataProvider;
   import scaleform.clik.events.ListEvent;

   // What the mod adds to one skirmish room's members list:
   //
   //   - the special battles' sort dropdown, the same DropdownMenu with the
   //     same skins, above the list;
   //   - the order it picks, drawn by moving the rows. Each row keeps its
   //     slot, its data and its buttons, and the client keeps updating and
   //     acting on slots by number, so moving rows on screen never makes a
   //     button act on another player. Reordering the data would;
   //   - the detachment's average rating in a field just right of the title.
   //     Not appended to the title: in a TextField an <IMG> floats to the
   //     left edge, and the badge landed on top of the title.
   //
   // The title shown is the room's teamHeader, beside the section. The
   // section's own lblTeamHeader stays empty in a skirmish room.
   //
   // Sort keys follow the special battles' own (prb_items.py): by vehicle is
   // class, then tier from the highest, then name; by status is in battle,
   // then ready, then the rest. Empty slots go last in every order but the
   // client's. "score" is the rating chosen in the mod's settings.
   //
   // With the skirmish room switched off in the settings, all of it is
   // hidden and the rows are back in the client's order.
   public class MembersSection
   {
      public static const MODES:Array = ["default", "vehicle", "status", "name", "score", "rating"];

      private static const FALLBACK_LABELS:Array = ["By order", "By vehicle", "By status", "By name", "By score", "By rating"];

      private static const SLOTS:int = 15;

      private static const VEHICLE_TYPES:Array = ["heavyTank", "mediumTank", "AT-SPG", "lightTank", "SPG"];

      private static const DROPDOWN_WIDTH:int = 150;

      private static const BADGE_GAP:int = 10;

      // TextField's gutter, on each side of its text.
      private static const GUTTER:int = 2;

      private var _section:Sprite;

      private var _onPick:Function;

      private var _dropdown:DropdownMenu;

      private var _labels:String = null;

      // The orders in the dropdown, in its order.
      private var _shownModes:Array = MODES.concat();

      private var _average:TextField;

      private var _averageHtml:String = null;

      // Each row's y as the client laid it out, by slot number.
      private var _rowY:Array = [];

      private var _mode:String = "default";

      private var _scores:Object = {};

      public function MembersSection(section:Sprite, onPick:Function)
      {
         this._section = section;
         this._onPick = onPick;
         for(var i:int = 0; i < SLOTS; i++)
         {
            this._rowY.push(DisplayObject(section["slot" + i]).y);
         }
         this._dropdown = App.utils.classFactory.getComponent("DropdownMenuUI", DropdownMenu) as DropdownMenu;
         this._dropdown.dropdown = "DropdownMenu_ScrollingList";
         this._dropdown.itemRenderer = "DropDownListItemRendererSound";
         this._dropdown.width = DROPDOWN_WIDTH;
         this._dropdown.menuWidth = DROPDOWN_WIDTH;
         this._dropdown.menuRowCount = MODES.length;
         this._dropdown.dataProvider = new DataProvider(FALLBACK_LABELS.concat());
         this._dropdown.addEventListener(ListEvent.INDEX_CHANGE, this.onIndexChange);
         section.addChild(this._dropdown);
         this._average = new TextField();
         this._average.selectable = false;
         this._average.mouseEnabled = false;
         this._average.autoSize = TextFieldAutoSize.LEFT;
         this._average.wordWrap = false;
         section.addChild(this._average);
      }

      public static function accepts(target:Object) : Boolean
      {
         return target is Sprite && field(target, "lblTeamHeader") is TextField && field(target, "slot0") is DisplayObject && field(target, "slot" + (SLOTS - 1)) is DisplayObject;
      }

      private static function field(target:Object, name:String) : Object
      {
         try
         {
            return target[name];
         }
         catch(e:Error)
         {
         }
         return null;
      }

      public function get section() : Sprite
      {
         return this._section;
      }

      public function dispose() : void
      {
         this._mode = "default";
         this.order();
         this._dropdown.removeEventListener(ListEvent.INDEX_CHANGE, this.onIndexChange);
         for each(var added:DisplayObject in [this._dropdown, this._average])
         {
            if(added.parent != null)
            {
               added.parent.removeChild(added);
            }
         }
         this._dropdown.dispose();
         this._dropdown = null;
         this._section = null;
         this._onPick = null;
      }

      // Every frame, from RoomTools, with the state Python keeps up to date.
      public function update(enabled:Boolean, mode:String, labels:String, scores:Object, averageHtml:String) : void
      {
         this._mode = enabled && MODES.indexOf(mode) >= 0 ? mode : "default";
         this._scores = scores;
         this._dropdown.visible = enabled;
         this.updateDropdown(labels);
         this.order();
         this.updateAverage(enabled ? averageHtml : "");
      }

      private function updateDropdown(labels:String) : void
      {
         if(labels != this._labels)
         {
            this._labels = labels;
            var names:Array = labels != null ? labels.split("\n") : [];
            if(names.length != MODES.length)
            {
               names = FALLBACK_LABELS.concat();
            }
            // An empty label is an order left out of the dropdown.
            this._shownModes = [];
            var shown:Array = [];
            for(var i:int = 0; i < MODES.length; i++)
            {
               if(names[i] != "")
               {
                  this._shownModes.push(MODES[i]);
                  shown.push(names[i]);
               }
            }
            this._dropdown.menuRowCount = shown.length;
            this._dropdown.dataProvider = new DataProvider(shown);
         }
         if(this._shownModes.indexOf(this._mode) < 0)
         {
            this._mode = "default";
         }
         var index:int = this._shownModes.indexOf(this._mode);
         if(this._dropdown.selectedIndex != index)
         {
            this._dropdown.selectedIndex = index;
         }
         var row:DisplayObject = DisplayObject(this._section["slot0"]);
         this._dropdown.x = Math.round(row.x + row.width - DROPDOWN_WIDTH);
         this._dropdown.y = Math.round(this.titleTop() + (this.title().height - this._dropdown.height) / 2);
      }

      private function updateAverage(averageHtml:String) : void
      {
         if(averageHtml != this._averageHtml)
         {
            this._averageHtml = averageHtml;
            this._average.htmlText = averageHtml;
         }
         this._average.visible = averageHtml != "";
         // Where the title's text is, not its field: the field is wider than
         // its words, and aligns them within itself.
         var title:TextField = this.title();
         var line:TextLineMetrics = title.getLineMetrics(0);
         var top:Point = this._section.globalToLocal(title.localToGlobal(new Point(0, 0)));
         this._average.x = Math.round(top.x + GUTTER + line.x + line.width + BADGE_GAP);
         this._average.y = Math.round(top.y + (title.height - this._average.height) / 2);
      }

      // The title as shown: the room's, or the section's in a room without one.
      private function title() : TextField
      {
         var room:TextField = this._section.parent != null ? field(this._section.parent, "teamHeader") as TextField : null;
         return room != null && room.text.length > 0 ? room : TextField(this._section["lblTeamHeader"]);
      }

      private function titleTop() : Number
      {
         var title:TextField = this.title();
         return this._section.globalToLocal(title.localToGlobal(new Point(0, 0))).y;
      }

      private function onIndexChange(event:ListEvent) : void
      {
         var index:int = this._dropdown.selectedIndex;
         if(index >= 0 && index < this._shownModes.length && this._shownModes[index] != this._mode)
         {
            this._mode = this._shownModes[index];
            this._onPick(this._mode);
         }
      }

      private function order() : void
      {
         var rows:Array = [];
         for(var i:int = 0; i < SLOTS; i++)
         {
            rows.push(i);
         }
         rows.sort(this.compare);
         for(var place:int = 0; place < SLOTS; place++)
         {
            this.move(rows[place], this._rowY[place]);
         }
      }

      // A row, and what the client draws beside it by slot number.
      private function move(slot:int, y:Number) : void
      {
         // A disposed section has let go of its rows.
         var row:DisplayObject = field(this._section, "slot" + slot) as DisplayObject;
         if(row == null)
         {
            return;
         }
         var dy:Number = y - row.y;
         if(dy == 0)
         {
            return;
         }
         row.y = y;
         for each(var name:String in ["gunnerIcon", "dropTargetIndicator"])
         {
            var beside:DisplayObject = field(this._section, name + slot) as DisplayObject;
            if(beside != null)
            {
               beside.y += dy;
            }
         }
      }

      private function compare(a:int, b:int) : int
      {
         if(this._mode == "default")
         {
            return a - b;
         }
         var da:Object = this.data(a);
         var db:Object = this.data(b);
         if((da == null) != (db == null))
         {
            return da == null ? 1 : -1;
         }
         var result:int = da != null ? this.compareData(da, db) : 0;
         return result != 0 ? result : a - b;
      }

      // A taken slot's data, or null for an empty or closed one.
      private function data(slot:int) : Object
      {
         var row:Object = field(this._section, "slot" + slot);
         var slotData:Object = row != null ? row.slotData : null;
         return slotData != null && slotData.player != null ? slotData : null;
      }

      private function compareData(a:Object, b:Object) : int
      {
         switch(this._mode)
         {
            case "vehicle":
               return this.compareVehicles(a, b);
            case "status":
               if(a.playerStatus != b.playerStatus)
               {
                  return int(b.playerStatus) - int(a.playerStatus);
               }
               return this.compareVehicles(a, b) || this.compareNames(a, b);
            case "name":
               return this.compareNames(a, b);
            case "score":
               return compareNumbers(this._scores[String(a.player.dbID)], this._scores[String(b.player.dbID)]);
            case "rating":
               return compareNumbers(parseRating(a.player.rating), parseRating(b.player.rating));
         }
         return 0;
      }

      private function compareVehicles(a:Object, b:Object) : int
      {
         var va:Object = a.selectedVehicle;
         var vb:Object = b.selectedVehicle;
         if((va == null) != (vb == null))
         {
            return va == null ? 1 : -1;
         }
         if(va == null)
         {
            return 0;
         }
         var ta:int = typeRank(va.type);
         var tb:int = typeRank(vb.type);
         if(ta != tb)
         {
            return ta - tb;
         }
         if(va.level != vb.level)
         {
            return int(vb.level) - int(va.level);
         }
         return compareText(va.shortUserName, vb.shortUserName);
      }

      private function compareNames(a:Object, b:Object) : int
      {
         return compareText(a.player.userName, b.player.userName);
      }

      private static function typeRank(type:String) : int
      {
         var rank:int = VEHICLE_TYPES.indexOf(type);
         return rank >= 0 ? rank : VEHICLE_TYPES.length;
      }

      // Highest first; a missing value after every known one.
      private static function compareNumbers(a:*, b:*) : int
      {
         var knownA:Boolean = a is Number && !isNaN(a);
         var knownB:Boolean = b is Number && !isNaN(b);
         if(knownA != knownB)
         {
            return knownA ? -1 : 1;
         }
         if(!knownA || a == b)
         {
            return 0;
         }
         return b > a ? 1 : -1;
      }

      private static function compareText(a:String, b:String) : int
      {
         var la:String = (a || "").toLowerCase();
         var lb:String = (b || "").toLowerCase();
         return la < lb ? -1 : (la > lb ? 1 : 0);
      }

      // "6,151" or "6 151" as the client formats it; NaN when there is none.
      private static function parseRating(rating:String) : Number
      {
         var digits:String = (rating || "").replace(/\D/g, "");
         return digits.length > 0 ? Number(digits) : NaN;
      }
   }
}
