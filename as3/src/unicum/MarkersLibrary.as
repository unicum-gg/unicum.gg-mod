package unicum
{
   import flash.display.Sprite;

   // The root of unicum.markers.swf: a library, loaded into the client's
   // markers movie by unicum.markers.MarkersBoot, for its NameMarkerView.
   public class MarkersLibrary extends Sprite
   {
      private static const VIEW:Class = NameMarkerView;

      public function MarkersLibrary()
      {
         super();
      }
   }
}
