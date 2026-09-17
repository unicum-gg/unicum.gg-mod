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
   //
   // The same search finds the screens VehicleMarkers draws beside the
   // vehicle icons; Python sets the three public strings below.
   public class TeamNamesHtml extends AbstractView
   {
      private static const FIELDS:Array = ["team1TF", "team2TF", "team1Text", "team2Text"];

      // The loading screen's team names, whose average this view hides itself.
      private static const LOADING_FIELDS:Array = ["team1Text", "team2Text"];

      private static const MAX_DEPTH:int = 16;

      // field -> its name in FIELDS
      private var _fields:Dictionary = new Dictionary(true);

      // loading screen team name -> the text it shows with its average taken out
      private var _stripped:Dictionary = new Dictionary(true);

      private var _searched:Dictionary = new Dictionary(true);

      private var _markers:VehicleMarkers = new VehicleMarkers();

      // field -> [the text the client set, the same text once shown as HTML]
      private var _names:Dictionary = new Dictionary(true);

      // One vehicle a line: "id TAB badge TAB its width TAB flags TAB their width".
      public var markersText:String = null;

      // Each team's vehicle ids, top row first, comma separated.
      public var leftIds:String = null;

      public var rightIds:String = null;

      // True while a screen's ratings wait for the extended info key (Alt):
      // it draws none, and no team average either.
      public var panelHidden:Boolean = false;

      public var tabHidden:Boolean = false;

      public var loadingHidden:Boolean = false;

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
         this._stripped = new Dictionary(true);
         this._searched = new Dictionary(true);
         this._names = new Dictionary(true);
         this._markers.dispose();
         super.onDispose();
      }

      // Takes a loading screen team name's average out while hidden, and gives
      // it back after; a name the client has set since is left to it.
      private function hideAverage(field:TextField, hidden:Boolean) : void
      {
         var names:Array = this._names[field] as Array;
         if(names == null)
         {
            return;
         }
         var stripped:* = this._stripped[field];
         if(hidden && stripped === undefined && field.text == names[1])
         {
            var found:Object = VehicleMarkers.AVERAGE.exec(names[0]);
            if(found != null)
            {
               field.htmlText = found[1];
               this._stripped[field] = field.text;
            }
         }
         else if(!hidden && stripped !== undefined)
         {
            if(field.text == stripped)
            {
               field.htmlText = names[0];
               names[1] = field.text;
            }
            delete this._stripped[field];
         }
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
         this._markers.inspect(target);
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
               this._fields[field] = name;
            }
         }
      }

      // Every frame: a name the client has just set as text would otherwise
      // show its raw tag until the next check. There are four fields at most.
      // A row the panel has just moved takes its markers along the same way.
      private function onFrame(event:Event) : void
      {
         this._markers.update(this.markersText, this.leftIds, this.rightIds, this._names, this.panelHidden,
                              this.tabHidden, this.loadingHidden);
         for(var key:Object in this._fields)
         {
            var field:TextField = key as TextField;
            if(field == null)
            {
               continue;
            }
            // Once shown as HTML, .text no longer contains the tag, so a name
            // is converted once each time the client sets it.
            if(field.text.indexOf("<IMG") >= 0)
            {
               var set:String = field.text;
               field.htmlText = set;
               this._names[field] = [set, field.text];
               delete this._stripped[field];
            }
            if(LOADING_FIELDS.indexOf(this._fields[key]) >= 0)
            {
               this.hideAverage(field, this.loadingHidden);
            }
         }
      }
   }
}
