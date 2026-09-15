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
   //
   // Python reads and writes RoomTools' state through the GFx proxy, which
   // sees this view's public properties, so they are forwarded here.
   public class LobbyView extends AbstractView
   {
      private var _titles:TitleHtml;

      private var _room:RoomTools;

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
      }

      override protected function onDispose() : void
      {
         this._titles.dispose();
         this._room.dispose();
         super.onDispose();
      }
   }
}
