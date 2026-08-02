# Phase 4C — bezpečný návrh zpracování jednoho dne

Tento dokument je návrh. Nezavádí nový příkaz, nemění calendar resolver a
nepovoluje zpracování více událostí v živém Termino. Všechna rozhodnutí vycházejí
ze současného produkčního kódu, jednotkových a syntetických browserových testů a
zdokumentovaných ručních testů. Chybějící důkaz je označen `UNPROVEN`; neznámá,
která brání bezpečné automatizaci, je označena `BLOCKER`.

## Stav před Phase 4C

Phase 4A pouze anonymně diagnostikuje strukturu kalendáře. Nečte text eventů a
na nic nekliká. Její census vrací omezené počty, boolean příznaky a strukturální
vrstvy.

Phase 4B podporuje pouze ručně zvolený pohled Den s právě jedním obecným event
blockem. Event se neklasifikuje podle textu, barvy, rozměru ani vzhledu.
Podporovaná rezervace je potvrzena až známou strukturou otevřeného detailu.
Neznámý detail se automaticky nezavírá.

Bezprostředně před jediným kliknutím se provede nový census a event handle se
získá atomicky z právě platného DOM. Snapshotové ordinaly nejsou identitou mezi
dvěma censusy. Každý `JSHandle` a `ElementHandle` má explicitní vlastnictví a je
uvolněn i při chybě.

Produkční kód obsahuje tři povolená interaktivní místa:

- jedno kliknutí na bezpečně nalezený calendar event;
- nejvýše deset kliknutí na přesně pojmenované tlačítko `Více`;
- jedno kliknutí na strukturálně ověřený zavírací prvek známého rezervačního
  detailu.

Zpracování celého dne, více eventů, blokací ani jiných neklientských událostí
není implementováno.

| Kategorie důkazu | Současný stav |
| --- | --- |
| Implementováno | Anonymní census; jednoznačný pohled Den; právě jeden event; čerstvý handle před kliknutím; známý rezervační detail; rozbalení `Více`; strukturální close; parsování jedné rezervace; cleanup handlů a contextu. |
| Synteticky ověřeno | Lokální DOM pro Den a další gridové pohledy, strukturální ambiguity, změny fingerprintu, odpojené a nejednoznačné handly a lifecycle cleanup. Fixture nepoužívají síť ani produkční HTML. |
| Ručně ověřeno | Phase 4A v pohledu Den a Phase 4B s jedinou dummy rezervací. Ruční důkaz se nevztahuje na více eventů ani neklientské detaily. |
| Požadavek roadmapy | Zpracovat události jednoho dne a izolovat chybu jedné položky, pokud lze bezpečně pokračovat. |
| Dosud neznámé | Stabilní anonymní identita eventu; stabilita pořadí více eventů po otevření a zavření detailu; struktura blokací a jiných neklientských detailů; jejich bezpečný close kontrakt. |

## Cíl

Navrhnout fail-closed tok pro omezený počet eventů v jednom uživatelem ručně
zvoleném dni. Tok smí pokračovat pouze tehdy, když je pro každý krok prokázána
identita cíle, známý stav detailu, bezpečné zavření a nezměněná struktura
kalendáře. Výsledkem má být pouze in-memory `DayProcessingResult`.

## Rozsah

- pouze ručně zvolený pohled Den a ručně zvolené dummy-only datum;
- anonymní plán a strukturální census 1 až 10 eventů; prázdný den zůstává
  blokovaný, dokud nebude bezpečně prokázána jeho event layer;
- deterministické pořadí bez čtení textu event blocků;
- zpracování podporovaných rezervací existujícím bezpečným tokem;
- v budoucnu explicitně známé neklientské detaily, až budou zvlášť prokázány;
- přesné oddělení recoverable a fatal chyb;
- pevné limity, sanitizované kódy a explicitní vlastnictví handlů.

## Mimo rozsah

- automatická navigace na jiné datum nebo změna pohledu;
- Agenda, Týden, více pracovišť nebo více kalendářních kontextů;
- čtení textu, času, služby nebo jména z calendar event blocku;
- klasifikace podle barvy, geometrie, pozice, velikosti, CSS tříd nebo ID;
- export do Excelu nebo jiný zápis výsledků na disk;
- retry kliknutí na event;
- `force` click, JavaScriptový click, souřadnice, `Escape`, screenshot, OCR,
  ukládání HTML, trace nebo video;
- odhad struktury blokací a neznámých detailů;
- zpracování zcela prázdného dne bez samostatného no-click důkazu event layer.

## Bezpečnostní invarianty

1. Termino je pouze pro čtení. Nikdy se nevyvolá `Upravit`, `Odstranit` ani
   `Zkopírovat rezervaci`.
2. Před každým event clickem je detail prokazatelně zavřený.
3. Jeden plánovaný target smí dostat nejvýše jeden event click za celý běh.
4. Žádný dlouhodobý plán neobsahuje živý Playwright handle.
5. Handle se získá čerstvě, atomicky se strukturální validací, použije se nejvýše
   jednou a uvolní se před klasifikací detailu.
6. Pokračování vyžaduje potvrzené zavření známého detailu a platný post-event
   census.
7. Neznámý nebo nejednoznačný detail se nezavírá a ukončí celý běh.
8. Událost se neidentifikuje osobními údaji, textem, geometrií, třídou, ID ani
   snapshotovým ordinalem bez dalšího důkazu stability.
9. Raw detail a objekty `Reservation` zůstávají pouze v paměti a nejsou součástí
   chyb, logů ani `repr` day-level obálek.
10. Playwright chyba se mapuje na pevný kód bez původního textu. Původní výjimka
    může zůstat pouze jako nevypsaná exception cause.
11. Jakákoli nejistota o kliknutí, identitě, lifecycle handle nebo DOM změně je
    fatal.
12. BrowserContext se ukončí při úspěchu, očekávané chybě i `KeyboardInterrupt`.

## Známá fakta

- `CalendarDomSnapshot` je anonymní immutable model strukturálních hodnot.
- Resolver vyžaduje jednoznačný grid a event layer; event layer musí následovat
  za gridem.
- Současný handle režim je záměrně omezen na jeden sloupec, jeden event a
  ordinaly `1`.
- `SingleEventSelectionPlan` ukládá strukturální fingerprint, ale jeho ordinaly
  nejsou identitou mezi censusy.
- Současný single-event tok dělá nový census těsně před získáním handle a jeden
  event click bez retry.
- Rezervační detail je rozpoznán strukturou HEADER–CONTENT–ACTION. Zakázané akce
  jsou výslovně vyloučeny a close je strukturálně ověřen.
