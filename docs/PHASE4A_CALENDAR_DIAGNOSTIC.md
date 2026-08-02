# Phase 4A — bezpečná diagnostika kalendáře

Tato fáze pouze zjišťuje strukturální vlastnosti celého aktuálně zobrazeného kalendáře.
Termino může zobrazovat pohled Den, 3 dny, Týden nebo Agenda. Diagnostika nepředpokládá
sedm sloupců a pohled vybírá uživatel ručně. Nejde o automatické hledání, klasifikaci ani
zpracování rezervací a Phase 4 jako celek ještě není hotová.

První živý test skončil bezpečně bez nalezeného kořene: Termino neposkytlo očekávaný
jednoznačný semantický kořen. Při tomto konkrétním výsledku diagnostika nově
spustí bezpečné strukturální hledání vrstev ukotvených rolí `gridcell`. Pokud nelze
vrstvu mřížky nebo událostí určit jednoznačně, diagnostika skončí pevným bezpečným kódem a
nikdy nevybere první shodu. Nerozpoznané záhlaví však anonymní výstup vrstev neblokuje.

## Bezpečný ruční postup

Použijte den obsahující pouze zjevně smyšlenou rezervaci, například `TEST OSOBA`:

```powershell
python -m termino_exporter diagnose-calendar
```

Ve viditelném prohlížeči se ručně přihlaste, ručně zvolte pohled Den, 3 dny nebo Týden a
neotvírejte detail žádné události. Potom se vraťte do terminálu a stiskněte Enter.

Program pouze jednou přečte aktuální DOM. Nekliká na rezervace ani jiné prvky, neposouvá
kalendář a nemění datum. Nevytváří screenshot, HTML snapshot, trace, video, HAR ani jiný
soubor.

Browserový skript vytváří pouze omezený anonymní strukturální snapshot složený z počtů a
booleanů. Volbu jediné gridcell vrstvy, event layer a skupiny záhlaví provádí samostatný
čistý Python resolver bez Playwrightu a vedlejších účinků. Resolver je testován nad
smyšlenými snapshoty bez spuštění browseru.

## Povolený výstup

Výstup obsahuje pouze režim, diagnostický typ pohledu, počet sloupců, potvrzení obou
vrstev, normalizovaný index dne v týdnu a číslo dne a anonymní počet event blocks v
každém sloupci. Hodnoty textu, accessible name, `aria-label`, `href` a `data-*` se
nevypisují ani nevracejí.

Počet sloupců může být 1, 3, 7 nebo jiný bezpečně omezený počet do 14. Označení Den,
3 dny a Týden je pouze diagnostický popis jednoznačné skupiny, nikoli produkční rozhodnutí.
Automatické otevření události patří do pozdějšího kroku.

## Anonymní strukturální kotva

Termino používá samostatnou semantickou vrstvu, jejíž každá denní větev obsahuje právě
jeden element s rolí `gridcell`. Vedle ní byly anonymně pozorovány pravidelná časová mřížka,
prázdné pomocné paralelní vrstvy a vrstva obecných událostí. Event layer musí mít stejný
počet denních větví, nesmí obsahovat `gridcell` a musí jako jediná obsahovat alespoň jeden
malý neprázdný obsahový blok. Konkrétní počet buněk časové mřížky není konstanta. Nula nebo
více platných vrstev skončí pevným bezpečným kódem; první shoda se nikdy nevybere.

Přímé obsahové bloky paralelní vrstvy jsou označeny pouze neutrálně jako calendar event
blocks. Mohou to být obyčejné nefocusable elementy `div`. Text se uvnitř browserového
skriptu používá pouze jako boolean příznak neprázdného obsahu a nikdy se nevrací.
Rezervace a blokace mají podobnou vnější strukturu, proto se obě pouze započítají a
nerozlišují se podle potomků, textu, ikon, barev ani jiných vzhledových vlastností.
Klasifikace patří až do Phase 4B po bezpečném otevření a ověření detailu.

Pomocný přímý potomek bez neprázdného textu není event block. Záhlaví dnů mohou být mimo
omezeného společného předka; v takovém případě režim
`CALENDAR_LAYERS_FOUND_HEADERS_UNRESOLVED` vrátí pořadí sloupců a počty bloků, ale
`weekday_index` a `day_number` zůstanou `None`. Pokud celé období nemá žádný textový event
block, diagnostika vrátí `EVENT_LAYER_EMPTY_OR_NOT_FOUND` a žádnou prázdnou vrstvu
nevybere. To je známé omezení Phase 4A. Phase 4B zatím není implementována.

Po ručním testu sdílejte pouze slovní shrnutí strukturálních výsledků. Nevkládejte do
repozitáře ani komunikace klientská data, terminálový výstup obsahující nečekané hodnoty,
produkční HTML nebo screenshoty.
