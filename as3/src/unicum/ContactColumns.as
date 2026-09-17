package unicum
{
   import flash.display.DisplayObject;
   import flash.display.DisplayObjectContainer;
   import flash.display.Sprite;
   import flash.events.Event;
   import flash.text.TextField;
   import flash.text.TextFieldAutoSize;
   import flash.utils.Dictionary;
   import net.wg.gui.messenger.controls.ContactAttributesGroup;
   import net.wg.gui.messenger.controls.ContactItem;
   import net.wg.gui.messenger.data.ContactItemVO;
   import net.wg.gui.messenger.data.ContactUserPropVO;
   import net.wg.infrastructure.interfaces.IUserProps;

   // The contacts list's flags and rating, pinned to the right of each row
   // rather than after the name, so the name keeps the row's width.
   //
   // A row is the client's ContactItem, which draws name, clan and region in
   // one TextField, shortened by App.utils.commons.formatPlayerName to the
   // row's width, with the icons group (ignored, notes...) right after it.
   // Python (src/unicum/lobby.py) leaves the markup out of the region while
   // this view is loaded and hands it here instead, in markersText, one
   // contact a line: "dbID TAB markup". Each row gets a TextField of ours, a
   // child of the row, so it scrolls and is recycled with it, at the row's
   // right edge; and whenever the client has laid the row out, the name is
   // laid out again the client's way (ContactItem.applyLayout) with that
   // column's width taken off, so it never runs under the images.
   //
   // Part of LobbyView. Rows are found as TitleHtml and RoomTools find theirs:
   // every added object searched down to MAX_DEPTH, once.
   public class ContactColumns
   {
      private static const MAX_DEPTH:int = 16;

      // Between the name's column and ours, and ours and the row's edge.
      private static const GAP:int = 6;

      private static const EDGE:int = 4;

      // How far below the name's middle the field goes. In battle
      // (VehicleMarkers) it takes 2px to centre the images; in a contact row
      // that drew them a little low, so none here.
      private static const IMAGE_RISE:int = 0;

      private static const NAME:String = "unicumContactMarkers";

      private var _host:Sprite;

      private var _searched:Dictionary = new Dictionary(true);

      // row -> [our field, the markup on it, the name's htmlText and width once laid out]
      private var _rows:Dictionary = new Dictionary(true);

      private var _markersText:String = null;

      private var _markers:Object = {};

      public function ContactColumns(host:Sprite)
      {
         this._host = host;
         App.stage.addEventListener(Event.ADDED, this.onAdded, true, 0, true);
         host.addEventListener(Event.ENTER_FRAME, this.onFrame);
         // Rows already on screen when this view loads, after a hot reload.
         this.search(App.stage, 0);
      }

      public function get markersText() : String
      {
         return this._markersText;
      }

      public function set markersText(value:String) : void
      {
         if(value == this._markersText)
         {
            return;
         }
         this._markersText = value;
         this._markers = {};
         for each(var line:String in (value || "").split("\n"))
         {
            var tab:int = line.indexOf("\t");
            if(tab > 0)
            {
               this._markers[line.substring(0, tab)] = line.substring(tab + 1);
            }
         }
      }

      public function dispose() : void
      {
         App.stage.removeEventListener(Event.ADDED, this.onAdded, true);
         this._host.removeEventListener(Event.ENTER_FRAME, this.onFrame);
         for(var key:Object in this._rows)
         {
            var row:ContactItem = key as ContactItem;
            var field:TextField = this._rows[key][0] as TextField;
            if(field != null && field.parent != null)
            {
               field.parent.removeChild(field);
            }
            // The client's own layout again, at the row's full width.
            if(row != null && row.data != null && row.textField != null)
            {
               try
               {
                  row.applyLayout();
               }
               catch(e:Error)
               {
               }
            }
         }
         this._rows = new Dictionary(true);
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
         if(target is ContactItem)
         {
            if(this._rows[target] == null)
            {
               this._rows[target] = [null, null, null];
            }
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

      private function onFrame(event:Event) : void
      {
         for(var key:Object in this._rows)
         {
            var row:ContactItem = key as ContactItem;
            if(row == null || row.stage == null)
            {
               // Closed with its list: searched again when shown again.
               delete this._searched[key];
               delete this._rows[key];
               continue;
            }
            try
            {
               this.draw(row, this._rows[key] as Array);
            }
            catch(e:Error)
            {
               // A row the client is tearing down; the next frame decides.
            }
         }
      }

      private function draw(row:ContactItem, state:Array) : void
      {
         var vo:ContactItemVO = row.data;
         var name:TextField = row.textField;
         if(vo == null || name == null)
         {
            return;
         }
         var markup:String = this._markers[String(vo.dbID)] as String;
         var field:TextField = state[0] as TextField;
         if(!markup)
         {
            if(field != null && field.visible)
            {
               field.visible = false;
               // Give the name its full width back.
               row.applyLayout();
               state[2] = null;
            }
            return;
         }
         if(field == null)
         {
            field = new TextField();
            field.name = NAME;
            field.selectable = false;
            field.mouseEnabled = false;
            field.multiline = false;
            field.wordWrap = false;
            field.autoSize = TextFieldAutoSize.LEFT;
            state[0] = field;
         }
         if(field.parent != row)
         {
            row.addChild(field);
         }
         if(state[1] != markup)
         {
            field.htmlText = markup;
            state[1] = markup;
            state[2] = null;
         }
         field.visible = true;
         field.x = Math.round(row.width - EDGE - field.width);
         field.y = Math.round(name.y + (name.height - field.height) / 2) + IMAGE_RISE;
         // The client lays the name out again on new data and when its icons
         // load; its text or width then differ from what was left here.
         var laid:String = name.htmlText + "|" + name.width;
         if(state[2] != laid)
         {
            this.layOut(row, name, field);
            state[2] = name.htmlText + "|" + name.width;
         }
      }

      // ContactItem.applyLayout, with our column's width taken off the name's.
      private function layOut(row:ContactItem, name:TextField, column:TextField) : void
      {
         var props:ContactUserPropVO = row.data.userPropsVO;
         var user:IUserProps = App.utils.commons.getUserProps(props.userName, props.clanAbbrev, props.region, 0, []);
         user.rgb = props.rgb;
         var group:DisplayObject = null;
         for(var i:int = 0; i < row.numChildren; i++)
         {
            if(row.getChildAt(i) is ContactAttributesGroup)
            {
               group = row.getChildAt(i);
            }
         }
         var groupWidth:Number = group != null ? group.width : 0;
         name.autoSize = TextFieldAutoSize.NONE;
         name.width = Math.max(0, column.x - GAP - name.x - groupWidth);
         App.utils.commons.formatPlayerName(name, user);
         name.autoSize = TextFieldAutoSize.LEFT;
         if(group != null)
         {
            group.x = int(name.x + name.width);
         }
      }
   }
}