- `inspect_open_detail` aktuálně zpracuje, vypíše a zavře jednu rezervaci. Při
  chybě před close není obecně zaručeno bezpečné zavření, takže tuto chybu dnes
  nelze automaticky považovat za recoverable.
- `Reservation.raw_detail` může obsahovat osobní údaje, je pouze v paměti a je
  vyloučen z `repr` a porovnání.
- Census nečte stabilní anonymní atribut eventu a nevrací per-event identitu.
- Resolver přijímá event layer pouze tehdy, když obsahuje alespoň jeden event
  block. `EVENT_LAYER_EMPTY_OR_NOT_FOUND` nerozlišuje zcela prázdný den od
  chybějící nebo nerozpoznané event layer. Nula eventů proto dnes není bezpečně
  prokázaný vstup pro day plan.

## Neověřené předpoklady

- `UNPROVEN`: Termino po zavření detailu zachová stejné DOM uzly event blocků.
- `UNPROVEN`: Termino nepřeuspořádá dva eventy se stejnou strukturou.
- `UNPROVEN`: Existuje stabilní anonymní atribut eventu, který neobsahuje osobní
  ani provozně citlivá data.
- `UNPROVEN`: Všechny neklientské události otevírají detail.
- `UNPROVEN`: Blokace a jiné neklientské detaily mají stejný bezpečný close
  kontrakt jako rezervace.
- `UNPROVEN`: Chyba parsování může být oddělena od close tak, aby šlo detail vždy
  bezpečně zavřít bez další interakce.

Žádný z těchto předpokladů se nesmí v produkční implementaci použít jako fakt.

## Blokující neznámé

- `BLOCKER — EVENT_STABLE_IDENTITY_UNKNOWN`: současný census neumí rozlišit dva
  strukturálně stejné eventy po výměně jejich pořadí. Shodný agregovaný
  fingerprint proto sám neprokazuje identitu targetu.
- `BLOCKER — EVENT_ORDER_STABILITY_UNKNOWN`: není doloženo, že otevření a zavření
  detailu nezmění pořadí event blocků.
- `BLOCKER — NONCLIENT_DETAIL_STRUCTURE_UNKNOWN`: blokace a jiné neklientské
  detaily nebyly bezpečně anonymně pozorovány.
- `BLOCKER — NONCLIENT_CLOSE_CONTRACT_UNKNOWN`: bez známé struktury nelze bezpečně
  ověřit jejich zavírací prvek ani potvrdit zavření.
- `BLOCKER — RECOVERABLE_DETAIL_FAILURE_CLEANUP_UNKNOWN`: současný detailový tok
  negarantuje bezpečný close po každé chybě extrakce, parsování nebo výstupu.
- `BLOCKER — EMPTY_DAY_EVENT_LAYER_UNPROVEN`: při nule eventů současný resolver
  event layer bezpečně neurčí. Chybějící vrstva, prázdná pomocná vrstva ani kód
  `EVENT_LAYER_EMPTY_OR_NOT_FOUND` se nesmějí automaticky vyložit jako prázdný
  den.

Pro prázdný den je zvolena **Varianta A**: Phase 4C1 podporuje pouze 1 až 10
eventů a bezpečně končí kódem `DAY_EMPTY_EVENT_LAYER_UNPROVEN`. Varianta B je
zamítnuta, protože současný resolver i testy výslovně vyžadují neprázdný event
layer a neposkytují jednoznačný no-click kontrakt pro výběr prázdné vrstvy.

První blokátor nebrání Phase 4C1 bez klikání. Brání ale produkčnímu loopu přes
druhý a další event. Před Phase 4C2 je nutná samostatná diagnostická mezifáze:

1. pouze dummy-only den s nejméně dvěma eventy;
2. výstup pouze booleanů a omezených počtů, bez textu a atributových hodnot;
3. uživatel ručně otevře a zavře detail, diagnostika sama nekliká;
4. porovná se počet, pořadí, DOM node identity a dostupnost případného stabilního
   anonymního atributu, aniž se jeho hodnota vypíše;
5. atribut lze přijmout jen po zvláštním důkazu, že je unikátní, stabilní,
   neobsahuje PII a lze jej bezpečně validovat;
6. negativní nebo nejednoznačný výsledek zachová blokaci Phase 4C2.

Pro neklientské eventy je nutná druhá samostatná diagnostika jejich detailové
struktury. Nesmí být spojena s implementací loopu.

## Model více eventů

Baseline plán obsahuje pouze anonymní fingerprint dne a konečný počet targetů.
Targety jsou pozice v baseline plánu, nikoli trvalá DOM identita. Pro klikací
loop je navíc nutný prokázaný `stable_event_key`, nebo ekvivalentně silný důkaz
identity a pořadí. Dokud neexistuje, plán je použitelný pouze pro Phase 4C1 bez
kliknutí.

| Varianta | Bezpečnost | Stale handle | Duplicita / přeskočení | Reakce na DOM změnu | Současné důkazy |
| --- | --- | --- | --- | --- | --- |
| Baseline fingerprint + ordinal při nezměněné celé struktuře | Podmíněně bezpečná jen tehdy, když „celá struktura“ zahrnuje prokazatelnou per-event identitu a pořadí. Dnešní agregovaný fingerprint nestačí. | Nízké, handle se získává čerstvě. | Vysoké u dvou strukturálně stejných eventů, které se prohodí. | Zastaví se při zjistitelné změně; tichou výměnu stejných eventů nezjistí. | Částečně: single-event fresh census ano; multi-event identita `UNPROVEN`, `BLOCKER`. |
| Nový census před každým clickem a po každém close | Povinná ochrana, ale sama není identitou. | Nízké. | Bez stabilního klíče stále možná duplicita či skip. | Zjistitelná změna je fatal. | Census existuje; multi-event porovnání není implementováno. |
| Více živých `ElementHandle` současně | Nevhodná. Handly mohou po otevření detailu zastarat a jejich dlouhé vlastnictví komplikuje cleanup. | Vysoké. | Nejasné po rerenderu. | Změna může odpojit část handlů bez jednotného důkazu. | V rozporu se současným lifecycle hardeningem. Zamítnuto. |
| Opakovaně první dosud nezpracovaný event | Nebezpečná bez stabilní identity. „Dosud nezpracovaný“ nelze odvodit jen z DOM. | Nízké. | Vysoké riziko opakovaného clicku na první event, protože po close zůstává v kalendáři. | Rerender může změnit, co je „první“. | Nepodpořeno. Zamítnuto. |
| Stabilní DOM atribut | Preferovaný budoucí model, pouze pokud je anonymně prokázán jako ne-PII, unikátní a stabilní. | Nízké při atomickém fresh lookupu. | Nízké díky in-memory množině spotřebovaných klíčů. | Chybějící, duplicitní nebo změněný klíč je fatal. | `UNPROVEN`, vyžaduje diagnostickou mezifázi. |

