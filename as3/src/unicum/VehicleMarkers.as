package unicum
{
   import flash.display.DisplayObject;
   import flash.display.DisplayObjectContainer;
   import flash.geom.Point;
   import flash.geom.Rectangle;
   import flash.text.TextField;
   import flash.text.TextFormatAlign;
   import flash.utils.Dictionary;

   // Rating badge and flags for each player in the battle's Scaleform
   // screens, the badge nearest the row. In the players panel they sit beside
   // the vehicle icon: right of it for allies, left of it for enemies, where
   // the icon is nearest the middle of the screen. A Tab table packs a row
   // from edge to edge, so there they sit outside each team's rows, where the
   // team's average joins its badge column on the team name's line.
   //
   // Part of the battle view (TeamNamesHtml.as); Python (src/unicum/battle.py)
   // gives the markup per vehicle and the order of each team.
   //
   // No row names its vehicle, but every one of these screens lays a team out
   // in the order the statistics controller sends (leftItemsIDs /
   // rightItemsIDs), so a row's place gives its vehicle:
   //
   //   players panel   an object with listLeft and listRight; each list has
   //                   a container of rows, each with its vehicleIcon, set at
   //                   the row height times its place in that order; rows in
   //                   more than one column are left alone
   //   Tab (tables)    an object with vehicleIconCollection, one icon per
   //                   row of both teams; which half is which varies by mode,
   //                   so a team is the icons on its side of the screen
   //   loading screen  an object with vehicleIconsAlly and vehicleIconsEnemy
   //
   // The random battle's Tab is Gameface and has no such objects.
   //
   // A team's markers form two columns, badges then flags, so they line up
   // however wide each vehicle's icon is drawn or each rating is written.
   //
   // The client already puts things on that side of the icon -- health bars,
   // chat command pings, spotted indicators, prestige -- and each mode or mod
   // may add its own. So rather than a list per mode, the columns start past
   // the farthest visible neighbour on their side, in the icons' band:
   // whatever shows there pushes them out, and they come back when it hides.
   public class VehicleMarkers
   {
      // Between the icon's edge and the badge column.
      private static const GAP:int = 6;

      // Between the badge column and the flags column.
      private static const SPACE:int = 4;

      // A TextField's gutter, before its first image.
      private static const GUTTER:int = 2;

      private static const HEIGHT:int = 20;

      // A field draws its images this much higher than its middle (measured
      // in the players panel: a badge's centre 2px above its row's), so a
      // field centred on a row is lowered by it.
      private static const IMAGE_RISE:int = 2;

      // Wider than any neighbour: a row background spans the whole row.
      private static const MAX_NEIGHBOUR_WIDTH:int = 200;

      private static const NAME:String = "unicumMarkers";

      // A team name the client set with its average: "name  <average sign> <IMG .../>".
      public static const AVERAGE:RegExp = /^(.*?)\s*\u00d8\s*(<IMG.*)$/s;

      private static const WIDTH:RegExp = /width="(\d+)"/i;

      // Backgrounds and hit areas, which lie under the icon and its neighbours.
      private static const BACKGROUND:RegExp = /(bg|hit|background)$/i;

      // vehicle id -> [badge html, badge width, flags html, flags width]
      private var _markers:Object = {};

      private var _left:Array = [];

      private var _right:Array = [];

      private var _given:Array = [null, null, null];

      private var _panels:Dictionary = new Dictionary(true);

      private var _tables:Dictionary = new Dictionary(true);

      private var _loadings:Dictionary = new Dictionary(true);

      // vehicle icon -> [badge field, flags field]
      private var _fields:Dictionary = new Dictionary(true);

      // field -> the markup last set on it
      private var _html:Dictionary = new Dictionary(true);

      // team name field -> [the name left in it, the average taken out]
      private var _averages:Dictionary = new Dictionary(true);

      // team name field -> [badge field, average sign field]
      private var _averageFields:Dictionary = new Dictionary(true);

      private var _names:Dictionary = null;

      public function VehicleMarkers()
      {
         super();
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

      public function inspect(target:Object) : void
      {
         if(field(target, "listLeft") != null && field(target, "listRight") != null)
         {
            this._panels[target] = true;
         }
         if(field(target, "vehicleIconCollection") != null)
         {
            this._tables[target] = true;
         }
         if(field(target, "vehicleIconsAlly") != null && field(target, "vehicleIconsEnemy") != null)
         {
            this._loadings[target] = true;
         }
      }

      // names: team name field -> [the text the client set, the text once
      // shown as HTML], kept by TeamNamesHtml, since a name already shown as
      // HTML no longer reads back its average's tag.
      public function update(markers:String, left:String, right:String, names:Dictionary,
                             panelHidden:Boolean = false, tabHidden:Boolean = false,
                             loadingHidden:Boolean = false) : void
      {
         this._names = names;
         this.read(markers, left, right);
         // No ids: every row's fields are hidden, as for a player with no rating.
         for(var panel:Object in this._panels)
         {
            this.drawList(field(panel, "listLeft") as DisplayObjectContainer, panelHidden ? [] : this._left, true);
            this.drawList(field(panel, "listRight") as DisplayObjectContainer, panelHidden ? [] : this._right, false);
         }
         for(var table:Object in this._tables)
         {
            this.drawTable(table, tabHidden);
         }
         for(var loading:Object in this._loadings)
         {
            this.drawIcons(field(loading, "vehicleIconsAlly"), loadingHidden ? [] : this._left, true);
            this.drawIcons(field(loading, "vehicleIconsEnemy"), loadingHidden ? [] : this._right, false);
         }
      }

      public function dispose() : void
      {
         for each(var owned:Dictionary in [this._fields, this._averageFields])
         {
            for(var key:Object in owned)
            {
               for each(var shown:TextField in owned[key])
               {
                  if(shown.parent != null)
                  {
                     shown.parent.removeChild(shown);
                  }
               }
            }
         }
         for(var team:Object in this._averages)
         {
            // Give the name back its average, as the client set it.
            var name:TextField = team as TextField;
            if(name.text == this._averages[team][0])
            {
               name.htmlText = this._averages[team][0] + "  \u00d8 " + this._averages[team][1];
            }
         }
         this._averages = new Dictionary(true);
         this._averageFields = new Dictionary(true);
         this._fields = new Dictionary(true);
         this._html = new Dictionary(true);
         this._panels = new Dictionary(true);
         this._tables = new Dictionary(true);
         this._loadings = new Dictionary(true);
      }

      // The client's Scaleform has no JSON: markers come one vehicle a line,
      // "id TAB badge TAB badge width TAB flags TAB flags width", and orders
      // as comma separated ids.
      private function read(markers:String, left:String, right:String) : void
      {
         if(markers != this._given[0])
         {
            this._given[0] = markers;
            this._markers = {};
            for each(var line:String in (markers || "").split("\n"))
            {
               var parts:Array = line.split("\t");
               if(parts.length == 5)
               {
                  this._markers[parts[0]] = [parts[1], Number(parts[2]), parts[3], Number(parts[4])];
               }
            }
         }
         if(left != this._given[1])
         {
            this._given[1] = left;
            this._left = left ? left.split(",") : [];
         }
         if(right != this._given[2])
         {
            this._given[2] = right;
            this._right = right ? right.split(",") : [];
         }
      }

      private function drawList(list:DisplayObjectContainer, ids:Array, ally:Boolean) : void
      {
         var rows:DisplayObjectContainer = rowsOf(list);
         if(rows == null)
         {
            return;
         }
         // A row's place in the team is its place from the top: the list
         // sets each row at its index times the row height, whatever that
         // height is. Rows side by side are a layout whose order is not known.
         var found:Array = [];
         for(var i:int = 0; i < rows.numChildren; i++)
         {
            var row:DisplayObjectContainer = rows.getChildAt(i) as DisplayObjectContainer;
            var icon:DisplayObject = row != null ? field(row, "vehicleIcon") as DisplayObject : null;
            if(icon != null)
            {
               if(found.length > 0 && Math.round(row.x) != Math.round(found[0].row.x))
               {
                  return;
               }
               found.push({"row":row, "icon":icon});
            }
         }
         found.sort(function(a:Object, b:Object) : Number
         {
            return a.row.y - b.row.y;
         });
         var icons:Array = [];
         var rowIds:Array = [];
         var shown:Array = [];
         for(i = 0; i < found.length; i++)
         {
            icons.push(found[i].icon);
            rowIds.push(ids[i]);
            shown.push(found[i].row.visible && list.visible);
         }
         this.placeTeam(icons, rowIds, shown, ally, NaN);
      }

      // The list's child whose children are rows: the list also holds the
      // voice chat button, backgrounds and indicators, in no fixed order.
      private static function rowsOf(list:DisplayObjectContainer) : DisplayObjectContainer
      {
         if(list == null)
         {
            return null;
         }
         for(var i:int = 0; i < list.numChildren; i++)
         {
            var child:DisplayObjectContainer = list.getChildAt(i) as DisplayObjectContainer;
            if(child != null && child.numChildren > 0 && field(child.getChildAt(0), "vehicleIcon") != null)
            {
               return child;
            }
         }
         return null;
      }

      private function drawTable(table:Object, hidden:Boolean) : void
      {
         var icons:Object = field(table, "vehicleIconCollection");
         var count:int = icons != null ? int(icons.length) : 0;
         var middle:Number = 0;
         var placed:int = 0;
         for(var i:int = 0; i < count; i++)
         {
            var icon:DisplayObject = icons[i] as DisplayObject;
            if(icon != null && icon.parent != null)
            {
               middle += centre(icon);
               placed++;
            }
         }
         if(placed == 0)
         {
            return;
         }
         middle /= placed;
         // Each half keeps the collection's order, which is its rows' order.
         var lefts:Array = [];
         var rights:Array = [];
         for(i = 0; i < count; i++)
         {
            icon = icons[i] as DisplayObject;
            if(icon != null && icon.parent != null)
            {
               (centre(icon) < middle ? lefts : rights).push(icon);
            }
         }
         var leftColumn:Array = this.placeTeam(lefts, hidden ? [] : this._left, null, false, middle);
         var rightColumn:Array = this.placeTeam(rights, hidden ? [] : this._right, null, true, middle);
         for each(var name:String in ["team1TF", "team2TF"])
         {
            var team:TextField = field(table, name) as TextField;
            if(team != null && team.parent != null)
            {
               var left:Boolean = centre(team) < middle;
               this.placeAverage(team, left ? leftColumn : rightColumn, !left, hidden);
            }
         }
      }

      private static function centre(item:DisplayObject) : Number
      {
         var bounds:Rectangle = item.getBounds(item.parent);
         return item.parent.localToGlobal(new Point(bounds.x + bounds.width / 2, 0)).x;
      }

      // Moves a team's average out of its name into the team's badge column,
      // the average sign where the flags go. [edge, badges width], or null
      // while no player's markers are drawn, leaves the name as it is.
      // Hidden, the average is kept out of the name and not drawn.
      private function placeAverage(team:TextField, column:Array, rightwards:Boolean, hidden:Boolean) : void
      {
         var taken:Array = this._averages[team] as Array;
         if(taken == null || team.text != taken[0])
         {
            // New text from the client since: take its average, if any.
            taken = null;
            var set:String = team.text;
            var shown:Array = this._names != null ? this._names[team] as Array : null;
            if(set.indexOf("<IMG") < 0 && shown != null && set == shown[1])
            {
               set = shown[0];
            }
            var found:Object = AVERAGE.exec(set);
            if(found != null && WIDTH.test(found[2]))
            {
               taken = [found[1], found[2]];
            }
         }
         var fields:Array = this._averageFields[team] as Array;
         if(hidden)
         {
            if(taken != null)
            {
               if(team.text != taken[0])
               {
                  team.text = taken[0];
               }
               this._averages[team] = taken;
            }
            for each(var unshown:TextField in fields)
            {
               unshown.visible = false;
            }
            return;
         }
         if(taken == null || column == null)
         {
            if(taken != null && team.text == taken[0])
            {
               // No column any more: the average goes back after the name.
               team.htmlText = taken[0] + "  \u00d8 " + taken[1];
            }
            delete this._averages[team];
            for each(var gone:TextField in fields)
            {
               gone.visible = false;
            }
            return;
         }
         if(team.text != taken[0])
         {
            team.text = taken[0];
         }
         this._averages[team] = taken;
         if(fields == null)
         {
            var sign:TextField = newField();
            sign.defaultTextFormat = team.getTextFormat();
            sign.text = "\u00d8";
            fields = [newField(), sign];
            this._averageFields[team] = fields;
         }
         var parent:DisplayObjectContainer = team.parent;
         for each(var tf:TextField in fields)
         {
            if(tf.parent != parent)
            {
               parent.addChild(tf);
            }
            tf.visible = team.visible;
         }
         var bounds:Rectangle = team.getBounds(parent);
         var y:Number = Math.round(bounds.y + (bounds.height - HEIGHT) / 2) + IMAGE_RISE;
         var local:Number = parent.globalToLocal(new Point(column[0], 0)).x;
         var badgeWidth:Number = Number(WIDTH.exec(taken[1])[1]);
         var signWidth:Number = fields[1].textWidth;
         var badgeX:Number = rightwards ? local + GAP : local - GAP - badgeWidth;
         var signX:Number = rightwards ? local + GAP + column[1] + SPACE : local - GAP - column[1] - SPACE - signWidth;
         this.setField(fields[0], taken[1], badgeWidth, badgeX, y);
         fields[1].width = signWidth + GUTTER * 2 + 2;
         fields[1].x = Math.round(signX - GUTTER);
         fields[1].y = Math.round(bounds.y + (bounds.height - fields[1].height) / 2);
      }

      private function drawIcons(icons:Object, ids:Array, ally:Boolean) : void
      {
         var count:int = icons != null ? int(icons.length) : 0;
         var team:Array = [];
         for(var i:int = 0; i < count; i++)
         {
            team.push(icons[i]);
         }
         this.placeTeam(team, ids, null, ally, NaN);
      }

      // One team's icons, the ids of their rows in the same order, and
      // whether each row shows (null: all of them). Markers go right of the
      // icons when ally, else left; beside them, or with the middle of the
      // screen given, outside the team's rows. Returns [edge, badges width]
      // of the columns drawn, or null when none is.
      private function placeTeam(icons:Array, ids:Array, shown:Array, ally:Boolean, middle:Number) : Array
      {
         var edge:Number = NaN;
         var badges:Number = 0;
         var drawn:Array = [];
         for(var i:int = 0; i < icons.length; i++)
         {
            var icon:DisplayObject = icons[i] as DisplayObject;
            if(icon == null || icon.parent == null)
            {
               continue;
            }
            var id:* = ids[i];
            var marker:Array = id != null ? this._markers[String(id)] as Array : null;
            var visible:Boolean = marker != null && icon.visible && (shown == null || shown[i]);
            var fields:Array = this.fieldsFor(icon, marker != null);
            if(fields == null)
            {
               continue;
            }
            for each(var tf:TextField in fields)
            {
               tf.visible = visible;
            }
            if(!visible)
            {
               continue;
            }
            // The outer edge in stage space, where rows of one team compare.
            var parent:DisplayObjectContainer = icon.parent;
            var bounds:Rectangle = icon.getBounds(parent);
            var global:Number = parent.localToGlobal(new Point(this.edge(parent, icon, bounds, ally, middle), 0)).x;
            edge = isNaN(edge) ? global : (ally ? Math.max(edge, global) : Math.min(edge, global));
            badges = Math.max(badges, Number(marker[1]));
            drawn.push([icon, marker, fields, bounds]);
         }
         for each(var item:Array in drawn)
         {
            this.placeRow(item[0], item[1], item[2], item[3], edge, badges, ally);
         }
         return drawn.length > 0 ? [edge, badges] : null;
      }

      private function fieldsFor(icon:DisplayObject, create:Boolean) : Array
      {
         var fields:Array = this._fields[icon] as Array;
         if(fields == null)
         {
            if(!create)
            {
               return null;
            }
            fields = [newField(), newField()];
            this._fields[icon] = fields;
         }
         for each(var tf:TextField in fields)
         {
            if(tf.parent != icon.parent)
            {
               icon.parent.addChild(tf);
            }
         }
         return fields;
      }

      private static function newField() : TextField
      {
         var tf:TextField = new TextField();
         tf.selectable = false;
         tf.mouseEnabled = false;
         tf.multiline = false;
         tf.wordWrap = false;
         tf.height = HEIGHT;
         tf.name = NAME;
         return tf;
      }

      private function placeRow(icon:DisplayObject, marker:Array, fields:Array, bounds:Rectangle,
                                edge:Number, badges:Number, ally:Boolean) : void
      {
         var parent:DisplayObjectContainer = icon.parent;
         var local:Number = parent.globalToLocal(new Point(edge, 0)).x;
         var y:Number = Math.round(bounds.y + (bounds.height - HEIGHT) / 2) + IMAGE_RISE;
         var badgeWidth:Number = marker[1];
         var flagsWidth:Number = marker[3];
         // Allies read outwards from the icon, badge then flags; enemies are
         // mirrored, each column hugging the side nearest the icon.
         var badgeX:Number = ally ? local + GAP : local - GAP - badgeWidth;
         var flagsX:Number = ally ? local + GAP + badges + SPACE : local - GAP - badges - SPACE - flagsWidth;
         this.setField(fields[0], marker[0], badgeWidth, badgeX, y);
         this.setField(fields[1], marker[2], flagsWidth, flagsX, y);
      }

      private function setField(tf:TextField, html:String, width:Number, x:Number, y:Number) : void
      {
         if(!html)
         {
            tf.visible = false;
            return;
         }
         if(this._html[tf] != html)
         {
            tf.htmlText = html;
            // htmlText reads back rewritten, so what was set is kept aside.
            this._html[tf] = html;
         }
         tf.width = width + GUTTER * 2 + 2;
         tf.x = Math.round(x - GUTTER);
         tf.y = y;
      }

      // Where a field's text is drawn, in its parent's space, or null when empty.
      private static function textBounds(text:TextField, box:Rectangle) : Rectangle
      {
         if(text.text == null || text.text.length == 0)
         {
            return null;
         }
         var width:Number = Math.min(text.textWidth + 4, box.width);
         var align:String = text.getTextFormat().align;
         var left:Number = box.left;
         if(align == TextFormatAlign.RIGHT)
         {
            left = box.right - width;
         }
         else if(align == TextFormatAlign.CENTER)
         {
            left = box.left + (box.width - width) / 2;
         }
         return new Rectangle(left, box.top, width, box.height);
      }

      // The outer edge of the icon and of every visible neighbour beyond it,
      // on the markers' side and across the icon's middle. With the middle of
      // the screen given, every neighbour on the icon's half counts: the edge
      // of the whole row.
      private function edge(parent:DisplayObjectContainer, icon:DisplayObject, bounds:Rectangle, ally:Boolean, screenMiddle:Number) : Number
      {
         var edge:Number = ally ? bounds.right : bounds.left;
         var middle:Number = bounds.y + bounds.height / 2;
         var half:Number = isNaN(screenMiddle) ? NaN : parent.globalToLocal(new Point(screenMiddle, 0)).x;
         for(var i:int = 0; i < parent.numChildren; i++)
         {
            var child:DisplayObject = parent.getChildAt(i);
            if(child == icon || !child.visible || child.alpha == 0 || child.name == NAME || BACKGROUND.test(child.name))
            {
               continue;
            }
            var other:Rectangle = child.getBounds(parent);
            if(other.width <= 0 || other.width > MAX_NEIGHBOUR_WIDTH || other.top > middle || other.bottom < middle)
            {
               continue;
            }
            var text:TextField = child as TextField;
            if(text != null)
            {
               // A text field is often wider than its text and set over the
               // icon, so only the text itself counts, wherever it starts.
               other = textBounds(text, other);
               if(other == null)
               {
                  continue;
               }
            }
            if(!isNaN(half))
            {
               var side:Number = other.x + other.width / 2;
               if(ally && side > half && other.right > edge)
               {
                  edge = other.right;
               }
               else if(!ally && side < half && other.left < edge)
               {
                  edge = other.left;
               }
            }
            else if(text != null)
            {
               if(ally && other.right > edge)
               {
                  edge = other.right;
               }
               else if(!ally && other.left < edge)
               {
                  edge = other.left;
               }
            }
            else if(ally && other.left >= bounds.right - 2 && other.right > edge)
            {
               edge = other.right;
            }
            else if(!ally && other.right <= bounds.left + 2 && other.left < edge)
            {
               edge = other.left;
            }
         }
         return edge;
      }
   }
}
