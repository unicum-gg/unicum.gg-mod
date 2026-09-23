package unicum
{
   import flash.display.Bitmap;
   import flash.display.BitmapData;
   import flash.display.Loader;
   import flash.display.Sprite;
   import flash.events.Event;
   import flash.events.IOErrorEvent;
   import flash.external.ExternalInterface;
   import flash.geom.Rectangle;
   import flash.net.URLRequest;
   import flash.text.TextField;
   import flash.text.TextFieldAutoSize;
   import flash.text.TextFormat;
   import flash.text.TextFormatAlign;
   import flash.utils.Dictionary;

   // One vehicle's rating badge and flags, right of the player's name in the
   // client's marker above that vehicle, added to that marker by
   // unicum.markers.NameMarkerAddon. Lives in unicum.markers.swf, reloaded
   // while the battle runs.
   //
   // The images are the PNGs the players panel shows, loaded with a Loader:
   // the way the client's own code in this movie loads its images. Until they
   // are all in, or if one cannot load, the same rating and flags show as
   // text instead.
   public class NameMarkerView extends Sprite
   {
      private static const GAP:int = 6;

      // A resource path under gui/ as a URL: relative to gui/flash, where the
      // client's markers movie loads its own files from.
      private static const PREFIX:String = "../";

      // Python writes what comes through here to game.log.
      private static const LOG_CALLBACK:String = "unicum.markers.ready";

      // resource path -> BitmapData, or an Array of views waiting for it, or
      // false once it failed. Shared by every marker of this SWF.
      private static var _images:Dictionary = new Dictionary();

      private static var _logged:Object = {};

      private var _label:TextField;

      // Drawn under the label, in black, one pixel across: the shadow.
      private var _shadow:TextField;

      private static const SHADOW_OFFSET:int = 1;

      private var _row:Sprite;

      private var _anchor:TextField = null;

      private var _wanted:Array = [];

      public function NameMarkerView()
      {
         super();
         mouseEnabled = false;
         mouseChildren = false;
         this._label = new TextField();
         this._label.selectable = false;
         this._label.mouseEnabled = false;
         this._label.autoSize = TextFieldAutoSize.LEFT;
         // Its shadow is a second field behind it, not a filter: a filter on
         // something that moves is rasterised again every frame, and a marker
         // moves with its vehicle. Thirty of them cost about twenty frames a
         // second, measured in battle.
         this._shadow = new TextField();
         this._shadow.selectable = false;
         this._shadow.mouseEnabled = false;
         this._shadow.autoSize = TextFieldAutoSize.LEFT;
         addChild(this._shadow);
         addChild(this._label);
         this._row = new Sprite();
         addChild(this._row);
      }

      private static function log(message:String) : void
      {
         if(_logged[message])
         {
            return;
         }
         _logged[message] = true;
         try
         {
            if(ExternalInterface.available)
            {
               ExternalInterface.call(LOG_CALLBACK, message);
            }
         }
         catch(e:Error)
         {
         }
      }

      // The marker's player name field, which the rating follows.
      public function setAnchor(field:TextField) : void
      {
         this._anchor = field;
         this.layout();
      }

      // text: the fallback; color: its RGB. images: "path|width|height|space
      // after" joined by ";", in the order they are drawn.
      public function setData(text:String, color:Number, images:String = "") : void
      {
         var format:TextFormat = this._anchor != null ? this._anchor.getTextFormat() : new TextFormat("$FieldFont", 14);
         format.color = uint(color);
         format.align = TextFormatAlign.LEFT;
         this._label.defaultTextFormat = format;
         this._label.text = text;
         var shadow:TextFormat = new TextFormat(format.font, format.size, 0x000000);
         shadow.align = TextFormatAlign.LEFT;
         shadow.bold = format.bold;
         this._shadow.defaultTextFormat = shadow;
         this._shadow.text = text;
         this._wanted = [];
         for each(var part:String in (images || "").split(";"))
         {
            var fields:Array = part.split("|");
            if(fields.length == 4)
            {
               this._wanted.push({"path":fields[0], "width":Number(fields[1]), "height":Number(fields[2]), "space":Number(fields[3])});
               this.request(fields[0]);
            }
         }
         this.drawRow();
      }

      private function request(path:String) : void
      {
         var known:* = _images[path];
         if(known is BitmapData || known === false)
         {
            return;
         }
         if(known is Array)
         {
            if((known as Array).indexOf(this) < 0)
            {
               (known as Array).push(this);
            }
            return;
         }
         _images[path] = [this];
         load(path);
      }

      private static function load(path:String) : void
      {
         var url:String = PREFIX + path.replace(/^gui\//, "");
         var loader:Loader = new Loader();
         var done:Function = function(event:Event) : void
         {
            loader.contentLoaderInfo.removeEventListener(Event.COMPLETE, done);
            loader.contentLoaderInfo.removeEventListener(IOErrorEvent.IO_ERROR, done);
            var bitmap:Bitmap = event is IOErrorEvent ? null : loader.content as Bitmap;
            var waiting:Array = _images[path] as Array;
            _images[path] = bitmap != null ? bitmap.bitmapData : false;
            if(bitmap == null)
            {
               log("cannot load " + url);
            }
            for each(var view:NameMarkerView in waiting)
            {
               view.drawRow();
            }
         };
         loader.contentLoaderInfo.addEventListener(Event.COMPLETE, done);
         loader.contentLoaderInfo.addEventListener(IOErrorEvent.IO_ERROR, done);
         try
         {
            loader.load(new URLRequest(url));
         }
         catch(e:Error)
         {
            done(new IOErrorEvent(IOErrorEvent.IO_ERROR, false, false, e.message));
         }
      }

      // The images once they are all in; the text meanwhile, or for good if
      // one of them cannot load.
      private function drawRow() : void
      {
         while(this._row.numChildren > 0)
         {
            this._row.removeChildAt(0);
         }
         var ready:Boolean = this._wanted.length > 0;
         for each(var image:Object in this._wanted)
         {
            if(!(_images[image.path] is BitmapData))
            {
               ready = false;
               break;
            }
         }
         this._row.visible = ready;
         this._label.visible = !ready;
         this._shadow.visible = !ready;
         if(ready)
         {
            var x:Number = 0;
            for(var i:int = 0; i < this._wanted.length; i++)
            {
               image = this._wanted[i];
               var bitmap:Bitmap = new Bitmap(_images[image.path] as BitmapData);
               bitmap.smoothing = true;
               bitmap.width = image.width;
               bitmap.height = image.height;
               bitmap.x = x;
               bitmap.y = -image.height / 2;
               this._row.addChild(bitmap);
               x += image.width + image.space;
            }
         }
         this.layout();
      }

      // Right of the name as drawn, centred on its line; hidden with it.
      public function layout() : void
      {
         var field:TextField = this._anchor;
         if(field == null || field.parent == null || this.parent == null)
         {
            visible = false;
            return;
         }
         visible = field.visible && (this._row.visible || this._label.text != "");
         if(!visible)
         {
            return;
         }
         var box:Rectangle = field.getBounds(this.parent);
         var width:Number = Math.min(field.textWidth + 4, box.width);
         var align:String = field.getTextFormat().align;
         var right:Number = box.left + width;
         if(align == TextFormatAlign.RIGHT)
         {
            right = box.right;
         }
         else if(align == TextFormatAlign.CENTER)
         {
            right = box.left + (box.width + width) / 2;
         }
         var middle:Number = box.top + box.height / 2;
         x = Math.round(right + GAP);
         y = Math.round(middle);
         this._label.y = Math.round(-this._label.height / 2);
         this._shadow.x = this._label.x + SHADOW_OFFSET;
         this._shadow.y = this._label.y + SHADOW_OFFSET;
         this._row.y = 0;
      }
   }
}