Doporučení: Phase 4C1 vytvoří immutable ordinal plan pro 1 až 10 eventů bez
clicku. Phase 4C2 smí
přejít na event loop až po prokázání stabilního anonymního klíče. Pokud žádný
takový klíč neexistuje, musí zůstat multi-event click loop blokovaný; agregovaný
fingerprint a ordinal nejsou náhradou identity.

## Stabilita a identita targetu

Pojmy se nesmějí zaměňovat:

- **baseline ordinal** je pouze pozice eventu v jednom snapshotu a Phase 4C1
  plánu;
- **živá DOM identita** je porovnání konkrétních uzlů uvnitř jediného browserového
  průchodu; nepřenáší se do Python plánu a není stabilitou přes rerender;
- **agregovaný calendar fingerprint** popisuje vrstvy, počty a omezené strukturální
  metriky; neidentifikuje jednotlivý event;
- **per-event identita** musí rozlišit každý target a zachovat jeho vazbu přes
  fresh census a rerender;
- **stabilní anonymní event key** je zatím neprokázaný kandidát per-event identity,
  nikoli implementovaná schopnost.

Bez stabilního anonymního klíče nebo jiného stejně silného mechanismu identity
nelze s aktuálními důkazy bezpečně cílit druhý a další event. Preferovaným
kandidátem může být stabilní anonymní DOM atribut, ale jeho existence není fakt.
Jiný mechanismus je přijatelný pouze tehdy, když prokáže jednoznačnost, stabilitu
přes rerender, absenci osobních i provozně citlivých dat, atomický fresh lookup,
detekci duplicity a sanitizovaný výstup bez hodnoty klíče. DOM ordinal je bezpečný
pouze jako pozice uvnitř jednoho atomického
lookupu. Mezi dvěma snapshoty může být použit pouze tehdy, pokud je nezávisle
prokázána neměnnost identity a pořadí všech eventů. Současný fingerprint tuto
podmínku nesplňuje.

Před každým eventem musí budoucí loop provést:

1. kontrolu, že detail není otevřený;
2. fresh census;
3. porovnání gridu, event layer, počtu eventů, per-event stabilních klíčů a jejich
   pořadí s baseline;
4. kontrolu, že cílový klíč ještě není v `consumed_targets` ani
   `attempted_targets`;
5. atomický lookup právě jednoho viditelného eventu podle bezpečně prokázaného
   klíče a stejného strukturálního kontextu;
6. nejvýše jeden click a okamžitý dispose handle.

Pořadí zpracování má jedinou přijatelnou variantu, a i ta je podmíněná důkazem
identity:

| Varianta pořadí | Rozhodnutí |
| --- | --- |
| Aktuální DOM pořadí uvnitř jednoznačné event branch | Jediný přijatelný kandidát. Smí se použít jen při neměnném baseline fingerprintu, prokázané per-event identitě a pořadí, omezeném počtu eventů, ekvivalentním census po každé položce a nejvýše jednom použití každého targetu. |
| Obrácené DOM pořadí | Zamítnuto. Je stejně závislé na stabilitě DOM, nepřidává bezpečnostní důkaz a komplikuje audit spotřebovaných targetů. |
| Geometrie nebo vizuální pořadí | Zakázáno; vyžadovalo by rozměry či souřadnice a je citlivé na layout. |
| Text, jméno, čas nebo služba | Zakázáno; jde o soukromý obsah a není to bezpečná DOM identita. |

Následující změny znamenají okamžitý `FATAL_STOP`:

- změna počtu eventů nebo jejich prokázaného pořadí;
- přidání, odebrání, duplicita nebo změna stabilního klíče;
- změna grid layer, event layer nebo bezpečnostního fingerprintu;
- ztráta event layer či víceznačný grid, context nebo target;
- otevřený detail před clickem;
- neznámý či víceznačný detail po clicku;
- nepotvrzené zavření;
- post-event census odlišný od baseline;
- jakákoli nejasnost, zda event click proběhl.

## Prevence duplicit

Prevence duplicit má tři oddělené vrstvy:

1. **Duplicitní click:** před clickem se atomicky vloží stabilní target key do
   `attempted_targets`. Vložení proběhne ještě před interakcí a nikdy se nevrací
   zpět. Pokud proces skončí po vložení do `attempted_targets`, ale ještě před
   skutečným vyvoláním `click()`, celý běh je fatal: target není zpracovaný ani
   `consumed`, ale v témže běhu se nesmí opakovat. Jakákoli chyba po tomto bodu
   zakazuje retry stejného targetu.
2. **Duplicitní `Reservation`:** objekt `Reservation` není identita eventu a
   nededuplikuje se podle jména, času, služby ani hodnotového porovnání. Jedna
   rezervace se přiřadí právě k jednomu prokázanému target key.
3. **Spotřebovaný target:** do `consumed_targets` přejde až po zaznamenání
   výsledku, potvrzeném bezpečném close a úspěšném post-event census odpovídajícím
   baseline. Pokud tato hranice nenastane, běh je fatal; target se neopakuje.

Porovnání možných hranic:

| Okamžik | Proč nestačí / důsledek |
| --- | --- |
| Po získání handle | Neproběhla interakce a handle může být před clickem odpojen. |
| Po event clicku | Není známo, zda click otevřel očekávaný detail. Target je pouze `attempted`, ne `consumed`. |
| Po potvrzení detailu | Je znám typ povrchu, ale detail je stále otevřený. |
| Po klasifikaci | Stále chybí výsledek zpracování a bezpečný návrat ke kalendáři. |
| Po parsování | Parsování neprokazuje zavření ani stabilitu kalendáře. |
| Po bezpečném zavření | Ještě chybí post-event census; DOM mohl být změněn. |
| Po úspěšném post-event census | Nejbezpečnější hranice, pokud je výsledek zaznamenán a target má stabilní prokázanou identitu. |

Vybraná hranice je poslední řádek. Parser chyba může být recoverable teprve po
budoucím oddělení parsování od close a pouze pokud se známý detail bezpečně zavře,
close se potvrdí a post-census je stabilní. Chyba výpisu je fatal; výpis může být
částečný a současný tok jej nemá bezpečně transakční. Doporučený day loop proto
nejprve sestaví in-memory výsledek a teprve po `DAY_COMPLETED` jej formátuje.
Známá neklientská událost může pokračovat pouze po svém prokázaném close kontraktu
a stejné hranici spotřebování. Pokud click proběhl, ale detail nelze potvrdit,
target zůstane `attempted`, další click je zakázán a celý den končí.
Totéž platí pro `UNKNOWN_DETAIL`: target zůstane `attempted`, nikdy `consumed`.

