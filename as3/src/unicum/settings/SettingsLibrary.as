package unicum.settings
{
   import flash.display.Sprite;

   // The root of unicum.settings.swf: a library, loaded by the unicum.SettingsTab
   // shell into a domain of its own, for its SettingsTabView.
   public class SettingsLibrary extends Sprite
   {
      private static const VIEW:Class = SettingsTabView;

      public function SettingsLibrary()
      {
         super();
      }
   }
}
