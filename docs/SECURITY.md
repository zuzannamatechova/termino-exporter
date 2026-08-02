# Bezpečnost a soukromí

Repozitář je veřejný. V testech, příkladech a dokumentaci smějí být pouze smyšlená data.

- Program nikdy nesmí ukládat heslo do Termino. Přihlášení se očekává ručně ve
  viditelném prohlížeči.
- Profily prohlížeče, cookies a autentizační data jsou pouze lokální.
- Cesta persistentního profilu nesmí ležet uvnitř žádného Git repozitáře. Kontrola
  prochází cílovou cestu a její rodiče a rozpozná `.git` jako adresář i soubor worktree.
- Exporty za běhu mohou obsahovat osobní údaje a musí zůstat v adresářích ignorovaných
  Gitem.
- Produkční snímky, záznamy, HTML a logy mohou obsahovat osobní údaje. Ve výchozím
  nastavení musí být vypnuté, nebo se smějí ukládat jen lokálně do ignorovaných
  adresářů.
- Tajné údaje nesmějí být ve zdrojovém kódu, dokumentaci, commitech, popisech issues ani
  pull requestech.
- Aplikace musí vůči Termino zůstat pouze pro čtení. Nesmí vytvářet, upravovat,
  kopírovat, rušit ani mazat rezervace.
- Po jediném kliknutí na bezpečné tlačítko `Více` aplikace omezenou dobu polluje čerstvý
  DOM. Stejný kandidát nikdy neklikne podruhé a na tlačítko `Méně` nekliká vůbec.
- `raw_detail` zůstává pouze v paměti, je skrytý z `repr`, neovlivňuje rovnost objektů a
  nesmí se objevit ve strukturovaném výstupu ani chybové zprávě.
- Diagnostika kalendáře čte pouze omezené strukturální metriky celého aktuálního pohledu. Nevrací
  text prvků ani hodnoty `aria-label`, `href` nebo `data-*`, nekliká a neukládá HTML,
  screenshoty, trace, video ani HAR.
- Browserový census vrací pouze explicitně sestavený omezený snapshot čísel a booleanů.
  Snapshot je před použitím validován a vrstvy vybírá čistý Python resolver testovatelný
  bez browseru; neplatná data končí pevným bezpečným chybovým kódem bez jejich `repr`.
- Při chybějící nebo víceznačné vrstvě mřížky či událostí diagnostika skončí pevným
  bezpečným kódem. Nerozpoznaná záhlaví mohou zůstat nepřipojená a jejich hodnoty budou
  `None`; neblokují anonymní strukturální výstup. Diagnostika nevrací DOM elementy, text ani
  atributové hodnoty a žádná událost se automaticky neotevírá.
- Kalendářová vrstva se kotví pouze přes přesnou standardní roli `gridcell`. Paralelní
  event layer musí mít stejný počet denních větví, být jednoznačná a obsahovat alespoň jeden
  omezený neprázdný obsahový blok. Prázdné pomocné vrstvy, pravidelná časová mřížka a
  elementy bez textu se nevybírají. Ve zcela prázdném období se event layer neodhaduje.
  Obecné event blocks mohou být neinteraktivní `div`; rezervace a blokace se neklasifikují
  podle textu, potomků, ikon, barev, tříd, ID ani vzhledu.
- Jakákoli budoucí zapisující akce vyžaduje samostatné výslovné návrhové rozhodnutí a
  nesmí vzniknout jako vedlejší efekt jiné úlohy.

Před commitem je nutné zkontrolovat změny i neznámé soubory a ověřit, že neobsahují
osobní, autentizační ani produkční data.
