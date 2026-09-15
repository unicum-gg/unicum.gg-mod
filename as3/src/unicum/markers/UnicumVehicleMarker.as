package unicum.markers
{
   import VehicleMarker;

   // The client's vehicle marker, with our rating and flags by the player's
   // name. src/unicum/name_markers.py has the markers manager create this in
   // place of the client's "VehicleMarker" symbol: subclassing the symbol
   // class keeps everything the client and the engine expect of a vehicle
   // marker, and adds only NameMarkerAddon.
   public class UnicumVehicleMarker extends VehicleMarker
   {
      private var _unicum:NameMarkerAddon = null;

      public function UnicumVehicleMarker()
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
