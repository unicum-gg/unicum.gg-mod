package unicum
{
   import flash.display.DisplayObjectContainer;
   import flash.events.Event;
   import flash.text.TextField;
   import flash.utils.Dictionary;
   import net.wg.infrastructure.base.AbstractView;

   // Lets a battle's team names show the unicum.gg badge after them.
   //
   // The loading screen and the Tab screen set each team name with
   // TextField.text, where an <IMG> is shown as written. Python appends the
   // badge's <IMG> to the name all the same (src/unicum/battle.py), and this
   // view, loaded into the battle app by src/unicum/views.py, finds those
   // fields and re-sets a name that carries a tag as htmlText. A name without
   // a tag is never touched.
   //
   // The fields are found by their names -- team1TF/team2TF on stats tables,
   // team1Text/team2Text on loading forms -- rather than by class, so a mode
   // with its own table class (Onslaught's is not in the decompiled sources)
   // is covered as long as it keeps the names. A screen arrives as one display
   // object with its fields already inside, so each added object is searched
   // down to MAX_DEPTH, once.
   public class TeamNamesHtml extends AbstractView
   {
      private static const FIELDS:Array = ["team1TF", "team2TF", "team1Text", "team2Text"];

      private static const MAX_DEPTH:int = 16;

      private var _fields:Dictionary = new Dictionary(true);

      private var _searched:Dictionary = new Dictionary(true);

      public function TeamNamesHtml()
      {
         super();
      }

      override protected function configUI() : void
      {
         super.configUI();
         mouseEnabled = false;
         mouseChildren = false;
         App.stage.addEventListener(Event.ADDED, this.onAdded, true, 0, true);
         addEventListener(Event.ENTER_FRAME, this.onFrame);
         // Screens drawn before this view loaded: Onslaught builds its stats
         // table first, and a hot reload finds everything already there.
         this.search(App.stage, 0);
      }

      override protected function onDispose() : void
      {
         App.stage.removeEventListener(Event.ADDED, this.onAdded, true);
         removeEventListener(Event.ENTER_FRAME, this.onFrame);
         this._fields = new Dictionary(true);
         this._searched = new Dictionary(true);
         super.onDispose();
      }

      private function onAdded(event:Event) : void
      {
         this.search(event.target, 0);
      }

      private function search(target:Object, depth:int) : void
      {
         if(target == null || this._searched[target])
         {
            return;
         }
         this._searched[target] = true;
         this.inspect(target);
         var container:DisplayObjectContainer = target as DisplayObjectContainer;
         if(container == null || depth >= MAX_DEPTH)
         {
            return;
         }
         for(var i:int = 0; i < container.numChildren; i++)
         {
            this.search(container.getChildAt(i), depth + 1);
         }
      }

      private function inspect(target:Object) : void
      {
         for each(var name:String in FIELDS)
         {
            var field:TextField = null;
            try
            {
               field = target[name] as TextField;
            }
            catch(e:Error)
            {
               // Not a property of this class; most added objects have none.
            }
            if(field != null)
            {
               this._fields[field] = true;
            }
         }
      }

      // Every frame: a name the client has just set as text would otherwise
      // show its raw tag until the next check. There are four fields at most.
      private function onFrame(event:Event) : void
      {
         for(var key:Object in this._fields)
         {
            var field:TextField = key as TextField;
            // Once shown as HTML, .text no longer contains the tag, so a name
            // is converted once each time the client sets it.
            if(field != null && field.text.indexOf("<IMG") >= 0)
            {
               field.htmlText = field.text;
            }
         }
      }
   }
}
