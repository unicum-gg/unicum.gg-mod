package net.wg.app.impl
{
   import net.wg.app.iml.base.RootApp;

   // Compile-time stand-in for the client's markers app root class, defined
   // in battleVehicleMarkersApp.swf itself. Listed in -externs by
   // tools/build_as3.py: never compiled in.
   public class BattleVehicleMarkersApp extends RootApp
   {
      public function BattleVehicleMarkersApp()
      {
         super(null, null, null);
      }

      override protected function onLibsLoadingComplete() : void
      {
      }
   }
}
