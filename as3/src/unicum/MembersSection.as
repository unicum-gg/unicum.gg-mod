package unicum
{
   import flash.display.DisplayObject;
   import flash.display.DisplayObjectContainer;
   import flash.display.Sprite;
   import flash.geom.Point;
   import flash.geom.Rectangle;
   import flash.utils.Dictionary;
   import flash.utils.getQualifiedClassName;
   import flash.text.StaticText;
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

      // The room's own Rating column, on the row. Named rather than searched
      // for: `ratingTF` is SimpleSlotRenderer's and this window's rows are
      // ClanBattleSortieSlotUI, a library symbol with no source to read. The
      // name came from asking a row to list its children.
      private static const RATING_FIELD:String = "candidateRating";

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

      // Each member's badge markup by dbID, and the field that draws it, one
      // per slot so a row keeps its own and nothing is created per frame.
      private var _badges:Object = {};

      private var _cells:Array = [];

      // What each cell was last given. Kept apart from the field, because
      // `htmlText` does not read back what it was assigned: Flash rebuilds
      // the markup, so comparing against it is always unequal, and the badge
      // would be reassigned every frame -- which restarts the image's load
      // every frame and leaves the cell empty for good. `_averageHtml` beside
      // it exists for the same reason.
      private var _cellHtml:Array = [];

      private var _header:TextField;

      private var _headerText:String = null;

      // The room's own figures in the column we took, and whether each was
      // visible when we took it; and the room's own name for that column.
      // Both are put back by `giveBackColumn`.
      private var _hidden:Dictionary = new Dictionary(true);

      private var _title:DisplayObject = null;

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
         // As many rows as it has orders: left fixed, the game's dropdown works
         // its row count out from maxRowCount, which is -1 and reads as five
         // whatever it holds (DropdownMenu.calcMenuAvailableRowCount).
         this._dropdown.menuRowsFixed = false;
         this._dropdown.menuRowCount = MODES.length;
         this._dropdown.dataProvider = new DataProvider(FALLBACK_LABELS.concat());
         this._dropdown.addEventListener(ListEvent.INDEX_CHANGE, this.onIndexChange);
         section.addChild(this._dropdown);
         this._average = this.plainField(section);
         this._header = this.plainField(section);
         for(var slot:int = 0; slot < SLOTS; slot++)
         {
            this._cells.push(this.plainField(section));
            this._cellHtml.push(null);
         }
      }

      // A field the mod draws into: no selection, no mouse, no wrapping, and
      // sized by its own text.
      private function plainField(section:Sprite) : TextField
      {
         var made:TextField = new TextField();
         made.selectable = false;
         made.mouseEnabled = false;
         made.autoSize = TextFieldAutoSize.LEFT;
         made.wordWrap = false;
         section.addChild(made);
         return made;
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

      // What this section sees, for Python to log. Every link in the chain
      // between a member and a badge in the room's own column, counted:
      // the rows, the room's figure field on each, who is seated, and which
      // of them a badge arrived for.
      public function report() : String
      {
         var rows:int = 0;
         var figures:int = 0;
         var seated:int = 0;
         var rated:int = 0;
         for(var slot:int = 0; slot < SLOTS; slot++)
         {
            var row:Object = field(this._section, "slot" + slot);
            if(row == null)
            {
               continue;
            }
            rows++;
            if(field(row, RATING_FIELD) is TextField)
            {
               figures++;
            }
            var taken:Object = this.data(slot);
            if(taken != null && taken.player != null)
            {
               seated++;
               if(this._badges[String(taken.player.dbID)] != null)
               {
                  rated++;
               }
            }
         }
         var held:int = 0;
         for(var id:Object in this._badges)
         {
            held++;
         }
         // Where the column we took actually is, in the same space the words
         // below are given in. Without it the two cannot be compared, and
         // comparing them is the whole question.
         var column:String = "none";
         var first:TextField = field(field(this._section, "slot0"), RATING_FIELD) as TextField;
         if(first != null)
         {
            var at:Point = this._section.globalToLocal(first.localToGlobal(new Point(0, 0)));
            column = Math.round(at.x) + "," + Math.round(at.y) +
                     "w" + Math.round(first.width) + "h" + Math.round(first.height);
         }
         var band:Rectangle = this.headerLine();
         return "rows=" + rows + " figureFields=" + figures + " seated=" + seated +
                " rated=" + rated + " held=" + held + " header=" + this._headerText +
                " foundTitle=" + (this._title != null) +
                " column=" + column +
                " band=" + (band == null ? "none"
                            : Math.round(band.y) + "h" + Math.round(band.height)) +
                ";";
      }

      public function dispose() : void
      {
         this._mode = "default";
         this.order();
         // The room's own column, exactly as it was before the mod took it.
         this.giveBackColumn();
         this._dropdown.removeEventListener(ListEvent.INDEX_CHANGE, this.onIndexChange);
         for each(var added:DisplayObject in [this._dropdown, this._average, this._header].concat(this._cells))
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
      public function update(enabled:Boolean, mode:String, labels:String, scores:Object, averageHtml:String, badges:Object, header:String) : void
      {
         this._mode = enabled && MODES.indexOf(mode) >= 0 ? mode : "default";
         this._scores = scores;
         this._badges = badges != null ? badges : {};
         this._dropdown.visible = enabled;
         this.updateDropdown(labels);
         this.order();
         this.updateAverage(enabled ? averageHtml : "");
         // After `order`, never before: the rows have just been moved, and a
         // badge is placed against the row it belongs to wherever that row
         // has ended up.
         this.updateColumn(enabled, enabled ? header : "");
      }

      // Each member's rating, in a column of its own just left of the room's.
      //
      // LEFT of it, which the layout decides rather than taste: the Vehicles
      // column starts immediately right of the room's Rating and its button
      // fills it, so there is nothing to the right to sit in.
      //
      // Placed against the row's own `candidateRating`, so the column lines
      // up with the room's whatever the window's width does, and a badge
      // rides at the height of the number it stands beside.
      private function updateColumn(enabled:Boolean, header:String) : void
      {
         // The column is ours when it has a name to put on it. Python sends
         // one only while the surface draws ratings, so this one test covers
         // the setting, the extended info key and the window being closed.
         var ours:Boolean = enabled && header != null && header != "";
         if(!ours)
         {
            this.giveBackColumn();
            for(var empty:int = 0; empty < SLOTS; empty++)
            {
               TextField(this._cells[empty]).visible = false;
               this._cellHtml[empty] = null;
            }
            this.updateColumnHeader("", null);
            return;
         }
         var anchor:TextField = null;
         for(var slot:int = 0; slot < SLOTS; slot++)
         {
            var cell:TextField = TextField(this._cells[slot]);
            var row:Object = field(this._section, "slot" + slot);
            var rating:TextField = row != null ? field(row, RATING_FIELD) as TextField : null;
            var taken:Object = this.data(slot);
            if(rating == null || taken == null || taken.player == null)
            {
               // Nobody in this seat: the room's own cell is left exactly as
               // the room drew it, which for an empty seat is nothing.
               cell.visible = false;
               this._cellHtml[slot] = null;
               continue;
            }
            // Somebody is in it, so the column is ours for this row whether
            // or not we have a figure for them. A row we cannot rate shows
            // nothing rather than Wargaming's number, because the header now
            // says what this column holds and must not say it over somebody
            // else's figure.
            this.hideRoomFigure(rating);
            if(anchor == null)
            {
               anchor = rating;
            }
            var markup:String = this._badges[String(taken.player.dbID)] as String;
            if(markup == null || markup == "")
            {
               cell.visible = false;
               this._cellHtml[slot] = null;
               continue;
            }
            cell.visible = true;
            if(this._cellHtml[slot] != markup)
            {
               this._cellHtml[slot] = markup;
               cell.htmlText = markup;
            }
            var origin:Point = this._section.globalToLocal(rating.localToGlobal(new Point(0, 0)));
            cell.x = Math.round(origin.x + (rating.width - cell.width) / 2);
            cell.y = Math.round(origin.y + (rating.height - cell.height) / 2);
         }
         this.updateColumnHeader(header, anchor);
      }

      // The room's own figure, out of the way while ours stands in its
      // place.
      //
      // Remembered, so `giveBackColumn` puts back exactly what it took and
      // nothing else: the room hides this field itself on a seat nobody is
      // in, and a blanket `visible = true` would show a number where the
      // room means to show none.
      private function hideRoomFigure(rating:TextField) : void
      {
         if(this._hidden[rating] == null)
         {
            this._hidden[rating] = rating.visible;
         }
         if(rating.visible)
         {
            rating.visible = false;
         }
      }

      private function giveBackColumn() : void
      {
         for(var key:Object in this._hidden)
         {
            TextField(key).visible = Boolean(this._hidden[key]);
         }
         this._hidden = new Dictionary(true);
         if(this._title != null)
         {
            this._title.visible = true;
            this._title = null;
         }
      }

      // The column's name, in the room's own header band, over the column we
      // took.
      //
      // The room writes "Rating" there, and that label has no name a mod can
      // ask for: the section's named fields are the members count and the
      // vehicles title, and this is neither. So it is found by where it is,
      // which is the one thing about it that cannot drift: text above the
      // first row, over this column's box.
      private function updateColumnHeader(header:String, anchor:TextField) : void
      {
         if(header == null || header == "" || anchor == null)
         {
            this._header.visible = false;
            return;
         }
         var origin:Point = this._section.globalToLocal(anchor.localToGlobal(new Point(0, 0)));
         this.hideRoomTitle(origin.x, anchor.width);
         this._header.visible = true;
         if(this._headerText != header)
         {
            this._headerText = header;
            this._header.defaultTextFormat = this.title().defaultTextFormat;
            this._header.htmlText = header;
         }
         this._header.x = Math.round(origin.x + (anchor.width - this._header.width) / 2);
         // On the room's own header line, which is where its column names
         // are. Taken from the line itself, so ours sits with the names it
         // stands among rather than at a height worked out from the title.
         // Always off the line, never off the label we hid: that label lives
         // inside a button inside a bar, so its own `y` is given in its
         // container's space and means nothing here. The line is read in the
         // section's, which is the space everything else on this row uses.
         var line:Rectangle = this.headerLine();
         if(line != null)
         {
            this._header.y = Math.round(line.y + (line.height - this._header.height) / 2);
            return;
         }
         var band:Number = this.titleTop() + this.title().height;
         this._header.y = Math.round(band + (this._rowY[0] - band - this._header.height) / 2);
      }

      // The line the room writes its column names on, in the section's own
      // space, or null.
      //
      // Read off `lblTeamVehicles`, which is the room's own field for the
      // Vehicles title and sits on that line by construction. Named, so it
      // cannot be confused with anything, where the height of the line was
      // being worked out from the title's and landed a row too high.
      private function headerLine() : Rectangle
      {
         var vehicles:DisplayObject = field(this._section, "lblTeamVehicles") as DisplayObject;
         if(vehicles == null)
         {
            return null;
         }
         var origin:Point = this._section.globalToLocal(vehicles.localToGlobal(new Point(0, 0)));
         return new Rectangle(origin.x, origin.y, vehicles.width, vehicles.height);
      }

      // The room's own name for the column, hidden while ours stands in it.
      //
      // Searched for once and kept. Two levels deep at most, because a label
      // deeper than that is inside something that is not a header line, and
      // hiding the wrong text is worse than leaving ours beside theirs --
      // which is exactly what the first attempt did: it took any text whose
      // CENTRE fell in the column, and the section's own title runs the full
      // width of the panel, so its centre falls in whichever column sits in
      // the middle. It hid the title and put our name on the title's line.
      //
      // So a candidate has to SIT in the column, most of its width inside
      // it, and on the line the room writes its column names on.
      private function hideRoomTitle(left:Number, width:Number) : void
      {
         if(this._title != null)
         {
            this._title.visible = false;
            return;
         }
         var line:Rectangle = this.headerLine();
         this._title = this.findTitle(this._section, left, width, line, 2);
         if(this._title == null && this._section.parent != null)
         {
            // The room's column names are not in the section at all. They
            // are a sortable header BAR beside it, in the section's parent,
            // and each name is a label inside one of its buttons -- which is
            // why a search of the section found nothing, twice, and why the
            // section's own `lblTeamVehicles` is an empty field: it draws
            // nothing, the bar draws everything.
            //
            // Deeper, because a label inside a button inside a bar is four
            // levels down where a field of the section was one.
            this._title = this.findTitle(
               DisplayObjectContainer(this._section.parent), left, width, line, 4);
         }
         if(this._title != null)
         {
            this._title.visible = false;
         }
      }

      private function findTitle(where:DisplayObjectContainer, left:Number, width:Number,
                                 line:Rectangle, depth:int) : DisplayObject
      {
         for(var i:int = 0; i < where.numChildren; i++)
         {
            var kid:DisplayObject = where.getChildAt(i);
            if(!kid.visible || kid == this._header || kid == this._average ||
               this._cells.indexOf(kid) >= 0 || kid == this._dropdown ||
               kid == this.title())
            {
               continue;
            }
            if(kid is TextField || kid is StaticText)
            {
               // Text, and text that says something: a header bar is full of
               // empty fields the room never writes into, and hiding one of
               // those would leave the name it was meant to replace on
               // screen while this reported success.
               if(MembersSection.hasText(kid) && this.sitsInColumn(kid, left, width, line))
               {
                  return kid;
               }
            }
            else if(depth > 0 && kid is DisplayObjectContainer)
            {
               var found:DisplayObject = this.findTitle(
                  DisplayObjectContainer(kid), left, width, line, depth - 1);
               if(found != null)
               {
                  return found;
               }
            }
         }
         return null;
      }

      // How much of the COLUMN a label has to cover to be that column's
      // name, and how many times the column it may measure.
      //
      // Against the column, not against the label: a name is routinely wider
      // than the figures beneath it. The room's "Rating" is 64 wide over a
      // 36-wide column -- it covers the column entirely and still fails a
      // test asking for 60% of ITSELF, which is how this was rejected by two
      // pixels. The ceiling is what keeps a banner out: the panel's own
      // title runs the full width of the window, fourteen times the column.
      private static const COVERS:Number = 0.6;

      private static const WIDEST:Number = 4;

      private static function hasText(kid:DisplayObject) : Boolean
      {
         if(kid is TextField)
         {
            var said:String = TextField(kid).text;
            return said != null && said.replace(/^\s+|\s+$/g, "").length > 0;
         }
         return true;
      }

      private function sitsInColumn(kid:DisplayObject, left:Number, width:Number,
                                    line:Rectangle) : Boolean
      {
         if(kid.width <= 0 || kid.height <= 0)
         {
            return false;
         }
         var origin:Point = this._section.globalToLocal(kid.localToGlobal(new Point(0, 0)));
         var over:Number = Math.min(origin.x + kid.width, left + width) -
                           Math.max(origin.x, left);
         if(over <= 0 || over < width * COVERS || kid.width > width * WIDEST)
         {
            return false;
         }
         var middle:Number = origin.y + kid.height / 2;
         if(line != null)
         {
            return middle >= line.y && middle <= line.y + line.height;
         }
         // No line to go by: anywhere above the first seat, as before.
         return origin.y + kid.height <= this._rowY[0];
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
         // As far in from the right edge as the title is from the left. The
         // dropdown used to sit flush against the rows, which read as an
         // element shoved into the corner next to a heading that breathes.
         // The inset is MEASURED from the title rather than written down: the
         // heading's own left offset is whatever this client's layout gives
         // it, and a number typed in here would be right on one machine.
         this._dropdown.x = Math.round(row.x + row.width - DROPDOWN_WIDTH - this.titleInset(row));
         this._dropdown.y = Math.round(this.titleTop() + (this.title().height - this._dropdown.height) / 2);
      }

      // Where the title's first letter is, in the section's own coordinates.
      //
      // The TEXT, not the field: the field is wider than its words and aligns
      // them within itself, so its bounds say nothing about where the heading
      // appears to start.
      private function titleTextLeft() : Number
      {
         var title:TextField = this.title();
         var line:TextLineMetrics = title.getLineMetrics(0);
         var top:Point = this._section.globalToLocal(title.localToGlobal(new Point(0, 0)));
         return top.x + GUTTER + line.x;
      }

      // How far that letter sits from the rows' left edge.
      private function titleInset(row:DisplayObject) : Number
      {
         return Math.max(0, this.titleTextLeft() - row.x);
      }

      private function updateAverage(averageHtml:String) : void
      {
         if(averageHtml != this._averageHtml)
         {
            this._averageHtml = averageHtml;
            this._average.htmlText = averageHtml;
         }
         this._average.visible = averageHtml != "";
         var title:TextField = this.title();
         var line:TextLineMetrics = title.getLineMetrics(0);
         var top:Point = this._section.globalToLocal(title.localToGlobal(new Point(0, 0)));
         this._average.x = Math.round(this.titleTextLeft() + line.width + BADGE_GAP);
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

      // Again at the last moment, after the client has laid its rows out:
      // moved in the frame's first half, they would be put back before the
      // frame is drawn, and the list would jump.
      public function reorder() : void
      {
         this.order();
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
