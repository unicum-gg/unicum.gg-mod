package unicum.markers
{
   import net.wg.app.impl.BattleVehicleMarkersApp;

   // The root of the client's markers movie, as tools/build_as3.py installs
   // it: the client's own BattleVehicleMarkersApp, named in place of it in the
   // SWF's SymbolClass tag, so this runs for certain as the movie starts.
   //
   // The client's app loads its libraries and then registers with Python,
   // which starts making markers. Ours extend classes from those libraries, so
   // they can only be loaded after them -- and must be in before the first
   // marker is made. So registration waits for them here (see
   // MarkersBoot.loadClasses).
   public class UnicumMarkersApp extends BattleVehicleMarkersApp
   {
      public function UnicumMarkersApp()
      {
         super();
      }

      override protected function onLibsLoadingComplete() : void
      {
         MarkersBoot.loadClasses(this.register);
      }

      private function register() : void
      {
         super.onLibsLoadingComplete();
      }
   }
}
