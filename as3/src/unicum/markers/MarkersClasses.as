package unicum.markers
{
   import flash.display.Sprite;

   // The root of unicum.markers.classes.swf: our marker classes, loaded into
   // the client's markers movie by MarkersBoot once the classes they extend
   // are there.
   public class MarkersClasses extends Sprite
   {
      private static const MARKERS:Array = [UnicumVehicleMarker, UnicumComp7VehicleMarker];

      public function MarkersClasses()
      {
         super();
      }
   }
}