Bez stabilní anonymní identity nelze výše uvedenou prevenci spolehlivě prokázat.
To je `BLOCKER`, nikoli důvod deduplikovat podle osobních dat.

## Klasifikace detailu

Klasifikace probíhá až po event clicku a pouze podle jednoznačné známé struktury
otevřeného detailu. Nikdy nepoužívá calendar text, barvu, geometrii, velikost ani
absenci klientského jména.

| Klasifikace | Význam | Automatický close | Pokračování | Bucket výsledku |
| --- | --- | --- | --- | --- |
| `SUPPORTED_RESERVATION` | Právě jeden detail odpovídá známému HEADER–CONTENT–ACTION kontraktu rezervace. | Ano, pouze existujícím strukturálně ověřeným close prvkem; následně potvrdit zmizení detailu. | Ano jen po výsledku, close confirmation a stabilním post-census. | `reservations`, nebo sanitizovaná recoverable `errors` po splnění všech podmínek. |
| `KNOWN_NONCLIENT_EVENT` | Detail odpovídá samostatně prokázanému neklientskému kontraktu. Dnes `UNPROVEN`. | Teprve po prokázání jeho vlastního jednoznačného close kontraktu. | Teprve po potvrzeném close a stabilním post-census. | `skipped_items`; nejde o rezervaci ani automatický error. |
| `UNKNOWN_DETAIL` | Otevřený povrch neodpovídá žádnému známému kontraktu. Nesmí se automaticky označit za blokaci. | Ne. | Ne; celý run končí a BrowserContext se zavře. | Fatal `errors`. |
| `DETAIL_NOT_OPENED` | V timeoutu se nepotvrdil žádný detail; výsledek clicku je neznámý. | Ne. | Ne. | Fatal `errors`. |
| `AMBIGUOUS_DETAIL` | Je přítomen více než jeden odpovídající nebo konfliktní detail/povrch. | Ne. | Ne. | Fatal `errors`. |

`UNKNOWN_DETAIL` je v Phase 4C fatal pro celý den. Zotavení je možné až v jiné
verzi po bezpečné anonymní diagnostice a implementaci přesného kontraktu. Ruční
zásah během automatického loopu se nepovoluje, protože by zneplatnil census a
identitu targetu.

## Recoverable a fatal chyby

Chyba je recoverable pouze při současném splnění všech podmínek:

- target má stabilní prokázanou anonymní identitu a je právě jednou `attempted`;
- detail byl jednoznačně klasifikován jako podporovaná rezervace nebo později
  bezpečně známý neklientský detail;
- chyba nepochází z event clicku, klasifikace, identity ani lifecycle vlastnictví;
- známý detail byl právě jednou bezpečně zavřen a zavření bylo potvrzeno;
- post-event census včetně identity a pořadí odpovídá baseline;
- výsledek chyby byl uložen pod pevným sanitizovaným kódem;
- nebyl překročen limit recoverable chyb.

Po potřebném refaktoru mohou být recoverable například validační nebo parser
chyba jednoho již známého rezervačního detailu a chyba rozbalení `Více`, pokud lze
detail následně bezpečně zavřít bez dalšího clicku na `Více`. V současném toku jsou
tyto případy `UNPROVEN` a mají být fatal, protože close po chybě není garantován.

Primární chyby mají pevné kódy. Nikdy se k nim nepřipojuje text DOM, locator ani
syrová Playwright výjimka:

| Situace | Kód |
| --- | --- |
| Nulu eventů nelze odlišit od neprokázané event layer | `DAY_EMPTY_EVENT_LAYER_UNPROVEN` |
| Změna baseline struktury, počtu nebo pořadí | `DAY_CALENDAR_STRUCTURE_CHANGED` |
| Chybějící nebo nejednoznačná identita | `DAY_EVENT_IDENTITY_AMBIGUOUS` |
| Čerstvý target nenalezen / nalezen vícekrát | `DAY_EVENT_HANDLE_NOT_FOUND` / `DAY_EVENT_HANDLE_AMBIGUOUS` |
| Event click selhal nebo má neznámý výsledek | `DAY_EVENT_CLICK_FAILED` |
| Detail se neotevřel | `DAY_DETAIL_NOT_OPENED` |
| Neznámý / víceznačný detail | `DAY_UNKNOWN_DETAIL` / `DAY_AMBIGUOUS_DETAIL` |
| Neizolovatelná chyba zpracování známého detailu | `DAY_DETAIL_PROCESSING_FAILED` |
| Close selhal / nebyl potvrzen | `DAY_DETAIL_CLOSE_FAILED` / `DAY_DETAIL_CLOSE_UNCONFIRMED` |
| Nejasné vlastnictví nebo dispose | `DAY_HANDLE_LIFECYCLE_FAILED` |
| Chyba výstupu | `DAY_OUTPUT_FAILED` |
| Přerušení uživatelem | `DAY_INTERRUPTED` |

Fatal jsou vždy:

- změna calendar fingerprintu, počtu, pořadí, vrstev nebo stabilních klíčů;
- event nelze jednoznačně čerstvě najít;
- click selže nebo má neznámý výsledek;
- `DETAIL_NOT_OPENED`, `UNKNOWN_DETAIL` nebo `AMBIGUOUS_DETAIL`;
- detail nelze bezpečně zavřít nebo close nelze potvrdit;
- lifecycle či vlastník handle je nejasný nebo dispose znemožní určit stav;
- hrozí duplicitní click nebo přeskočení eventu;
- chyba výstupu během loopu;
- překročení ochranného limitu;
- `KeyboardInterrupt`.

Po fatal chybě se neprovádí žádná další stránková interakce. Pouze se uvolní
vlastněné handly a ukončí BrowserContext. Požadavek „jedna chyba nezastaví
ostatní“ platí jen pro prokazatelně recoverable chyby; bezpečnost má přednost.

## Stavový automat

`0` znamená žádný click v daném stavu. `1 event` znamená nejvýše jeden pokus na
aktuální target. `≤10 Více` a `1 close` jsou oddělené existující bezpečné
interakce uvnitř známého detailu.

