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
- Vnořené grid anchory se považují za ekvivalentní pouze při stejném počtu větví a shodě
  uspořádaných živých DOM elementů `gridcell`. Porovnání identity probíhá výhradně uvnitř
  browserového skriptu. Context root určuje pouze kanonický anchor; zastíněné vnější obaly
  se nepoužijí jako kořen ani se nepřidávají jako duplicitní snapshot vrstvy. Nezávislé
  kandidáty se neslučují a první ani obecně nejhlubší shoda se automaticky nevybírá.
- Přímé děti context rootu jsou paralelní vrstvy a jejich počet není počet dnů. Event layer
  musí následovat za kanonickou grid vrstvou, mít stejný `branch_count`, neobsahovat
  `gridcell`, nebýt navigací ani záhlavím a být jediným platným kandidátem. Obsahová vrstva
  před gridem se nikdy automaticky nepoužije.
- Jakákoli budoucí zapisující akce vyžaduje samostatné výslovné návrhové rozhodnutí a
  nesmí vzniknout jako vedlejší efekt jiné úlohy.
- Phase 4B vytvoří pouze interní plán z čerstvého anonymního snapshotu. Druhý nezávislý
  census znovu provede jednoznačné rozpoznání a porovná pouze anonymní významový fingerprint
  počtu sloupců a bloků a omezených číselných a booleanových metrik vybrané grid a event
  vrstvy. Ordinaly platí jen uvnitř jednoho snapshotu, mezi censy se jako identita
  neporovnávají a atomický resolver podle starého ordinalu neindexuje.
- Na ověřený event block se kliká nejvýše jednou, bez `force`, souřadnic nebo opakování.
  Kalendářní text se nepoužívá ke klasifikaci. Pouze jednoznačná známá struktura detailu
  dovolí předání existujícímu zpracování rezervace; neznámý detail se nezavírá neověřeným
  prvkem a operace bezpečně skončí.
- Každý vytvořený Playwright `JSHandle` nebo `ElementHandle` má jednoznačného vlastníka.
  Dočasné handly se uvolňují ve `finally`; vlastnictví vráceného handle přechází na volajícího.
  `DetailStructure` uvolňuje všechny své vlastní wrappery idempotentně a chyby Playwrightu při
  `dispose()` nesmějí zakrýt původní aplikační chybu. Caller-owned vstupní obsah struktura
  neočekávaně neuvolňuje.
- BrowserContext se nadále vždy zavře, ale slouží jen jako poslední pojistka. Primární úklid
  handlů probíhá explicitně během jednoho zpracování detailu, aby se wrappery nehromadily při
  budoucím opakování toku.
- Headless browserové integrační testy používají pouze lokální syntetické HTML se smyšlenými
  hodnotami. Nepřistupují k Termino ani k internetu, nepoužívají produkční HTML, persistentní
  profil, screenshoty, trace, video, HAR ani autentizační stav.

Před commitem je nutné zkontrolovat změny i neznámé soubory a ověřit, že neobsahují
osobní, autentizační ani produkční data.
