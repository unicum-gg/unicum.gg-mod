package unicum
{
   import net.wg.infrastructure.base.AbstractView;

   // The mod's one view in the lobby, loaded by src/unicum/views.py.
   //
   // One view, not one per feature: the lobby's service layer is a
   // single-view container, and loading a second view there destroys the
   // first. The features live in their own classes:
   //
   //   TitleHtml   profile window titles that render HTML
   //   RoomTools   the skirmish room's members sort and average
   //   ContactColumns  the contacts list's flags and rating, right of each row
   //   SettingsTabs    the unicum.gg tab of the game's settings window
   //
   // Python reads and writes RoomTools' state through the GFx proxy, which
   // sees this view's public properties, so they are forwarded here.
   public class LobbyView extends AbstractView
   {
      private var _titles:TitleHtml;

      private var _room:RoomTools;

      private var _contacts:ContactColumns;

      private var _settingsTabs:SettingsTabs;

      public function LobbyView()
      {
         super();
      }

      public function get sortMode() : String
      {
         return this._room != null ? this._room.sortMode : "";
      }

      public function set sortMode(value:String) : void
      {
         if(this._room != null)
         {
            this._room.sortMode = value;
         }
      }

      public function get sortLabels() : String
      {
         return this._room != null ? this._room.sortLabels : "";
      }

      public function set sortLabels(value:String) : void
      {
         if(this._room != null)
         {
            this._room.sortLabels = value;
         }
      }

      public function get ratingByPlayer() : String
      {
         return this._room != null ? this._room.ratingByPlayer : "";
      }

      public function set ratingByPlayer(value:String) : void
      {
         if(this._room != null)
         {
            this._room.ratingByPlayer = value;
         }
      }

      public function get averageHtml() : String
      {
         return this._room != null ? this._room.averageHtml : "";
      }

      public function set averageHtml(value:String) : void
      {
         if(this._room != null)
         {
            this._room.averageHtml = value;
         }
      }

      public function get contactMarkers() : String
      {
         return this._contacts != null ? this._contacts.markersText : "";
      }

      public function set contactMarkers(value:String) : void
      {
         if(this._contacts != null)
         {
            this._contacts.markersText = value;
         }
      }

      public function get settingsTab() : String
      {
         return "";
      }

      // The page of the settings window's unicum.gg tab (src/unicum/settings_tab.py).
      public function set settingsTab(value:String) : void
      {
         SettingsTab.page = value;
      }

      // What the tab's Apply or OK committed, for Python to take.
      public function get settingsTabOut() : String
      {
         return SettingsTab.out.join("\n");
      }

      public function set settingsTabOut(value:String) : void
      {
         SettingsTab.out = value ? value.split("\n") : [];
      }

      public function get roomEnabled() : Boolean
      {
         return this._room == null || this._room.roomEnabled;
      }

      public function set roomEnabled(value:Boolean) : void
      {
         if(this._room != null)
         {
            this._room.roomEnabled = value;
         }
      }

      override protected function configUI() : void
      {
         super.configUI();
         mouseEnabled = false;
         this._titles = new TitleHtml(this);
         this._room = new RoomTools(this);
         this._contacts = new ContactColumns(this);
         this._settingsTabs = new SettingsTabs(this);
      }

      override protected function onDispose() : void
      {
         this._titles.dispose();
         this._room.dispose();
         this._contacts.dispose();
         this._settingsTabs.dispose();
         super.onDispose();
      }
   }
}