| Stav | Vstupy a povolené operace | Vlastněné handly | Click limit | Výstup / bezpečné chyby | Povinný cleanup |
| --- | --- | --- | --- | --- | --- |
| `WAITING_FOR_MANUAL_SETUP` | URL otevřená; uživatel ručně nastaví Den, dummy-only datum a zavřený detail; Enter. | Žádné. | 0 | `BASELINE_CENSUS`; přerušení → `FATAL_STOP`. | Context zavře outer scope. |
| `BASELINE_CENSUS` | Ověřit zavřený detail, načíst anonymní snapshot a vyřešit jediný Den/grid/event layer s 1 až 10 eventy. | Pouze krátkodobé interní JS handly census funkce. | 0 | `DAY_PLAN_CREATED`; nerozpoznaná prázdná event layer → `FATAL_STOP` s `DAY_EMPTY_EVENT_LAYER_UNPROVEN`; ambiguity/limit/otevřený detail → `FATAL_STOP`. | Dispose všech dočasných handlů. |
| `DAY_PLAN_CREATED` | Vytvořit immutable fingerprint a 1 až 10 ordinal targetů. Mutable attempted/consumed množiny patří runneru, nikoli plánu. | Žádné. | 0 | `PRE_EVENT_CENSUS`. Tento stav pro nulu eventů nevznikne. | Nic. |
| `PRE_EVENT_CENSUS` | Ověřit zavřený detail, limity, baseline ekvivalenci, stabilní klíče, pořadí a neattempted target. | Jen census temporaries. | 0 | `EVENT_HANDLE_ACQUIRED`; odchylka → `FATAL_STOP`. | Dispose temporaries. |
| `EVENT_HANDLE_ACQUIRED` | Atomicky získat právě jeden čerstvý viditelný handle. Bezprostředně před voláním clicku nevratně označit key jako attempted. Selhání po tomto zápisu, i když click ještě nebyl vyvolán, je fatal a target se neopakuje. | Právě jeden event `ElementHandle`. | 0 | `EVENT_CLICK_ATTEMPTED`; lookup/ownership nebo pre-click chyba → `FATAL_STOP`. | Při každém odchodu handle dispose; žádná další DOM interakce. |
| `EVENT_CLICK_ATTEMPTED` | Právě jednou kliknout a bez ohledu na výsledek ihned dispose handle. Stav po clicku je záměrně nejistý: nelze předpokládat otevřený detail ani bezpečný kalendář. | Do `finally` event handle, potom žádný. | 1 event | `DETAIL_CLASSIFICATION`; click/timeout/dispose nejistota → `FATAL_STOP`. | Event handle vždy dispose; žádný retry ani close naslepo. |
| `DETAIL_CLASSIFICATION` | Pollovat omezeně pouze známé strukturální kontrakty; nečíst calendar text. | Krátkodobé detailové handly vlastněné classifierem. | 0 | Rezervace → `RESERVATION_PROCESSING`; známý nonclient → `KNOWN_NONCLIENT_PROCESSING`; ostatní → `FATAL_STOP`. | Classifier uvolní všechny nevrácené handly; předaný známý detail má jednoho vlastníka. |
| `RESERVATION_PROCESSING` | Rozbalit jen přesné `Více`, extrahovat a parsovat v paměti; nezapisovat day výstup. | Jeden známý `DetailStructure` a vždy nejvýše jeden krátkodobý `Více` handle. | ≤10 `Více` | `DETAIL_CLOSE_CONFIRMATION`; bezpečně izolovatelná datová chyba může pokračovat jen budoucím close-on-error kontraktem, jinak `FATAL_STOP`. | Každý `Více` handle dispose; detail předat close stavu. |
| `KNOWN_NONCLIENT_PROCESSING` | Pouze explicitní, samostatně prokázaný kontrakt; žádná extrakce rezervace. | Jeden známý nonclient detail handle set. | 0 | `DETAIL_CLOSE_CONFIRMATION`; dnes je větev `BLOCKER`. | Předat přesně vlastněný detail close stavu. |
| `DETAIL_CLOSE_CONFIRMATION` | Najít právě jeden kontraktem ověřený close, jednou kliknout, potvrdit zmizení známého detailu. | Detail structure a právě jeden close handle. | 1 close | `POST_EVENT_CENSUS`; chyba close/confirmation → `FATAL_STOP`. | Dispose close i všech detail handlů. |
| `POST_EVENT_CENSUS` | Ověřit, že detail není otevřený; nový anonymní census; porovnat fingerprint, klíče a pořadí s baseline. | Jen census temporaries. | 0 | `EVENT_COMPLETED`; odchylka → `FATAL_STOP`. | Dispose temporaries. |
| `EVENT_COMPLETED` | Atomicky zaznamenat result a přesunout target z attempted logu do consumed setu; nikdy nemaže attempted. | Žádné. | 0 | Další target → `PRE_EVENT_CENSUS`; konec → `DAY_COMPLETED`; limit → `FATAL_STOP`. | Nic. |
| `DAY_COMPLETED` | Sestavit pouze in-memory day result. Automaticky nevypisovat osobní data; případné explicitní formátování je oddělený budoucí krok mimo loop. | Žádné. | 0 | Terminální úspěch. | BrowserContext zavře outer scope. |
| `FATAL_STOP` | Nevstupovat znovu do DOM a neklikat; vytvořit pouze sanitizovaný fatal výsledek. | Nanejvýš handly převzaté z přerušeného stavu. | 0 | Terminální chyba. | Dispose bez přepsání aktivní bezpečné chyby; programátorskou cleanup chybu neignorovat; při nejistotě zachovat fatal stav; vždy zavřít BrowserContext. |

Stav po event clicku je kritický: samotný návrat z `click()` neprokazuje otevření
detailu. Target je již nevratně `attempted`, ale není `consumed`. Selhání
klasifikace nevede k retry ani k obecnému close; vede do `FATAL_STOP`.

## Vlastnictví Playwright handlů

- Census funkce vlastní všechny své `JSHandle` a `ElementHandle` a vrací pouze
  immutable anonymní hodnoty.
- Day plan ani target nikdy neobsahují handle.
- Atomic event lookup vrátí právě jeden `ElementHandle`; vlastní jej stav
  `EVENT_HANDLE_ACQUIRED` a předá jej pouze `EVENT_CLICK_ATTEMPTED`.
- Event handle se uvolní v `finally` bezprostředně po jediném click pokusu.
- Classifier vlastní všechny dočasné kandidáty. Při jedné známé klasifikaci předá
  přesně jeden vlastněný detail processing stavu; ostatní uvolní.
- Detail processing nesmí cacheovat handle `Více`; po každé DOM změně získá nový
  kandidát a starý uvolní.
- Close handle se získá až z čerstvé známé struktury a po jednom clicku se uvolní.
- Playwright `Error` při dispose se nikdy nevypíše a nesmí překrýt již aktivní
  aplikační chybu. Pokud vznikne bez předchozí chyby a znejasní lifecycle day
  loopu, pokračování je zakázáno a výsledkem je sanitizovaný
  `DAY_HANDLE_LIFECYCLE_FAILED`.
