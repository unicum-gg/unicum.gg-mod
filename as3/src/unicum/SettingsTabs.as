package unicum
{
   import flash.display.DisplayObject;
   import flash.display.Sprite;
   import flash.events.Event;
   import flash.system.ApplicationDomain;
   import flash.utils.Dictionary;
   import flash.utils.getQualifiedClassName;

   // Adds the unicum.gg tab to the game's settings window, in the app this is
   // loaded into (LobbyView in the lobby, TeamNamesHtml in battle).
   //
   // The window's tabs are the list SettingsConfigHelper.instance holds, one
   // entry a tab: a label, and the class name of the view the window creates
   // for it (SettingsTab). The helper is made with the window and disposed
   // with it, so the entry is added each time a window shows up, and the
   // window's tab bar given the list again if it was drawn without it.
   //
   // The window comes from its own SWF (settingsWindow.swf), so it is known
   // by its class name, and the game's classes are taken from its own domain.
   //
   // Safe to be late: a window reopened on a tab index its list does not have
   // yet brings it back within the list (SettingsWindow.updateTabs).
   public class SettingsTabs
   {
      public static const LABEL:String = "unicum.gg";

      // The window's own class, and the symbol of settingsWindow.swf built on it.
      private static const WINDOW_CLASSES:Array = ["net.wg.gui.lobby.settings::SettingsWindow", "SettingsWindowUI"];

      private var _host:Sprite;

      // Settings windows on screen, weakly held.
      private var _windows:Dictionary = new Dictionary(true);

      // Whether the window was showing this tab when its list was last read:
      // applying settings makes the window build the list again, without this
      // tab, and the selection would fall back to the first one.
      private var _selected:Boolean = false;

      public function SettingsTabs(host:Sprite)
      {
         this._host = host;
         // Referenced so the compiler keeps the class the window creates by name.
         var tab:Class = SettingsTab;
         // ADDED_TO_STAGE, captured: a window is put together off stage and
         // added whole, and only what is added itself sends ADDED.
         App.stage.addEventListener(Event.ADDED_TO_STAGE, this.onAdded, true, 0, true);
         host.addEventListener(Event.ENTER_FRAME, this.onFrame);
      }

      private function onAdded(event:Event) : void
      {
         var target:DisplayObject = event.target as DisplayObject;
         if(target == null)
         {
            return;
         }
         if(WINDOW_CLASSES.indexOf(getQualifiedClassName(target)) < 0)
         {
            return;
         }
         if(this._windows[target])
         {
            return;
         }
         this._windows[target] = true;
         this.addTab(target);
      }

      private function onFrame(event:Event) : void
      {
         for(var key:Object in this._windows)
         {
            var window:DisplayObject = key as DisplayObject;
            if(window == null || window.stage == null)
            {
               delete this._windows[key];
               continue;
            }
            this.addTab(window);
         }
      }

      private function addTab(window:DisplayObject) : void
      {
         try
         {
            var domain:ApplicationDomain = window.loaderInfo != null ? window.loaderInfo.applicationDomain :
                                           ApplicationDomain.currentDomain;
            var helper:Object = domain.getDefinition("net.wg.gui.lobby.settings.config.SettingsConfigHelper");
            var tabs:Array = helper.instance.tabsDataProvider as Array;
            if(tabs == null)
            {
               return;
            }
            var found:Boolean = false;
            for each(var tab:Object in tabs)
            {
               if(tab.linkage == SettingsTab.LINKAGE)
               {
                  found = true;
                  break;
               }
            }
            var bar:Object = window["tabs"];
            if(found)
            {
               // Only while the list still holds this tab: once it is built
               // again without it, the window has already dropped the
               // selection, and what was showing before is what matters.
               this.remember(bar);
            }
            else
            {
               var entry:Class = domain.getDefinition("net.wg.gui.lobby.settings.vo.TabsDataVo") as Class;
               tabs.push(new entry({"label":LABEL, "linkage":SettingsTab.LINKAGE}));
            }
            if(bar != null && bar.dataProvider != null && bar.dataProvider.length < tabs.length)
            {
               var list:Class = domain.getDefinition("scaleform.clik.data.DataProvider") as Class;
               var selected:int = this._selected ? tabs.length - 1 : bar.selectedIndex;
               bar.dataProvider = new list(tabs);
               bar.selectedIndex = selected;
            }
            if(SettingsTab.holding > 0)
            {
               SettingsTab.holding--;
               this.keep(bar, tabs);
            }
         }
         catch(e:Error)
         {
            delete this._windows[window];
         }
      }

      // This tab back up after the window put its own one there: the window
      // shows the tab it remembers whenever settings come back from Python,
      // and applying from this tab is what asked for them.
      private function keep(bar:Object, tabs:Array) : void
      {
         if(bar == null)
         {
            return;
         }
         for(var i:int = 0; i < tabs.length; i++)
         {
            if(tabs[i].linkage == SettingsTab.LINKAGE)
            {
               if(bar.selectedIndex != i)
               {
                  bar.selectedIndex = i;
               }
               return;
            }
         }
      }

      // Whether the tab the window shows is this one, read before its list is
      // touched: the window drops its selection when the list is built again.
      private function remember(bar:Object) : void
      {
         if(bar == null || bar.dataProvider == null)
         {
            return;
         }
         var index:int = bar.selectedIndex;
         if(index < 0 || index >= bar.dataProvider.length)
         {
            return;
         }
         var item:Object = bar.dataProvider.requestItemAt(index);
         this._selected = item != null && item.linkage == SettingsTab.LINKAGE;
      }

      public function dispose() : void
      {
         App.stage.removeEventListener(Event.ADDED_TO_STAGE, this.onAdded, true);
         this._host.removeEventListener(Event.ENTER_FRAME, this.onFrame);
         this._windows = new Dictionary(true);
      }
   }
}
