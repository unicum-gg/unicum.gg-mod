package unicum.markers
{
   import Comp7VehicleMarkerUI;

   // Onslaught's vehicle marker, with our rating and flags by the player's
   // name: the same as UnicumVehicleMarker, on the "Comp7VehicleMarkerUI"
   // symbol that mode uses instead.
   public class UnicumComp7VehicleMarker extends Comp7VehicleMarkerUI
   {
      private var _unicum:NameMarkerAddon = null;

      public function UnicumComp7VehicleMarker()
      {
         super();
         this._unicum = new NameMarkerAddon(this);
      }

      override protected function onDispose() : void
      {
         this._unicum.dispose();
         super.onDispose();
      }

      // Called through the canvas's markerInvoke.
      public function setUnicumData(... args) : void
      {
         this._unicum.call("setData", args);
      }

      public function reloadUnicumView() : void
      {
         MarkersBoot.load();
      }
   }
}