- Programátorská chyba v cleanupu se nesmí svévolně ignorovat. Při aktivní
  aplikační chybě se zachová její bezpečný kód a cleanup chyba může zůstat pouze
  jako nevypsaná cause; bez aktivní chyby se převede na fatal lifecycle selhání.
  Žádná cleanup chyba nesmí vyvolat další DOM interakci.
- BrowserContext vlastní outer context manager a zavře se vždy jako poslední.

## Navržené datové struktury

Všechny struktury jsou pouze návrh; názvy polí mohou být při implementaci
upřesněny bez oslabení kontraktu.

| Struktura | Minimální pole | PII / tisk / `repr` | Mutabilita, vlastník, handle, disk |
| --- | --- | --- | --- |
| `DayStructureFingerprint` | pouze agregovaný anonymní grid a event-layer fingerprint a count; neobsahuje per-event key ani identitu | Bez PII; lze tisknout pouze omezené počty a boolean výsledky; `repr` ano | `frozen`; vlastní plan; bez handle; neukládat na disk v Phase 4C. |
| `EventSelectionTarget` | baseline ordinal jako pozice; volitelný stabilní anonymní key; očekávaný day fingerprint reference. `key=None` povoluje pouze no-click Phase 4C1. | Bez PII; key se nesmí tisknout, dokud není doložena jeho necitlivost; `repr=False` pro key | `frozen`; vlastní plan; bez handle; neukládat. |
| `DaySelectionPlan` | fingerprint, tuple targetů, limity, verze kontraktu | Bez PII; tisk jen count a verze; targety/keys mimo `repr` | `frozen`; vlastní day runner; bez handle; neukládat. |
| `DetailClassification` | enum pěti pevných klasifikací | Bez PII; tisk i `repr` ano | Enum immutable; vlastní classifier/result; bez handle; může být v sanitizovaném in-memory reportu, ne na disk v této fázi. |
| `EventDisposition` | enum `RESERVATION_OK`, `KNOWN_NONCLIENT_SKIPPED`, `RECOVERABLE_FAILURE`, `FATAL_FAILURE` | Bez PII; tisk i `repr` ano | Enum immutable; vlastní result; bez handle; pouze paměť. |
| `EventFailure` | baseline ordinal jako anonymní target reference, pevný error code, fatal boolean, state enum; žádná hodnota stable key | Bez PII; tisk pouze ordinal/code/state; `repr` ano, nikdy key, exception text, DOM text ani locator | `frozen`; vlastní event/day result; bez handle; pouze paměť. |
| `EventProcessingResult` | target reference, disposition, volitelná `Reservation`, volitelný `EventFailure` | `Reservation` a `raw_detail` mohou obsahovat PII; celé reservation pole `repr=False`; sanitizovaná metadata lze tisknout | `frozen`; vlastní day result; bez handle; pouze paměť. |
| `DayProcessingResult` | tuple event výsledků, tuple rezervací nebo odvozený přístup, completed, fatal failure, counts | Obsahuje PII transitivně; reservations/results `repr=False`; tisknout jen counts a fixed codes, nikoli data, dokud uživatel výslovně nezvolí terminálový výstup | `frozen`; vlastní caller; bez handle; pouze paměť, žádný export v Phase 4C. |

`attempted_targets` a `consumed_targets` jsou interní in-memory stav runneru, ne
součást dlouhodobého plánu. Obsahují pouze prokázané anonymní keys. Pokud key
nelze bezpečně získat, loop se nesmí spustit.

## Pseudokód

```text
otevři persistentní BrowserContext v outer context manageru
try:
    vyzvi uživatele, aby ručně zvolil pohled Den a dummy-only datum
    vyžaduj, aby detail zůstal zavřený; počkej na Enter

    assert_no_open_detail()
    baseline = fresh_anonymous_census()
    validate_day_view_unique_layers_and_event_count_1_to_10(baseline)
    require_proven_stable_event_identity(baseline)  # pro click loop; jinak BLOCKER
    plan = immutable_day_plan(baseline)
    attempted = empty_set()
    consumed = empty_set()
    results = empty_list()

    for target in plan.targets_in_baseline_dom_order:
        enforce_global_limits()
        assert_no_open_detail()
        before = fresh_anonymous_census()
        require_exact_baseline_structure_identity_and_order(before, plan)
        require(target.key not in attempted and target.key not in consumed)

        event_handle = atomic_find_one_fresh_visible_event(before, target.key)
        attempted.add(target.key)  # nevratná hranice bezprostředně před click
        try:
            event_handle.click_once_with_bounded_timeout()
        finally:
            dispose(event_handle)
        # Selhání po attempted.add, i před skutečným vyvoláním click, je fatal.

        classification, owned_detail = classify_one_open_detail_with_timeout()
        if classification == DETAIL_NOT_OPENED:
            fatal("DAY_DETAIL_NOT_OPENED")
        if classification == UNKNOWN_DETAIL:
            fatal_without_close("DAY_UNKNOWN_DETAIL")
        if classification == AMBIGUOUS_DETAIL:
            fatal_without_close("DAY_AMBIGUOUS_DETAIL")

        if classification == SUPPORTED_RESERVATION:
            outcome = process_known_reservation_in_memory(
                owned_detail,
                max_more_expansions=10,
                no_event_retry=True,
            )
        else if classification == KNOWN_NONCLIENT_EVENT:
            require_proven_nonclient_contract()
            outcome = record_known_nonclient_skip_in_memory(owned_detail)

        pending_result = sanitized_event_result(target, outcome)  # pouze paměť

        close_control = find_exactly_one_contract_verified_close(owned_detail)
        close_control.click_once_with_bounded_timeout()
        dispose(close_control)
        confirm_known_detail_closed_with_bounded_timeout()
        dispose_all_detail_handles(owned_detail)

        after = fresh_anonymous_census()
        require_exact_baseline_structure_identity_and_order(after, plan)
        require_no_open_detail()

        results.append(pending_result)
        consumed.add(target.key)  # pouze zde, po stabilním post-census

    require(consumed == set(plan.target_keys))
    return in_memory_day_result(results)
finally:
    dispose_owned_handles_preserving_primary_error_or_failing_lifecycle()
    close_BrowserContext()
```

Pseudokód záměrně neobsahuje retry event clicku, force nebo JavaScriptový click,
souřadnice, `Escape`, screenshot, OCR, CSS třídy, ID, ukládání HTML ani
automatickou navigaci na datum.

## Ochranné limity

První click-capable implementace má být záměrně malá:

