package unicum.settings
{
   import flash.display.DisplayObject;
   import flash.display.DisplayObjectContainer;
   import flash.display.Sprite;
   import flash.events.Event;
   import flash.events.MouseEvent;
   import flash.text.TextField;
   import flash.text.TextFieldAutoSize;
   import flash.system.ApplicationDomain;
   import flash.utils.getQualifiedClassName;
   import scaleform.clik.data.DataProvider;
   import scaleform.clik.events.ButtonEvent;
   import scaleform.clik.events.IndexEvent;
   import scaleform.clik.events.ListEvent;

   // What the unicum.gg tab of the settings window shows, loaded by the
   // unicum.SettingsTab shell into a domain of its own each time the tab is
   // made, so a new build shows the next time the window opens.
   //
   // The page comes from Python (src/unicum/settings_window.py, native_page),
   // a line an item: sub-tabs, framed groups in two columns, and in them
   // dropdowns, checkboxes, text and a button. Drawn with the game's own
   // controls, taken from its libraries by name: ButtonBarEx and its tab
   // button for the sub-tabs (as Battle Notifications has), FieldSet for the
   // sections (as General has), DropdownMenuUI, CheckBox, ButtonNormal.
   //
   // A change waits for the window's Apply or OK, as the window's own settings
   // do, and lights Apply up; Cancel or the cross drop it. Committed, each goes
   // to Python through the shell's send; a button at once.
   public class SettingsTabView extends Sprite
   {
      // The General tab's own measures (SettingsWindow, GameSettings): the
      // content 802x522 on the window's background, a section 390 wide, the
      // columns at 0 and 388, a checkbox every 28 at 22 in, a dropdown under
      // its label every 45, 180 wide, the labels $TextFont 12 in #969687.
      private static const WIDTH:int = 802;

      private static const HEIGHT:int = 522;

      private static const SECTION_WIDTH:int = 390;

      private static const COLUMN_X:Array = [0, 388];

      // Where the General tab's ground lies, measured in the client: x 10 to
      // 788, y 19 down. Here it starts under the sub-tabs instead.
      private static const GROUND_LEFT:int = 10;

      private static const GROUND_RIGHT:int = 788;

      private static const GROUND_BOTTOM:int = 511;

      private static const GROUND_TOP:int = 19;

      private static const INSET:int = 22;

      private static const SECTION_TOP:int = 28;

      private static const SECTION_BOTTOM:int = 22;

      private static const CHECKBOX_ROW:int = 28;

      private static const DROPDOWN_ROW:int = 45;

      private static const DROPDOWN_WIDTH:int = 180;

      // The first section, as General has it, under the sub-tabs' 22.
      private static const PAGE_TOP:int = 13;

      private static const SUB_TABS_HEIGHT:int = 22;

      private static const LABEL_FONT:String = "$TextFont";

      private static const LABEL_COLOR:String = "#969687";

      private static const LABEL_SIZE:int = 12;

      // The game's tab buttons, the first its library has.
      private static const TAB_BUTTONS:Array = ["SmallTabButton", "TabButtonUI"];

      private var _shell:Object;

      private var _window:Object;

      private var _bar:Object;

      // The page the sections are drawn on, and the General tab's scroll pane holding it.
      private var _content:Sprite;

      private var _pane:Object;

      public function SettingsTabView()
      {
         super();
      }

      // --- the shell's calls ------------------------------------------------

      public function start(shell:Object) : void
      {
         this._shell = shell;
         if(this.memory.pending == null)
         {
            this.memory.pending = {};
         }
         this.hookWindow();
         this.hideOthers(true);
         this.takeGround();
         this.build();
         if(_ground == null)
         {
            // The General tab is not always in the window's stack yet when
            // this one is built first: its ground is waited for, and the page
            // drawn again on it once it is there.
            this._tries = 60;
            addEventListener(Event.ENTER_FRAME, this.onGround);
         }
      }

      private var _tries:int = 0;

      private function onGround(event:Event) : void
      {
         this.takeGround();
         if(_ground == null && this._tries-- > 0)
         {
            return;
         }
         removeEventListener(Event.ENTER_FRAME, this.onGround);
         if(_ground != null)
         {
            this.build();
         }
      }

      private var _logged:int = 0;

      private function log(text:String) : void
      {
         if(this._logged++ < 250)
         {
            this._shell.send("log\tl\t" + text.split("\t").join(" ").split("\n").join(" "));
         }
      }

      // The General tab, wherever the window keeps it: a sibling of this tab
      // in the window's view stack.
      private function nativeTab() : DisplayObject
      {
         var places:Array = [DisplayObject(this._shell).parent];
         var stack:DisplayObjectContainer = this._window != null ? this._window.view as DisplayObjectContainer : null;
         if(stack != null)
         {
            for(var k:int = 0; k < stack.numChildren; k++)
            {
               places.push(stack.getChildAt(k) as DisplayObjectContainer);
            }
         }
         for each(var container:DisplayObjectContainer in places)
         {
            if(container == null)
            {
               continue;
            }
            for(var i:int = 0; i < container.numChildren; i++)
            {
               var child:DisplayObject = container.getChildAt(i);
               if(getQualifiedClassName(child) == "GameSettings")
               {
                  return child;
               }
            }
         }
         return null;
      }

      // The ground under the General tab, copied from the tab itself the first
      // time this one is built, and kept for the client's life.
      private function takeGround() : void
      {
         if(_ground != null)
         {
            return;
         }
         var view:DisplayObject = this.nativeTab();
         if(view == null)
         {
            // The window's stack only holds the tab it shows, so coming
            // straight to this one leaves no General tab to copy: one is made
            // from the window's own library instead, and thrown away after.
            view = this.makeNativeTab();
            if(view == null)
            {
               return;
            }
            this.shootGround(view);
            return;
         }
         var was:Boolean = view.visible;
         view.visible = true;
         this.shootGround(view);
         view.visible = was;
      }

      private function makeNativeTab() : DisplayObject
      {
         try
         {
            var domain:ApplicationDomain = DisplayObject(this._window).loaderInfo.applicationDomain;
            var made:Class = domain.getDefinition("GameSettings") as Class;
            return new made() as DisplayObject;
         }
         catch(e:Error)
         {
            this.log("no General tab to copy the ground from: " + e);
         }
         return null;
      }

      public function update() : void
      {
         this.build();
      }

      public function stop() : void
      {
         this.hideOthers(false);
         this.unhookWindow();
         removeEventListener(Event.ENTER_FRAME, this.onGround);
         removeEventListener(Event.ENTER_FRAME, this.onRebuild);
         // Closed without Apply or OK: what was changed is dropped.
         this.memory.pending = {};
         this.clear();
         this._shell = null;
      }

      // The window leaves the tab shown before this one on screen, above it:
      // the others are hidden while this one shows, and shown again after.
      private function hideOthers(hidden:Boolean) : void
      {
         var shell:DisplayObject = DisplayObject(this._shell);
         var container:DisplayObjectContainer = shell.parent;
         if(container == null)
         {
            return;
         }
         for(var i:int = 0; i < container.numChildren; i++)
         {
            var child:DisplayObject = container.getChildAt(i);
            if(child != shell)
            {
               child.visible = !hidden;
            }
         }
      }

      private function get memory() : Object
      {
         return this._shell != null ? this._shell.memory : {};
      }

      // --- the window's buttons ---------------------------------------------

      private function hookWindow() : void
      {
         var parent:DisplayObjectContainer = DisplayObject(this._shell).parent;
         while(parent != null && !parent.hasOwnProperty("submitBtn"))
         {
            parent = parent.parent;
         }
         this._window = parent;
         if(this._window == null)
         {
            return;
         }
         // Before the window's own handlers: OK closes the window. The game's
         // buttons say buttonClick, not click (SettingsWindow, ButtonEvent).
         for each(var button:Object in [this._window.submitBtn, this._window.applyBtn])
         {
            if(button != null)
            {
               button.addEventListener(ButtonEvent.CLICK, this.onCommit, false, 100);
            }
         }
      }

      private function unhookWindow() : void
      {
         if(this._window == null)
         {
            return;
         }
         for each(var button:Object in [this._window.submitBtn, this._window.applyBtn])
         {
            if(button != null)
            {
               button.removeEventListener(ButtonEvent.CLICK, this.onCommit);
            }
         }
         this._window = null;
      }

      private function onCommit(event:Event) : void
      {
         var pending:Object = this.memory.pending;
         for(var key:String in pending)
         {
            this._shell.send(key + "	" + pending[key]);
         }
         this.memory.pending = {};
         // The window shows its own tab again once the settings come back.
         // A shell of an older build has no hold: the window's own handler
         // must still run after this one.
         try
         {
            this._shell.hold();
         }
         catch(e:Error)
         {
         }
      }

      private function change(key:String, kind:String, value:String) : void
      {
         this.memory.pending[key] = kind + "	" + value;
         if(this._window != null && this._window.applyBtn != null)
         {
            this._window.applyBtn.enabled = true;
         }
      }

      private function pending(key:String) : String
      {
         var value:String = this.memory.pending[key];
         return value != null ? value.split("	")[1] : null;
      }

      // --- drawing ------------------------------------------------------------

      private function clear() : void
      {
         if(this._bar != null)
         {
            try
            {
               this._bar.removeEventListener(IndexEvent.INDEX_CHANGE, this.onSubTab);
            }
            catch(e:Error)
            {
            }
            this._bar = null;
         }
         if(this._pane != null)
         {
            try
            {
               this._pane.target = null;
            }
            catch(e:Error)
            {
            }
            this._pane = null;
         }
         while(this._content != null && this._content.numChildren > 0)
         {
            var item:DisplayObject = this._content.removeChildAt(0);
            try
            {
               Object(item).dispose();
            }
            catch(e:Error)
            {
            }
         }
         while(numChildren > 0)
         {
            var child:DisplayObject = removeChildAt(0);
            try
            {
               Object(child).dispose();
            }
            catch(e:Error)
            {
            }
         }
      }

      private function build() : void
      {
         if(this._shell == null)
         {
            return;
         }
         this.clear();
         var tabs:Array = [];
         var current:Object = null;
         for each(var line:String in String(this._shell.page).split("\n"))
         {
            var fields:Array = line.split("\t");
            if(fields[0] == "tab")
            {
               current = {"label":fields[1], "items":[]};
               tabs.push(current);
            }
            else if(current != null && line.length > 0)
            {
               current.items.push(fields);
            }
         }
         if(tabs.length == 0)
         {
            return;
         }
         var index:int = int(this.memory.subTab);
         if(index < 0 || index >= tabs.length)
         {
            index = 0;
         }
         this.drawSubTabs(tabs, index);
         this._content = new Sprite();
         this.drawItems(tabs[index].items);
         this.drawPane();
      }

      // Battle Notifications' own sub-tabs: a ButtonBarEx of SmallTabButton at
      // 2,0, 22 high, each button as wide as its label.
      private function drawSubTabs(tabs:Array, selected:int) : void
      {
         var labels:Array = [];
         for each(var tab:Object in tabs)
         {
            labels.push({"label":tab.label});
         }
         try
         {
            var bar:Object = App.utils.classFactory.getComponent("ButtonBarEx", DisplayObject);
            bar.itemRendererName = "SmallTabButton";
            bar.autoSize = TextFieldAutoSize.LEFT;
            bar.paddingHorizontal = 12;
            // Its size first: a bar lays out only the buttons its own width
            // holds, and drops the rest (ButtonBar.updateRenderers). Placed in
            // the editor, the game's bars have one; made here, it is 0.
            bar.width = WIDTH - 4;
            bar.height = SUB_TABS_HEIGHT;
            bar.dataProvider = new DataProvider(labels);
            bar.selectedIndex = selected;
            bar.x = 2;
            bar.y = 0;
            addChild(DisplayObject(bar));
            bar.validateNow();
            bar.addEventListener(IndexEvent.INDEX_CHANGE, this.onSubTab);
            this._bar = bar;
            return;
         }
         catch(e:Error)
         {
            this.log("no sub-tab bar: " + e);
         }
         // Without the game's tab bar, a line of text links.
         var x:int = 4;
         for(var i:int = 0; i < labels.length; i++)
         {
            var link:TextField = this.text(labels[i].label, i == selected ? "#F5F0E6" : LABEL_COLOR, 13, "$FieldFont");
            link.x = x;
            link.mouseEnabled = true;
            link.name = String(i);
            link.addEventListener(MouseEvent.CLICK, this.onSubTabText);
            addChild(link);
            x += link.width + 24;
         }
      }

      // The page under the sub-tabs, on the window's own background. Not in
      // the General tab's scroll pane: that symbol carries the General tab's
      // own controls with it, and drew them over this page.
      private function drawPane() : void
      {
         this.background();
         this._content.y = SUB_TABS_HEIGHT;
         addChild(this._content);
      }

      private function onSubTab(event:Object) : void
      {
         var index:int = this._bar != null ? int(this._bar.selectedIndex) : 0;
         if(index != int(this.memory.subTab) && index >= 0)
         {
            this.memory.subTab = index;
            // Later: the bar is still dispatching.
            addEventListener(Event.ENTER_FRAME, this.onRebuild);
         }
      }

      private function onSubTabText(event:MouseEvent) : void
      {
         this.memory.subTab = int(TextField(event.currentTarget).name);
         addEventListener(Event.ENTER_FRAME, this.onRebuild);
      }

      private function onRebuild(event:Event) : void
      {
         removeEventListener(Event.ENTER_FRAME, this.onRebuild);
         this.build();
      }

      // The ground the General tab is drawn on, read from it in the client:
      // #17150F over the whole content, a shade lighter towards the middle.
      // Its own symbol cannot be borrowed, it carries the General tab's
      // controls with it, so the same ground is painted here.
      private static const GROUND:uint = 0x17150F;

      private static const GROUND_MIDDLE:uint = 0x181610;

      // The General tab's ground, taken from the tab itself with its controls
      // hidden for the shot: its art is drawn in the editor, not in code, so
      // it cannot be redrawn here, only copied. Kept for the window's life.
      private static var _ground:flash.display.BitmapData = null;

      private function shootGround(view:DisplayObject) : void
      {
         var hidden:Array = [];
         try
         {
            this.hideControls(DisplayObjectContainer(view), hidden, 0);
            // Clear, not black: what the General tab never draws must stay
            // empty here too, so the window's own frame shows through it.
            var shot:flash.display.BitmapData = new flash.display.BitmapData(WIDTH, HEIGHT, true, 0);
            shot.draw(view);
            _ground = shot;
            this.log("ground taken, " + hidden.length + " controls hidden");
         }
         catch(e:Error)
         {
            this.log("could not take the ground: " + e);
         }
         for each(var shown:DisplayObject in hidden)
         {
            shown.visible = true;
         }
      }

      // Everything the General tab draws on its ground: its sections, its
      // controls, its scroll bar. What is left is the ground alone.
      private function hideControls(container:DisplayObjectContainer, hidden:Array, depth:int) : void
      {
         if(depth > 4)
         {
            return;
         }
         for(var i:int = 0; i < container.numChildren; i++)
         {
            var child:DisplayObject = container.getChildAt(i);
            var name:String = getQualifiedClassName(child);
            if(/FieldSet|CheckBox|Dropdown|Label|ScrollBar|Button|TextField|Content/.test(name))
            {
               if(child.visible)
               {
                  child.visible = false;
                  hidden.push(child);
               }
               continue;
            }
            if(child is DisplayObjectContainer)
            {
               this.hideControls(DisplayObjectContainer(child), hidden, depth + 1);
            }
         }
      }

      private function background() : void
      {
         if(_ground != null)
         {
            // As it was taken, not stretched, and starting under the sub-tabs
            // rather than behind them: its first row of ground falls on the
            // row below the bar, as Battle Notifications has it, and nothing
            // of it is drawn above. What it never drew stays clear, so the
            // window's own frame shows through it.
            var picture:flash.display.Bitmap = new flash.display.Bitmap(_ground);
            picture.y = SUB_TABS_HEIGHT - GROUND_TOP - 1;
            var clip:Sprite = new Sprite();
            clip.graphics.beginFill(0);
            clip.graphics.drawRect(0, SUB_TABS_HEIGHT, WIDTH, HEIGHT - SUB_TABS_HEIGHT);
            clip.graphics.endFill();
            addChildAt(picture, 0);
            addChildAt(clip, 1);
            picture.mask = clip;
            return;
         }
         var width:int = GROUND_RIGHT - GROUND_LEFT + 1;
         var height:int = GROUND_BOTTOM - SUB_TABS_HEIGHT + 1;
         var ground:Sprite = new Sprite();
         ground.graphics.beginFill(GROUND);
         ground.graphics.drawRect(GROUND_LEFT, SUB_TABS_HEIGHT, width, height);
         ground.graphics.endFill();
         ground.graphics.beginFill(GROUND_MIDDLE);
         ground.graphics.drawRect(GROUND_LEFT + 60, SUB_TABS_HEIGHT + 40, width - 120, height - 100);
         ground.graphics.endFill();
         ground.mouseEnabled = false;
         addChildAt(ground, 0);
      }

      private static function rowHeight(fields:Array) : int
      {
         return fields[0] == "dropdown" ? DROPDOWN_ROW : CHECKBOX_ROW;
      }

      private function drawItems(items:Array) : void
      {
         var tops:Array = [PAGE_TOP, PAGE_TOP];
         var groups:Array = [];
         var group:Array = null;
         for each(var fields:Array in items)
         {
            if(fields[0] == "group")
            {
               group = [int(fields[1]), fields[2], []];
               groups.push(group);
            }
            else if(group != null)
            {
               group[2].push(fields);
            }
         }
         for each(group in groups)
         {
            var column:int = group[0] == 1 ? 1 : 0;
            var x:int = COLUMN_X[column];
            var height:int = SECTION_TOP + SECTION_BOTTOM;
            for each(fields in group[2])
            {
               height += rowHeight(fields);
            }
            this.frame(group[1], x, tops[column], SECTION_WIDTH, height);
            var y:int = tops[column] + SECTION_TOP;
            for each(fields in group[2])
            {
               this.item(fields, x + INSET, y);
               y += rowHeight(fields);
            }
            tops[column] += height;
         }
      }

      private function frame(title:String, x:int, y:int, width:int, height:int) : void
      {
         var fieldSet:Object = App.utils.classFactory.getComponent("FieldSet", DisplayObject);
         fieldSet.label = title;
         fieldSet.x = x;
         fieldSet.y = y;
         fieldSet.width = width;
         fieldSet.height = height;
         this._content.addChild(DisplayObject(fieldSet));
      }

      private function item(fields:Array, x:int, y:int) : void
      {
         var kind:String = fields[0];
         if(kind == "dropdown")
         {
            this.label(fields[2], x + 3, y - 2);
            this.dropdown(fields[1], int(fields[3]), int(fields[4]), String(fields[5]).split("|"), x + 1, y + 13);
         }
         else if(kind == "checkbox")
         {
            this.checkbox(fields[1], fields[2], fields[3] == "1", x, y);
         }
         else if(kind == "text")
         {
            this.label(fields[1], x + 3, y + 1);
         }
         else if(kind == "button")
         {
            this.label(fields[2], x + 3, y + 1);
            this.button(fields[1], fields[3], x + SECTION_WIDTH - 2 * INSET - 110, y - 2);
         }
      }

      private function text(value:String, color:String, size:int, font:String = "$TextFont") : TextField
      {
         var field:TextField = new TextField();
         field.autoSize = TextFieldAutoSize.LEFT;
         field.selectable = false;
         field.mouseEnabled = false;
         field.htmlText = "<font face='" + font + "' size='" + size + "' color='" + color + "'>" +
                          value.split("&").join("&amp;").split("<").join("&lt;") + "</font>";
         return field;
      }

      private function label(value:String, x:int, y:int) : void
      {
         var field:TextField = this.text(value, LABEL_COLOR, LABEL_SIZE, LABEL_FONT);
         field.x = x;
         field.y = y;
         this._content.addChild(field);
      }

      private function dropdown(key:String, selected:int, offset:int, options:Array, x:int, y:int) : void
      {
         var wanted:String = this.pending(key);
         if(wanted != null)
         {
            selected = int(wanted) - offset;
         }
         var list:Array = [];
         for each(var option:String in options)
         {
            list.push({"label":option});
         }
         var menu:Object = App.utils.classFactory.getComponent("DropdownMenuUI", DisplayObject);
         menu.dropdown = "DropdownMenu_ScrollingList";
         menu.itemRenderer = "DropDownListItemRendererSound";
         menu.dataProvider = new DataProvider(list);
         menu.menuRowCount = list.length;
         menu.selectedIndex = selected;
         menu.x = x;
         menu.y = y;
         menu.width = DROPDOWN_WIDTH;
         var self:SettingsTabView = this;
         menu.addEventListener(ListEvent.INDEX_CHANGE, function(event:Object):void
         {
            self.change(key, "d", String(int(event.target.selectedIndex) + offset));
         });
         this._content.addChild(DisplayObject(menu));
         menu.validateNow();
      }

      private function checkbox(key:String, title:String, selected:Boolean, x:int, y:int) : void
      {
         var wanted:String = this.pending(key);
         if(wanted != null)
         {
            selected = wanted == "1";
         }
         var box:Object = App.utils.classFactory.getComponent("CheckBox", DisplayObject);
         box.label = title;
         box.selected = selected;
         box.x = x;
         box.y = y;
         box.width = 350;
         var self:SettingsTabView = this;
         box.addEventListener(Event.SELECT, function(event:Event):void
         {
            self.change(key, "c", event.target.selected ? "1" : "0");
         });
         this._content.addChild(DisplayObject(box));
         box.validateNow();
      }

      private function button(key:String, title:String, x:int, y:int) : void
      {
         var button:Object = App.utils.classFactory.getComponent("ButtonNormal", DisplayObject);
         button.label = title;
         button.x = x;
         button.y = y;
         button.width = 110;
         var self:SettingsTabView = this;
         // buttonClick, not click: the game's buttons say so (ButtonEvent).
         button.addEventListener(ButtonEvent.CLICK, function(event:Event):void
         {
            self._shell.send(key + "\tb\t1");
         });
         this._content.addChild(DisplayObject(button));
         button.validateNow();
      }
   }
}