| Limit | Návrh | Sanitizovaný kód při překročení |
| --- | ---: | --- |
| Event blocky v jednom dni | 1 až 10 | nula: `DAY_EMPTY_EVENT_LAYER_UNPROVEN`; více než 10: `DAY_EVENT_LIMIT_EXCEEDED` |
| Zpracované eventy | 10 | `DAY_PROCESSED_LIMIT_EXCEEDED` |
| Event click pokusy | 10, přesně nejvýše jeden na target | `DAY_EVENT_CLICK_LIMIT_EXCEEDED` |
| Otevření detailu | 3 s na target | `DAY_DETAIL_NOT_OPENED` |
| Zavření detailu | 3 s na target | `DAY_DETAIL_CLOSE_UNCONFIRMED` |
| Rozbalení `Více` | 10 na známý detail | `DAY_MORE_LIMIT_EXCEEDED` |
| Censusy | 21: jeden baseline a dva na každý z 10 eventů | `DAY_CENSUS_LIMIT_EXCEEDED` |
| Recoverable chyby | 3 | `DAY_RECOVERABLE_LIMIT_EXCEEDED` |
| Close click | 1 na známý otevřený detail | `DAY_CLOSE_CLICK_LIMIT_EXCEEDED` |

Timeouty používají monotonic clock a nezáporný polling interval. Překročení
limitu je fatal; nezpůsobí retry ani další close, pokud close nebyl již samostatně
bezpečně zahájen na známém detailu. Limity se mohou později změnit pouze na základě
testů a zdokumentovaného bezpečnostního review.

## Unit testovací plán

Povinný rozsah prvního PR Phase 4C1 je výhradně no-click:

- plán pro 1, 2, 3 a 10 eventů; 11 eventů odmítnuto pevným kódem;
- zcela prázdný den a chybějící event layer skončí
  `DAY_EMPTY_EVENT_LAYER_UNPROVEN`; žádná prázdná vrstva se nevybere;
- ne-Den pohled se odmítne;
- víceznačný context, grid nebo event layer se odmítne bez výběru první shody;
- immutable plan a target bez Playwright handle;
- fingerprint obsahuje pouze anonymní strukturální hodnoty;
- ordinal je pouze baseline pozice a není mezisnapshotová identita;
- `EventSelectionTarget` v Phase 4C1 nemá stable key ani handle;
- sanitizované chyby neobsahují snapshot `repr` ani DOM data;
- žádný click ani získání event handle.

Následující unit scénáře patří do diagnostického gate nebo Phase 4C2–4C4:

- stabilní keys jedinečné, úplné a ve stejném pořadí;
- změněný fingerprint, count, key nebo pořadí je fatal před clickem;
- target se před clickem označí attempted a nikdy se neretryuje;
- target je consumed jen po výsledku, potvrzeném close a post-census;
- parser chyba je recoverable pouze při splnění celého close/post-census
  kontraktu; jinak fatal;
- výstupní chyba je fatal a nevede k dalšímu eventu;
- známý nonclient je povolen jen s explicitním kontraktem;
- neznámý, neotevřený a ambiguous detail jsou fatal bez close clicku;
- přerušení nezpůsobí duplicitní event click;
- limity clicků, censusů a recoverable chyb;
- všechny event, detail, `Více` a close handly jsou uvolněny při úspěchu i chybě;
- dispose chyba během původní aplikační chyby nepřepíše původní pevný kód a
  nevyvolá interakci;
- `KeyboardInterrupt` zavře context;
- všechny výjimky a `repr` jsou sanitizované a neobsahují testovací detail;
- kontrola, že v produkci nevznikl další interaktivní typ mimo event, `Více` a
  ověřený close.

## Syntetický browserový testovací plán

Testy používají pouze lokální `page.set_content()` se smyšleným minimalistickým
DOM, blokují všechny síťové požadavky a nekopírují produkční HTML, CSS třídy ani
ID.

Povinný rozsah prvního PR Phase 4C1 je výhradně no-click:

- Den se 2, 3 a 10 eventy a immutable ordinal plánem;
- 11 eventů odmítnuto pevným kódem;
- prázdný den odmítnut `DAY_EMPTY_EVENT_LAYER_UNPROVEN` bez výběru prázdné vrstvy;
- nested equivalent grid anchors se kanonizují, dva nezávislé gridy se odmítnou;
- dvě event vrstvy se odmítnou a nevybere se první;
- žádný `click()`;
- žádný `evaluate_handle()` vracející event ani jiný event handle;
- žádná síť a pouze syntetické HTML.

Následující scénáře jsou plánem pro diagnostický gate nebo Phase 4C2, nikoli
rozsahem Phase 4C1:

- click-capable Den se dvěma event blocky;
- click-capable Den se třemi event blocky v deterministickém DOM pořadí;
- fresh census a fresh handle před každým targetem;
- DOM nahrazený ekvivalentní kopií: bez stabilního key musí být fatal, se
  prokázaným key lze znovu najít právě jeden target;
- prohození dvou eventů je fatal, i když count zůstane stejný;
- přidání a odebrání eventu během běhu je fatal;
- odpojený target a dva odpovídající targety jsou fatal bez click retry;
- změněná nebo víceznačná event layer je fatal;
- známý rezervaci podobný detail projde jen přes úplný strukturální kontrakt;
- známý nonclient fixture bude přidán až po samostatném kontraktu;
- neznámý detail nekončí close clickem a ukončí run;
- nepotvrzené zavření zastaví run před dalším census/clickem podle přesně
  definovaného stavu;
- parser chyba se synteticky izoluje jen po ověřeném close a stabilním census;
- starý target se po chybě nikdy neklikne podruhé;
- žádný síťový požadavek;
- všechny `JSHandle` a `ElementHandle` jsou po scénáři uvolněné.

Syntetické testy mohou prokázat chování algoritmu, nikoli stabilitu skutečného DOM
Termino. Ta vyžaduje zvláštní anonymní diagnostický gate.

## Budoucí ruční test

Ruční test je gate až po unit a syntetických testech a po odstranění identity
blokátoru. Uživatel vytvoří den obsahující výhradně zjevně dummy položky:

- `TEST OSOBA 1`;
- `TEST OSOBA 2`;
- `TEST UDÁLOST`;
- `TESTOVACÍ POZNÁMKA`;
- `test@example.invalid`.

Nejdříve se odděleně spustí read-only diagnostika identity bez clicku nástroje;
uživatel případné otevření a zavření provede ručně. Teprve po úspěšném review se
smí jednou spustit click-capable flow na dni s několika podporovanými dummy
rezervacemi. Neznámý detail, změna census nebo nejistý close musí běh ukončit.
Test nesmí používat skutečné služby, pracoviště, zaměstnance, telefon, jméno ani
text živé rezervace.

## Rozdělení do implementačních PR

1. **Phase 4C1 — anonymní plán více eventů bez kliknutí.** Pouze Den s 1 až 10
   prokázanými event blocky; čisté immutable datové modely, vytvoření plánu z
   anonymního snapshotu, validace pohledu, contextu, gridu, event layer, počtu a
   limitů, anonymní fingerprint a ordinal targety označené pouze jako baseline
   pozice. Unit a syntetické Chromium testy jsou no-click. Phase 4C1 nevrací ani
   nezískává `ElementHandle`, neotevírá ani neklasifikuje detail, nepřidává
   day-processing loop, close, stable key, podporu blokací ani nový produkční
   interaktivní bod. Nepřidává nový CLI příkaz; poskytne čisté API pro testy a
   budoucí diagnostický gate.
2. **Phase 4C diagnostic gate — stabilita identity.** Samostatná read-only
   diagnostika na dummy-only dni; omezené boolean/count výstupy, ruční otevření a
   zavření, žádný text ani atributové hodnoty. Výsledkem je důkaz stabilního
   anonymního klíče, nebo zachovaný `BLOCKER`.
3. **Phase 4C2 — více známých dummy rezervací.** Až po identity gate. Fresh census
   před a po každém eventu, jeden event click na key, stop při neznámém detailu;
   žádné blokace.
4. **Phase 4C3 — známé neklientské události.** Až po odděleném anonymním pozorování
   jejich struktury, explicitní klasifikaci a close kontraktu. Žádné heuristiky
   podle event textu nebo vzhledu.
5. **Phase 4C4 — izolace recoverable chyb.** Nejdříve oddělit in-memory zpracování
   od výstupu a garantovat close-on-known-error; pokračovat pouze po close
   confirmation a stabilním post-census.

Jediný doporučený první implementační PR je **Phase 4C1 — anonymní plán více
eventů bez kliknutí**. Je bezpečně testovatelný s aktuálními znalostmi a
nepředstírá vyřešenou identitu.

## Dokumentační nesrovnalosti

V tomto návrhovém kroku se jiné dokumenty nemění. Budoucí samostatná dokumentační
oprava má:

- v `ROADMAP.md` nahradit historickou větu, že hardeningem Phase 4 nebyla
  zahájena, přesným stavem dokončených Phase 4A a 4B;
- v `ROADMAP.md` a `README.md` oddělit synteticky podporované gridové pohledy od
  produkčně povoleného pohledu Den; Agenda není současná schopnost Phase 4B;
- v `SPEC.md` nahradit popis krokového scrollování a textové deduplikace aktuálním
  tokem rozbalení přesného `Více` a čtení současného DOM;
- ve specifikaci výslovně uvést, že `UNKNOWN_DETAIL` se automaticky nezavírá a je
  fatal pro day loop;
- v `docs/PHASE4A_CALENDAR_DIAGNOSTIC.md` odstranit historické tvrzení, že Phase
  4B ještě není implementována;
- doplnit, že ordinal v census snapshotu není persistentní identita eventu.

## Rozhodnutí

1. **Lze Phase 4C implementovat bezpečně pouze s aktuálními znalostmi?** Pouze
   Phase 4C1 pro 1 až 10 eventů bez clicku. Prázdný den a celý click-capable day
   loop ne: `UNPROVEN`, `BLOCKER` kvůli event layer, identitě eventů a neznámým
   neklientským strukturám.
2. **Lze bezpečně cílit druhý a další event bez stabilního atributového ID?** S
   dnešními důkazy ne. Teoreticky ano jen s jiným stejně silným důkazem identity a
   pořadí; ten nyní chybí: `UNPROVEN`, `BLOCKER`.
3. **Je DOM ordinal bezpečný pouze při neměnném baseline fingerprintu?** Neměnný
   fingerprint je nutný, ale dnešní agregovaný fingerprint není dostačující.
   Ordinal je mezi censusy bezpečný pouze spolu s prokázanou per-event identitou a
   pořadím: `UNPROVEN`.
4. **Kdy je target spotřebován?** Až po zaznamenání výsledku, bezpečném close,
   potvrzení zavření a úspěšném post-event census shodném s baseline včetně
   identity a pořadí. Předtím je po click hranici pouze nevratně `attempted`.
5. **Které chyby jsou recoverable?** Jen datová chyba uvnitř jednoznačně známého
   detailu, po které je detail bezpečně zavřen, close potvrzen, target prokázán a
   post-census stabilní. Současný detailový tok to obecně negarantuje, tedy
   konkrétní seznam je pro implementaci 4C4 zatím `UNPROVEN`.
6. **Které chyby okamžitě zastaví celý den?** Změna fingerprintu/count/order/key,
   ambiguity, chybějící target, nejistý click, neotevřený/neznámý/ambiguous detail,
   nejistý close, lifecycle nejistota, duplicita/skip riziko, výstupní chyba,
   limit nebo přerušení.
7. **Lze pokračovat po `UNKNOWN_DETAIL`?** Ne. Nezavírá se a celý BrowserContext se
   ukončí. Zotavení vyžaduje samostatnou budoucí diagnostiku a nový známý
   kontrakt.
8. **Lze bezpečně přeskočit blokaci bez znalosti její detailové struktury?** Ne:
   `BLOCKER`. Neznámý detail nelze prohlásit za blokaci ani bezpečně zavřít.
9. **Je před loopem nutná další read-only diagnostická fáze?** Ano: identita a
   pořadí více eventů; pro neklientské události navíc oddělená diagnostika jejich
   detailu a close kontraktu.
10. **Jaký je nejmenší bezpečný první implementační PR?** Phase 4C1: immutable
    anonymní multi-event day plan pro 1 až 10 eventů, limity a syntetické testy,
    bez handle, CLI a jediného clicku. Nula eventů zůstává `BLOCKER`.

## Doporučený další krok

Implementovat pouze Phase 4C1. PR má rozšířit čistý Python model nad anonymním
census snapshotem pro 1 až 10 eventů v pohledu Den, vytvořit immutable plán a
ověřit jeho limity a strukturální fingerprint. Nesmí přidat event loop ani nové
produkční `click()` místo, event handle, stable key nebo CLI příkaz. Prázdný den
musí skončit `DAY_EMPTY_EVENT_LAYER_UNPROVEN`, dokud samostatný no-click důkaz nebo
resolverová mezifáze nezavede jednoznačný bezpečnostní kontrakt.

Po review Phase 4C1 má následovat samostatná read-only diagnostická mezifáze
stability identity na dummy-only dni. Teprve pozitivní, anonymní a opakovatelný
důkaz smí odblokovat návrh Phase 4C2. Pokud stabilní bezpečný klíč nebude nalezen,
automatické zpracování druhého a dalšího eventu zůstane záměrně nepovoleno.
