# Phase 4C-ID0/ID1 — návrh diagnostiky identity eventů

Tento dokument definuje samostatnou diagnostickou mezifázi mezi Phase 4C1 a
Phase 4C2. Neimplementuje ji, nepřidává produkční příkaz a nepovoluje
multi-event processing. Výchozí blokátor
`EVENT_STABLE_IDENTITY_UNKNOWN` zůstává aktivní, dokud neprojdou odděleně
technický důkaz ID0 a sémantický/privacy důkaz ID1.

Návrh záměrně netvrdí, že Termino používá některý konkrétní atribut. Phase
4C-ID0 však z důvodu fail-closed privacy testuje pouze source-controlled
allowlist předem schválených generických názvů atributů definovaný níže. Žádný
runtime objevený název nesmí opustit browser execution context. Technicky
stabilní allowlisted kandidát není schválená identita a ID0 nikdy nevrací
verdict `PROVEN`.

## Terminologie a hranice důkazu

- **Candidate attribute name** je předem reviewovaný generický název ze
  source-controlled allowlistu a je testován pouze přímo na event root elementu.
  ID0 smí vypsat jen takový název; runtime objevený název kandidátem není.
- **Candidate attribute value** je runtime hodnota atributu. Nikdy se nesmí
  vypsat, logovat, persistovat, přidat do výjimky ani přenést do běžného Python
  result objektu.
- **Technically stable candidate** je atribut, který splnil pouze technické
  podmínky ID0. Nejde o potvrzení anonymity ani o `stable_event_key`.
- **Approved stable_event_key** může vzniknout až v samostatném ID1 kroku po
  technickém i sémantickém/privacy důkazu a explicitním review.
- **Baseline ordinal** je pozice elementu v jediném census. Není identita a
  nepoužívá se pro porovnání eventů mezi censusy.
- **DOM node continuity** je pouze pomocná anonymní metrika, zda browser při
  ručním otevření či zavření zachoval stejné uzly. Není podmínkou technické
  stability atributu a nesmí být použita jako event key.

Technická stabilita hodnoty, neprůhledný formát, UUID, hash ani fakt, že hodnota
není vypsána, samy o sobě neprokazují, že atribut neobsahuje osobní nebo
provozně citlivé údaje.

## Rozdělení gate

### Phase 4C-ID0 — allowlisted candidate verification

ID0 je read-only diagnostika dummy-only dne se dvěma až deseti eventy. Provede
přesně tři čerstvé censusy: baseline, po ručním otevření detailu a po ručním
zavření detailu. Zjišťuje pouze technickou přítomnost, tvar, jedinečnost a
stabilitu předem nominovaných allowlisted atributů. Původní význam „candidate
discovery“ se tím úmyslně zužuje: ID0 nové názvy neobjevuje, nezveřejňuje ani
nenavrhuje. Bezpečnost názvů má přednost před zachováním původního názvu
diagnostiky.

ID0 může skončit nalezením nula, jednoho nebo více technicky stabilních
kandidátů. Žádný z nich automaticky nevybírá a blokátor
`EVENT_STABLE_IDENTITY_UNKNOWN` vždy zachová.

### Phase 4C-ID1 — candidate approval/proof

ID1 je budoucí samostatný design a implementační krok. Přijme právě jeden
konkrétní candidate attribute name, který člověk explicitně vybere z úspěšného
ID0 výstupu. ID1 znovu ověří technický kontrakt pro tento jediný název a současně
vyžaduje nezávislý důkaz významu, původu a citlivosti hodnot.

ID1 nesmí schválit kandidáta pouze podle názvu, formátu hodnoty, shody hashů,
UUID-like tvaru nebo jednoho úspěšného ID0 běhu.

## Budoucí ID0 entrypoint

Budoucí implementace přidá explicitní CLI příkaz:

```text
termino-exporter diagnose-event-identity-candidates --dummy-only
```

Příkaz použije stejné bezpečné volby `--url`, `--profile-dir` a
`--timeout-seconds` jako stávající diagnostické příkazy. Přepínač
`--dummy-only` je povinné vědomé potvrzení. Bez něj se prohlížeč neotevře a
příkaz skončí kódem `ID0_DUMMY_ONLY_ACK_REQUIRED`.

Příkaz nepřijímá jméno kandidátního atributu. Testovaná jména určuje výhradně
source-controlled allowlist; ID0 je technické ověření, nikoli approval.
Příkaz nevytváří výstupní soubor a nemá volbu pro HTML, screenshot, trace,
video nebo HAR. BrowserContext vlastní výhradně ID0 worker popsaný níže. Worker
se jej na každé cestě nejdříve pokusí korektně uzavřít; host supervisor vynutí
deadline a při zatuhnutí požádá Windows o ukončení celého izolovaného process
tree. Dokončené ukončení se tvrdí pouze po potvrzení `ActiveProcesses == 0`.

Procesní exit kódy budou:

| Exit code | Význam |
| ---: | --- |
| `0` | ID0 doběhlo do pozitivního found-unapproved nebo legitimního negativního no-candidate result code. |
| `1` | Libovolný fatal diagnostic code, včetně interní, cleanup, close nebo output chyby. |
| `2` | Neplatná syntaxe argumentů; vypsán pouze `ID0_INVALID_ARGUMENTS`. `--help` končí `0` s pevným bounded help textem. |
| `130` | `KeyboardInterrupt`, vypsán pouze `ID0_INTERRUPTED`. |

## Přesný manuální workflow ID0

1. Parent CLI ověří `--dummy-only`, bezpečnou cestu browser profilu a podporované
   Windows prostředí. Bez potvrzení `--dummy-only` nespustí worker ani browser.
2. Ještě před vytvořením workeru parent vypíše právě tři pevné očíslované řádky:
   baseline setup a Enter, ruční otevření známé dummy rezervace a Enter, ruční
   zavření téhož detailu a Enter. První řádek výslovně požaduje pohled Den, datum
   obsahující výhradně zjevně testovací rezervace, dva až deset eventů, žádný
   otevřený známý rezervační detail a zákaz `Upravit`, `Odstranit` i
   `Zkopírovat rezervaci`.
3. ID0 worker otevře viditelný persistentní BrowserContext a zadanou URL. Sám
   neprovede žádnou stránkovou interakci kromě navigace na URL a DOM čtení.
4. Uživatel se ručně přihlásí a provede baseline setup podle prvního řádku. Na
   login a tento setup má před vznikem raw state neomezený čas.
5. Enter pouze požádá o baseline kontrolu. Worker nejdříve zavolá existující
   `find_detail_structure()` bez extrakce a bez parsování. Nalezený známý detail,
   nejednoznačná struktura nebo Playwright nejistota jsou fatal. Diagnostika nic
   nezavírá. Teprve potvrzený stav bez známého detailu dovolí validovat calendar
   structure, pohled Den a 2..10 eventů a vytvořit baseline private state.
6. Uživatel podle druhého již vypsaného řádku ručně otevře právě jednu známou
   dummy rezervaci. ID0 live workflow je výslovně omezen na již podporovaný
   rezervační detail; obecný nebo neklientský detail není podporovaný. Program
   nevybírá event a nekliká.
7. Enter pouze spustí kontrolu. Worker musí pomocí `find_detail_structure()` potvrdit
   právě jeden známý HEADER–CONTENT–ACTION detail a všechny vrácené handly ihned
   uvolnit. Nevolá extrakci polí, `inner_text`, parser ani `inspect_open_detail`.
   Nenalezený, neznámý, nejednoznačný nebo Playwrightem nepotvrzený detail je
   fatal bez candidate verdictu a nikdy se automaticky nezavírá. Až poté proběhne
   druhý atomický census.
8. Uživatel podle třetího již vypsaného řádku tentýž detail ručně zavře běžným
   ovládacím prvkem UI. Program nepoužije close click ani `Escape`.
9. Enter znovu pouze spustí kontrolu. Wrapper nad `find_detail_structure()` musí
   zachytit `ReservationExtractionError.code` přesně
   `DETAIL_STRUCTURE_NOT_FOUND`; nalezený nebo nejednoznačný známý detail i
   Playwright nejistota jsou fatal bez candidate verdictu. Až poté proběhne třetí
   atomický census.
10. Browserový private-state handler porovná transientní hodnoty a vrátí pouze
    sanitizovaný bounded plain payload. Candidate technical verdict smí vzniknout
    jen po prokázané sekvenci `known detail absent -> known detail open -> known
    detail absent`.
11. Worker payload striktně zvaliduje. Parent jej zatím pouze bufferuje, nechá
    odstranit private state, korektně zavřít BrowserContext a ukončit worker.
    Parent samostatně potvrdí nulový počet aktivních procesů v Job Objectu a
    teprve po úspěšném cleanupu a graceful shutdownu vytvoří immutable result a
    vypíše povolená pole.

`--dummy-only` je povinný uživatelský safety prerequisite, nikoli tvrzení, že ID0
obsah dne automaticky ověřilo. Diagnostika z kalendářních ani detailových dat
dummy-only skutečnost nezjišťuje. Pre-baseline potvrzení zůstává bez timeoutu,
protože raw state ještě neexistuje. Oba manuální kroky po baseline mají pevné
host-side deadline definované níže.

## Získání event rootů

ID0 nebude přidávat nový CSS selector eventů. Event rooty získá uvnitř jednoho
atomického browserového průchodu stejným strukturálním kontraktem jako současný
`CALENDAR_DIAGNOSIS_SCRIPT` a `create_day_selection_plan()`:

1. najít a kanonizovat grid anchor přes přesnou roli `gridcell`;
2. vyžadovat právě jeden calendar context a jednu kanonickou grid vrstvu;
3. vyžadovat pohled Den, tedy právě jednu větev;
4. vybrat právě jednu event layer až za grid vrstvou podle současných
   strukturálních pravidel;
5. získat dva až deset viditelných event rootů přes současné
   `blocksForBranch()` pravidlo;
6. atomicky porovnat grid/event layer fingerprint a event count s baseline
   plánem před čtením atributů.

Implementace má rozšířit centralizovaný browserový resolver o explicitní ID0
mode nebo vyčlenit jeho sdílené read-only resolverové primitivy. Nesmí vytvořit
druhý odlišný event selector, který by se mohl rozejít s calendar resolverem.
Stávající calendar census a Phase 4B handle mode musí zůstat behaviorálně
beze změny.

Žádný census nevrací `ElementHandle`, event element ani DOM snapshot. Event rooty
existují pouze jako lokální proměnné uvnitř jednoho browserového vyhodnocení.

## Source-controlled allowlist názvů

ID0 zkoumá pouze atributy přímo na event root elementu. Atributy potomků se
nezjišťují. Descendant varianta je zamítnuta, protože není prokázáno, který
potomek je stabilní, násobí kandidáty a zvyšuje riziko čtení labelů nebo
klientských hodnot.

Jediný normativní privacy mechanismus pro názvy je varianta A: přesný
source-controlled allowlist. Jeho počáteční obsah je:

```text
data-event-id
data-event-key
```

Tyto dva názvy byly předem schváleny pouze jako generické a samy neobsahující
osobní ani provozní data. Toto schválení názvu nic netvrdí o existenci atributu
v Termino, významu nebo bezpečnosti jeho hodnoty. Změna allowlistu je změnou
tohoto bezpečnostního kontraktu a vyžaduje samostatný privacy review zdrojového
kódu/specifikace před spuštěním; runtime jej nesmí rozšířit.

Browserový census nesmí enumerovat, kopírovat ani vracet názvy ostatních root
atributů. Pro bounds smí přečíst pouze číselné `attributes.length`; jednotlivě
smí přes `hasAttribute`/`getAttribute` adresovat výhradně dva přesné allowlisted
názvy výše. Nalezený neallowlisted název, například název obsahující osobní nebo
ticketové údaje, se nečte, nehashuje, nepseudonymizuje, neklasifikuje a nikde se
nepublikuje. Regex, denylist, prefix, suffix ani délka nejsou privacy důkazem a
pro rozhodnutí o publikaci názvu se nepoužijí.

Invariant je fail-closed: žádný runtime-discovered attribute name nesmí opustit
browser execution context, pokud jeho přesný název nebyl předem schválen v tomto
allowlistu. Public payload a Python deserializer přijmou pouze exact členy tohoto
allowlistu; jiný název znamená `ID0_INVALID_SANITIZED_PAYLOAD` bez jeho `repr`.
ID0 technicky otestuje oba nominované názvy a může je vykázat jako absent nebo
technicky stabilní, nikdy však nevytváří `approved stable_event_key`. ID1 stále
vyžaduje samostatný semantic/privacy důkaz právě jedné hodnotové identity.

## Value-shape kontrakt ID0

Raw value se hodnotí pouze technicky a pouze v browserové paměti. Pro každý
event a candidate name musí:

- atribut skutečně existovat na rootu;
- hodnota být string délky 1 až 128 znaků;
- hodnota být shodná se svým `trim()` výsledkem;
- hodnota odpovídat `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`;
- porovnání probíhat case-sensitive nad přesnou raw hodnotou, bez normalizace;
- hodnota nebýt nahrazena hashem, digestem ani substringem pro výstup.

Tento tvar omezuje objem a vylučuje zjevný volný text, Unicode labely, HTML a
mezery. Nevylučuje ale například číselný osobní údaj, opaque backend ID nebo
UUID. Proto value-shape nikdy není semantic/privacy důkaz.

## Raw-value ownership

Zvolena je varianta **browser-only closure state bez `JSHandle`**. Kandidátní raw
values nikdy nejsou hodnotou vrácenou z `page.evaluate()`, argumentem poslaným do
Pythonu, remote-object preview ani vlastností objektu reprezentovaného v Pythonu.
ID0 candidate cesta nesmí zavolat `page.evaluate_handle()`,
`JSHandle.evaluate_handle()`, `get_property()`, `get_properties()` ani
`json_value()`.

### Přesný private-state mechanismus

1. Worker před baseline vygeneruje pomocí `secrets.token_hex(32)` jednorázový
   64znakový channel token. Token není candidate name ani value, nevypisuje se a
   zůstává pouze v worker Pythonu. Event type je pevný prefix
   `termino-exporter:id0:` následovaný tokenem.
2. Jediný baseline `page.evaluate()` provede resolver, ověří všechny bounds a
   vytvoří lexical closure. V closure jsou přesné baseline value arrays podle
   candidate name, bounded sanitizovaná metadata, current stage a `WeakMap`
   baseline event rootů na census-local pozice.
3. Baseline skript registruje na `window` právě jeden listener uvedeného náhodného
   event type. Raw state je dosažitelný pouze z lexical closure listeneru. Není
   přiřazen k `window`, `document`, DOM uzlu, `Symbol`, string property, datasetu,
   elementu ani jinému enumerovatelnému containeru. Listener ani jeho closure se
   nikdy neenumerují do výstupu.
4. Baseline evaluate vrátí pouze plain public payload vytvořený explicitní
   projekcí fixed keys: stage code, booleany, bounded counts a pouze exact
   source-controlled allowlisted candidate names. Funkce sestavující public payload nemá parametr
   ani property pro raw value a nesmí použít spread, `Object.assign`, JSON
   serializaci private state ani generické kopírování vlastností.
5. Druhý a třetí `page.evaluate()` obdrží pouze channel token a jeden fixed command.
   Vytvoří neperzistentní `Event`, synchronně jej dispatchují a vrátí pouze
   explicitně projektovanou sanitizovanou response. Event nese jen fixed command
   a sanitizovanou response; nikdy raw value. Listener provede nový resolver a
   porovnání uvnitř své closure.
6. Event type je prakticky neuhádnutelný routing identifikátor, nikoli bezpečnostní
   nebo privacy důkaz. Chybějící či duplicitní listener response, chybný stage
   nebo neplatné interní listener-response schema znamenají
   `ID0_BROWSER_STATE_LOST`. Až následná explicitní public projekce má vlastní
   přesné schema; jeho porušení je `ID0_INVALID_SANITIZED_PAYLOAD`. Ani jedna
   chyba nevytvoří candidate verdict.

Každý browser-side blok od prvního čtení raw value zachytí vlastní JS chyby uvnitř
execution contextu a převádí je pouze na fixed literal code; žádná assertion,
`Error`, interpolace ani serializace nesmí přijmout raw value. Worker tak může
obdržet jen explicitní public projekci nebo transportní Playwright chybu bez
candidate dat; ani její message parent nepřenese ani nevypíše.

Při druhém census se current values porovnají s baseline uvnitř closure. Open raw
values se po porovnání ihned odstraní z vlastněných arrays; state si ponechá jen
booleany a fixed rejection codes. Při třetím census proběhne totéž. `WeakMap`
nedrží DOM uzly silně a jeho ordinaly se nepoužívají jako identita.

### Cleanup a ztráta execution contextu

Explicitní fixed command `CLEAR`:

- zahodí všechny reference na baseline raw arrays a pomocné mapy;
- odstraní reference na `WeakMap`;
- nastaví stage `CLEARED`;
- odstraní listener z `window` pomocí stejné zachycené funkce a event type;
- vrátí jen `{code: "ID0_PRIVATE_STATE_CLEARED", cleared: true}`.

JavaScript string nelze garantovaně fyzicky přepsat v paměti; cleanup proto
netvrdí secure erasure, ale prokazatelně odstraní všechny reference vlastněné
aplikací a následně uzavře execution context. `CLEAR` se pošle po úspěchu,
očekávané chybě, invalid payloadu, timeoutu i `KeyboardInterrupt`. Je
logicky idempotentní na worker boundary: po validaci response
`ID0_PRIVATE_STATE_CLEARED` worker nastaví pouze sanitizovaný Python boolean
`clear_confirmed` a druhý `CLEAR` už neposílá. Odstraněný listener by podruhé
odpovědět nemohl; lokální no-op je úspěch výhradně při `clear_confirmed=true` v
tomtéž worker běhu.

Reload, cross-document navigation nebo replacement execution contextu zruší
listener i closure. Chybějící odpověď se mapuje na `ID0_BROWSER_STATE_LOST`; worker
se nepokouší state rekonstruovat, neprovádí další census a candidate verdict
nevydá. Zničení execution contextu současně odstraní jeho raw state. Same-document
rerender closure zachová, ale nové DOM uzly se projeví pouze v node-continuity
booleanech. Same-document navigace podléhá plnému fingerprint porovnání.

Pokud `CLEAR` selže nebo zatuhne, parent ještě vždy zahájí bounded context shutdown
a poté ukončení celého worker Job Objectu. Bez dřívější primární chyby je kód
`ID0_PRIVATE_STATE_CLEANUP_FAILED` nebo
`ID0_PRIVATE_STATE_CLEANUP_TIMEOUT`; s primární chybou zůstane podle autoritativní
priority zachován její fixed code. Žádný text cleanup výjimky se nevypíše.

Raw values:

- nikdy neopustí browser execution context, ani jako remote-object preview;
- nejsou součástí Python dataclass, argumentu, result payloadu ani `repr`;
- nejsou logovány, formátovány, interpolovány do error message ani exception
  code;
- nejsou ukládány na disk, do test artifacts, screenshotů, trace, videa nebo
  HAR;
- nejsou vráceny ani v debug režimu;
- po dokončení porovnání a `CLEAR` je aplikace dále nevlastní.

Varianty přenosu raw values do immutable Python objektu s `repr=False` i dlouho
žijícího raw-state `JSHandle` jsou zamítnuty. `JSHandle` může při svém vzniku
přenést preview metadata do Pythonu a jeho `repr`/`str` je může zobrazit. ID0 proto
pro candidate state nepoužívá žádný remote-object handle.

## Porovnání tří censusů

Pro každé způsobilé candidate name se používají přesné raw value arrays v
aktuálním DOM pořadí pouze uvnitř browseru. Technické porovnání identity probíhá
podle množiny hodnot, nikoli podle pozice.

Kandidát je `technically_stable=true` právě tehdy, když:

1. baseline detail precheck DOMově potvrdil nepřítomnost známého detailu;
2. manual-open check DOMově potvrdil právě jeden známý rezervační detail;
3. manual-close check DOMově potvrdil nepřítomnost známého detailu;
4. je přítomen na všech event rootech ve všech třech censusech;
5. všechny hodnoty jsou neprázdné a splňují value-shape kontrakt;
6. hodnoty jsou unikátní v každém jednotlivém census;
7. event count je stejný ve všech třech censusech;
8. množina hodnot po ručním otevření je přesně rovna baseline množině;
9. množina hodnot po ručním zavření je přesně rovna baseline množině;
10. calendar context, grid layer, event layer a jejich anonymní strukturální
   fingerprint odpovídají baseline.

Jestliže kterýkoli detail-state check neprojde, nevzniknou candidate observations,
`technically_stable` ani jeden ze dvou terminal result codes. Enter nastavuje pouze
`manual_*_acknowledged`; oddělené `baseline_known_detail_absent_confirmed`,
`manual_open_known_detail_confirmed` a
`manual_close_known_detail_absent_confirmed`
vzniknou výhradně z výsledku existujícího strukturálního resolveru.

`DETAIL_STRUCTURE_NOT_FOUND` je pouze důkaz, že resolver nenašel podporovanou
HEADER–CONTENT–ACTION strukturu známého rezervačního detailu. Není a nesmí být
interpretován jako důkaz, že není otevřen žádný neznámý, neklientský nebo nový
detailový surface. Proto jsou absence fields i invarianty výslovně omezeny na
**known detail**. Jakýkoli ambiguous/unknown stav je fatal a ID0 se jej nepokouší
automaticky zavřít.

Shoda pořadí není podmínkou `technically_stable`. Pro každý kandidát se zvlášť
vrátí:

- `order_stable_after_manual_open`;
- `order_stable_after_manual_close`.

Změna pořadí při stejné množině hodnot je platný technický výsledek: kandidát
může zůstat technically stable a příznak pořadí bude `false`. Tím test výslovně
prokáže, že algoritmus nezaměňuje ordinal za identitu.

Pomocně se vrátí také `same_dom_node_set_after_manual_open/close` a
`same_dom_node_order_after_manual_open/close`. Tyto booleany vzniknou pouze z
baseline `WeakMap`; nejsou keys, neovlivňují technical verdict a při rerenderu
mohou být `false`, i když candidate value set zůstane stabilní.

Candidate name set je vždy přesně source-controlled allowlist, nikoli sjednocení
runtime atributů. Allowlisted jméno nepřítomné v některém census nebo nově
přítomné až po baseline dostane `ID0_CANDIDATE_MISSING` a nemůže být technically
stable. Pokud zmizí pouze některá hodnota, platí totéž. Neallowlisted runtime
jméno se do této množiny nikdy nepřidá.

### Missing, duplicate a změna hodnoty

Tyto stavy jsou očekávaným negativním výsledkem jednotlivého kandidáta, nikoli
důvodem klikat nebo celý test opakovat:

| Stav kandidáta | Fixed rejection code | Důsledek |
| --- | --- | --- |
| Atribut není na všech eventech nebo ve všech censusech. | `ID0_CANDIDATE_MISSING` | Kandidát odmítnut. |
| Alespoň jedna hodnota je prázdná. | `ID0_CANDIDATE_EMPTY` | Kandidát odmítnut. |
| Alespoň jedna hodnota nesplní bounded value shape. | `ID0_CANDIDATE_VALUE_SHAPE_REJECTED` | Kandidát odmítnut. |
| Hodnota je duplicitní v kterémkoli census. | `ID0_CANDIDATE_DUPLICATED` | Kandidát odmítnut. |
| Unikátní množina se proti baseline změnila. | `ID0_CANDIDATE_VALUE_SET_CHANGED` | Kandidát odmítnut. |

Kandidát může mít více rejection codes. V immutable výsledku jsou vždy v pořadí
tabulky bez duplicit. Žádný rejection code neobsahuje name ani value.

Pokud se event count změní a event layer zůstane jednoznačně rozpoznatelná, celý
run skončí `ID0_EVENT_COUNT_CHANGED` a candidate výsledky se nevydají. Pokud
vrstvu již nelze jednoznačně rozpoznat, skončí
`ID0_CALENDAR_STRUCTURE_CHANGED`. Obojí je fail-closed a nelze interpretovat
jako negativní důkaz konkrétního kandidáta.

Stejná pravidla platí při otevřeném detailu: nedostupný calendar context,
zmizelá nebo nejednoznačná event layer, chybějící část kalendáře nebo
neporovnatelný fingerprint jsou fatal `ID0_CALENDAR_STRUCTURE_CHANGED`, nikoli
očekávané candidate rejection a nikdy technicky stabilní verdict.

## Bounded limity a timeouty

| Oblast | Limit | Překročení |
| --- | ---: | --- |
| Calendar DOM depth | `12` | `ID0_CENSUS_LIMIT_EXCEEDED` |
| Procházené DOM elementy | `5 000` | `ID0_CENSUS_LIMIT_EXCEEDED` |
| Contexts / layers | `20` / `20` | `ID0_CENSUS_LIMIT_EXCEEDED` |
| Calendar columns | přesně `1` | `ID0_REQUIRES_DAY_VIEW` |
| Event rooty | `2..10` | minimum/maximum kód níže |
| Atributy na jednom event rootu | `32` | `ID0_ATTRIBUTE_LIMIT_EXCEEDED` |
| Source-controlled allowlist | nejvýše `32`, v tomto kontraktu přesně `2` | změna bez privacy review není povolena |
| Runtime-discovered candidate names | `0` publikovaných | jiný public name → `ID0_INVALID_SANITIZED_PAYLOAD` |
| Délka allowlisted candidate name | `64` ASCII znaků | kontrola source-controlled kontraktu před spuštěním |
| Délka candidate value | `128` ASCII znaků | candidate value-shape reject |
| Censusy | přesně `3` | další census není povolen |
| Interní JS CPU budget jednoho census | `3 000 ms` monotonic `performance.now()` | defense-in-depth `ID0_CENSUS_TIMEOUT` |
| Post-create verification a pre-`START_BROWSER` frame/bootstrap wait | `5 s` každý | příslušný supervisor/bootstrap/IPC kód |
| `START_BROWSER_RESULT` | `--timeout-seconds`, host-enforced a nejvýše `300 s` | `ID0_BROWSER_START_TIMEOUT`; fixed failure podle operation boundary |
| `NAVIGATE_RESULT` před baseline | `--timeout-seconds`, host-enforced a nejvýše `300 s` | `ID0_CALENDAR_OPEN_TIMEOUT` nebo `ID0_CALENDAR_OPEN_FAILED` |
| Host deadline jednoho detail checku | `5 s` od zahájení command write do celé validní response | příslušný `ID0_*_DETAIL_CHECK_TIMEOUT` |
| Host deadline jednoho census/private-state commandu | `5 s` od zahájení command write do celé validní response | `ID0_CENSUS_TIMEOUT` |
| Manual open od validní baseline response po Enter | `120 s` | `ID0_MANUAL_OPEN_TIMEOUT` |
| Manual close od potvrzení open census po Enter | `60 s` | `ID0_MANUAL_CLOSE_TIMEOUT` |
| **Post-baseline operational deadline** | `220 s` od `post_baseline_t0` | `ID0_POST_BASELINE_OPERATIONAL_DEADLINE_EXCEEDED` |
| **Post-baseline supervisor deadline** | `222 s` od stejného `post_baseline_t0` | zachovat dřívější primary code, jinak přesný shutdown code podle potvrzení `ActiveProcesses` |
| Private-state `CLEAR` response | `5 s` | `ID0_PRIVATE_STATE_CLEANUP_TIMEOUT` |
| Korektní `BrowserContext.close()` response | `5 s` | `ID0_BROWSER_CLOSE_TIMEOUT` |
| Graceful exit workeru a potvrzení prázdného jobu | `2 s`, vždy oříznuto operational deadline | `ID0_WORKER_SHUTDOWN_TIMEOUT` |
| `SHUTDOWN_RESULT` | součást stejného `2 s` graceful-shutdown budgetu | `ID0_WORKER_SHUTDOWN_TIMEOUT` nebo `ID0_WORKER_SHUTDOWN_FAILED` |
| Hard `TerminateJobObject` + polling `ActiveProcesses` | `2 s`, vždy oříznuto supervisor deadline | zachovat dřívější primary code, jinak `ID0_PROCESS_TREE_TERMINATION_UNCONFIRMED` |
| Jeden IPC payload | `1..32 768` UTF-8 bajtů | framing/schema kódy níže |
| Celý IPC frame | `32 772` bajtů | prefix `4` bajty + payload |

`post_baseline_t0` vznikne až tehdy, když baseline `page.evaluate()` úspěšně
dokončí validaci, jako poslední browserovou operaci vytvoří private closure a
listener a vrátí přesný fixed registration success. Worker bezprostředně po
návratu tohoto callu uloží `time.monotonic_ns()` jako první host-observable
okamžik úspěšného vytvoření state a pošle jej v sanitizované baseline response.
Pro účely host kontraktu znamená „úspěšně vytvořeno“ právě návrat tohoto exact
success; dřívější rozpracovaný stav uvnitř nevráceného evaluate se nepovažuje za
success a zůstává kryt jeho pětisekundovým command deadlinem.
Parent přijme pouze hodnotu, která není v budoucnosti a není starší než
pětisekundový baseline-command deadline; jinak response odmítne jako
`ID0_INVALID_SANITIZED_PAYLOAD`. Přesný renderer instruction timestamp není z
hostu pozorovatelný a dokument netvrdí opak. Interval od odeslání baseline
commandu do tohoto fixed success je stále kryt samostatným pětisekundovým stage
deadlinem; při timeoutu se candidate verdict nevytvoří a následuje shutdown.
Parent a worker mohou timestamp přímo porovnat, protože Python na Windows používá
pro `monotonic` tentýž system-wide clock pro všechny procesy; tento předpoklad je
součástí dokumentovaného
[`time.monotonic()` kontraktu](https://docs.python.org/3.12/library/time.html#time.monotonic).

Před `post_baseline_t0` se obě post-baseline lhůty neuplatňují. Worker, Playwright
a Chromium už mohou běžet během časově neomezeného ručního login/setup kroku;
`220/222 s` proto nejsou a nesmějí být označeny jako absolutní lifetime workeru,
browseru ani celého process tree. Po `post_baseline_t0` dostává každá operace
nejvýše `min(local_timeout, remaining_operational_time)`. Operational deadline
ukončí další graceful čekání a zahájí hard termination. Následující nejvýše dvě
sekundy slouží pouze pro `TerminateJobObject` a polling jobu; supervisor deadline
je hranice čekání parentu, nikoli tvrzení o synchronním dokončení OS termination.

### Worst-case post-baseline timeline

Časový rozpočet se počítá konzervativně od `post_baseline_t0`:

| Krok | Maximum | Kumulativně |
| --- | ---: | ---: |
| Dokončení a přenos baseline registration response | `5 s` | `5 s` |
| Manual-open wait | `120 s` | `125 s` |
| Open detail validation | `5 s` | `130 s` |
| Open census | `5 s` | `135 s` |
| Manual-close wait | `60 s` | `195 s` |
| Close detail validation | `5 s` | `200 s` |
| Close census | `5 s` | `205 s` |
| `CLEAR` | `5 s` | `210 s` |
| Graceful `BrowserContext.close()` | `5 s` | `215 s` |
| `SHUTDOWN_RESULT`, worker exit a běžné potvrzení `ActiveProcesses == 0` | `2 s` | `217 s` |
| Bounded supervisor overhead reserve | `3 s` | `220 s` |
| Případný hard termination request a polling `ActiveProcesses` | `2 s` | `222 s` |

Třísekundová rezerva pokrývá bounded 50ms supervisor tick, IPC state transitions,
schema validaci, Job Object dotazy a scheduling mezi kroky. Není přičítána ke
každému lokálnímu limitu; global clipping zaručuje, že ji žádná operace neposune
za operational deadline. Pokud předchozí krok vyčerpá zbývající čas, následující
graceful krok dostane nulový čas, zachová dřívější primary nebo uloží
`ID0_POST_BASELINE_OPERATIONAL_DEADLINE_EXCEEDED` a supervisor přejde k hard
termination. Supervisor po `222 s` dále nečeká.

CLI `--timeout-seconds` má default `30`, přijímá hodnoty `(0, 300]` a omezuje
oddělený browser start, navigaci před baseline a Playwright operace, které veřejné API skutečně umí
timeoutovat. Není host-enforced deadline pro `page.evaluate()` ani
`BrowserContext.close()` a nesmí se tak interpretovat. `performance.now()` ani JS
`setTimeout` nemohou vynutit deadline, pokud renderer neodpovídá.

Rozdělení `START_BROWSER`/`NAVIGATE` nepřidává žádný post-baseline krok a
neobnovuje žádný budget. Před baseline má každý z obou commandů svůj jediný local
deadline. Po baseline se deadline každého command write, response read, manual
waitu, cleanupu, close a graceful shutdownu počítá z původního
`post_baseline_t0` jako `min(local_timeout, remaining_operational_time)`; pouze
hard termination polling používá
`min(2 s, remaining_supervisor_time)`. Nový command nikdy neposune ani znovu
nevytvoří `post_baseline_t0`. Proto konzervativní součet zůstává `220/222 s`.

### Bounded manual Enter na Windows

Parent nesmí pro pre-baseline, 120sekundový manual-open ani 60sekundový
manual-close krok volat blokující `input()`, `sys.stdin.readline()` ani vytvářet
pomocný input thread. Použije jeden Win32 wait loop:

1. Ještě před workflow instrukcemi načte `GetStdHandle(STD_INPUT_HANDLE)` a
   ověří `GetFileType(...) == FILE_TYPE_CHAR` a jedním preflight
   `GetConsoleMode` potvrdí, že jde skutečně o console input buffer. Neplatný
   handle nebo jiný file type znamená `ID0_INTERACTIVE_STDIN_REQUIRED`;
   preflight mode failure znamená `ID0_CONSOLE_MODE_QUERY_FAILED`. V obou
   případech redirected/non-interactive stdin selže před workerem i baseline.
   Parent potom vytvoří non-inheritable manual-reset interrupt event přes
   `CreateEventW`.
2. Bezprostředně před **každým** ze tří manual waitů parent zavolá
   `GetConsoleMode`, uloží přesnou původní hodnotu pro tento wait a zkontroluje
   bit `ENABLE_PROCESSED_INPUT` (`0x0001`). `GetConsoleMode` failure se mapuje
   pouze na `ID0_CONSOLE_MODE_QUERY_FAILED`.
3. Není-li `ENABLE_PROCESSED_INPUT` zapnutý, parent jej bezpečně zapne voláním
   `SetConsoleMode(original_mode | ENABLE_PROCESSED_INPUT)`, aniž změní ostatní
   bity. Failure se mapuje pouze na `ID0_CONSOLE_MODE_SET_FAILED` a wait
   nezačne.
4. Parent nainstaluje `SetConsoleCtrlHandler`. Handler pro
   `CTRL_C_EVENT`/`CTRL_BREAK_EVENT` pouze zavolá `SetEvent` na parent-owned
   interrupt event a vrátí `TRUE`; nedělá I/O, cleanup ani Python/browser práci.
   Callback reference zůstane živá do odregistrace. Registration failure se
   mapuje pouze na `ID0_CONSOLE_HANDLER_REGISTRATION_FAILED` a wait nezačne.
5. `WaitForMultipleObjects` čeká s `bWaitAll=FALSE` současně na console-input
   handle, interrupt event, worker process handle a právě aktivní OVERLAPPED I/O
   event, pokud existuje. Worker process handle je přítomen ve všech třech
   manual waitech; pouze dřívější interactivity preflight proběhne před jeho
   vytvořením. Timeout argument se při každém průchodu znovu spočítá z
   `time.monotonic_ns()` do nejbližšího local stage a aktivního globálního
   deadline; wait tak současně sleduje oba absolutní deadline bez dalšího
   waitable handle. Pre-baseline manual wait nemá časový limit, ale stále čeká
   na console handle, interrupt event i worker process handle, a je proto vždy
   přerušitelný přes Ctrl+C a reaguje na worker exit.
6. Signalizovaný console handle pouze znamená, že existuje alespoň jeden
   `INPUT_RECORD`. Parent jej čte po bounded dávkách přes `ReadConsoleInputW` a
   jako jediný běžný acknowledgement uzná Enter jen pro `KEY_EVENT`,
   `bKeyDown=TRUE` a carriage-return klávesu. Mouse/window/key-up a jiné key
   records bezpečně zahodí a okamžitě znovu čeká s nově vypočteným remaining
   time.
7. Signalizovaný worker handle se zpracuje přesně podle existující
   frame-versus-exit tabulky níže; manual wait nevytváří novou exit interpretaci.
   Signalizovaný interrupt event nebo outermost `KeyboardInterrupt` vytvoří
   `ID0_INTERRUPTED` podle globální tie priority a zahájí bounded cleanup.
   `WAIT_TIMEOUT` vybere příslušný manual/local/global deadline code. Failure
   kteréhokoli console/wait API po startu je `ID0_MANUAL_INPUT_FAILED`.
8. Každý manual wait má `finally`, který se spustí po Enter, Ctrl+C, worker exit,
   deadline i API failure. Nejprve se vždy pokusí obnovit **přesný** uložený
   console mode přes `SetConsoleMode`, i když byl původně processed bit zapnutý;
   potom vždy zavolá `SetConsoleCtrlHandler(handler, FALSE)`. Oba cleanup pokusy
   proběhnou i při selhání prvního. Restore failure se mapuje na
   `ID0_CONSOLE_MODE_RESTORE_FAILED`, handler removal failure na
   `ID0_CONSOLE_HANDLER_CLEANUP_FAILED`; existující dřívější `primary_code`
   zůstává zachován, bez dřívějšího primary má restore failure prioritu před
   handler cleanup failure. Žádný z těchto kódů ani jiná console chyba nesmí
   obsahovat raw Win32 error number nebo text.

Console input handle i process a event handles jsou dokumentovaně waitable;
console handle se signalizuje při nepřečtených input records. Tento mechanismus
odpovídá Win32
[`WaitForMultipleObjects`](https://learn.microsoft.com/windows/win32/api/synchapi/nf-synchapi-waitformultipleobjects),
[`ReadConsoleInputW`](https://learn.microsoft.com/windows/console/readconsoleinput),
[`GetConsoleMode`](https://learn.microsoft.com/windows/console/getconsolemode) a
[`SetConsoleMode`](https://learn.microsoft.com/windows/console/setconsolemode),
[`SetConsoleCtrlHandler`](https://learn.microsoft.com/windows/console/setconsolectrlhandler).
Žádná manual wait fáze nemůže překročit svůj deadline; i proud nerelevantních
console records vede vždy k přepočtu absolutního zbývajícího času.

### Normativní Windows bootstrap a vlastnictví

Budoucí implementace pro podporované Windows 10/11 a Python 3.12 použije právě
jeden race-safe mechanismus: přímé `CreateProcessW` se `STARTUPINFOEXW`, flags
`CREATE_SUSPENDED` a process attribute `PROC_THREAD_ATTRIBUTE_JOB_LIST`.
Nepoužije `subprocess.Popen` ani následné `AssignProcessToJobObject`. Job-list
attribute přiřadí nový proces do Job Objectu jako součást creation operation a
`CREATE_SUSPENDED` zabrání běhu primary threadu před post-create ověřením.
Worker proto v žádném okamžiku nespustí Python kód mimo Job Object; nevzniká
okno `Popen/CreateProcess → AssignProcessToJobObject`.

Normativní sekvence je:

1. Parent jako jediný vlastník vytvoří přes `CreateJobObjectW(NULL, NULL)`
   non-inheritable Job handle, nastaví
   `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` a nepovolí žádný breakaway flag. Job
   handle není v handle inheritance allowlistu; v job-list attribute je předán
   pouze jako assignment input, nikoli jako zděděný handle.
2. Parent získá profile lease a vytvoří dva lokální jednosměrné byte-mode Win32
   named-pipe kanály s náhodnými názvy, user-only DACL,
   `PIPE_REJECT_REMOTE_CLIENTS` a overlapped I/O: control parent→worker a result
   worker→parent. Parent vlastní control-write a result-read; worker potřebuje
   control-read a result-write. Všechny pipe handly vzniknou non-inheritable.
3. Parent otevře přes `CreateFileW("NUL", ...)` jeden validní read handle pro
   worker stdin a jeden validní write handle sdílený worker stdout i stderr.
   Standardní handly tedy nejsou IPC pipes, console handly ani parentovy veřejné
   streamy. Oba `NUL` handly také vzniknou non-inheritable.
4. Parent alokuje `STARTUPINFOEXW`; `StartupInfo.cb` je
   `sizeof(STARTUPINFOEXW)`, `dwFlags` obsahuje `STARTF_USESTDHANDLES`,
   `hStdInput=NUL-read` a `hStdOutput=hStdError=NUL-write`. Dvouprvkový attribute
   list vytvoří dvěma voláními `UpdateProcThreadAttribute`: exact child handle
   allowlist přes `PROC_THREAD_ATTRIBUTE_HANDLE_LIST` a jednoprvkový seznam Job
   handlů přes `PROC_THREAD_ATTRIBUTE_JOB_LIST`.
5. Exact inheritance allowlist obsahuje právě čtyři unikátní handly:
   `control-read`, `result-write`, `NUL-read`, `NUL-write`. Pod process-wide
   launch lockem parent dočasně nastaví inheritable právě tyto čtyři handly,
   použije `bInheritHandles=TRUE` a zavolá `CreateProcessW` s
   `EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW | CREATE_SUSPENDED`.
   `lpApplicationName` je přesný canonical `sys.executable`. Vstup pro Windows
   quoting je celý argv včetně executable jako `argv[0]`:

   ```text
   [sys.executable,
    "-m",
    "termino_exporter.identity_candidate_worker",
    "--control-handle", "<control-read-decimal>",
    "--result-handle", "<result-write-decimal>"]
   ```

   Parent jej zakóduje veřejným `subprocess.list2cmdline(argv)`, takže platí
   Windows quoting pravidla i pro mezery, uvozovky a backslashe v cestě
   executable. Výsledný text zkopíruje do zapisovatelného null-terminated
   bufferu vytvořeného přes `ctypes.create_unicode_buffer`; teprve pointer na
   tento mutable buffer předá jako `lpCommandLine`, protože `CreateProcessW` jej
   smí modifikovat. Buffer i argv backing values zůstanou živé do návratu callu.
   `-m` proto nikdy nemůže skončit jako `argv[0]`. Žádné jiné process creation
   pod launch lockem nesmí běžet.
6. `finally` launch úseku vždy okamžitě vrátí inheritability čtyř handlů na
   false a zavolá `DeleteProcThreadAttributeList`. Po úspěšném creation parent
   zavře své kopie `control-read`, `result-write` a obou `NUL` handlů. Z
   `PROCESS_INFORMATION` vlastní přímo worker process handle a primary-thread
   handle. Process handle drží do posledního wait/exit-status readu; primary
   thread handle musí zatím zůstat otevřený pro jediný povolený `ResumeThread`.
7. Úspěšný návrat `CreateProcessW` s job-list attribute je autoritativní
   assignment success. Parent ještě fail-closed ověří
   `IsProcessInJob(worker_process_handle, job_handle) == TRUE`, zatímco primary
   thread zůstává suspendovaný. Failure/false je contract/setup failure: parent
   nic neposílá ani neresumuje, zavře control channel, požádá o ukončení jobu i
   konkrétního workeru, bounded čeká a publikuje
   `ID0_SUPERVISOR_SETUP_FAILED`.
8. Pouze po potvrzeném členství zavolá parent právě jednou
   `ResumeThread(primary_thread_handle)`. Jediný přijatelný návrat je `1`, tedy
   předchozí suspend count procesu vytvořeného s `CREATE_SUSPENDED`; `DWORD(-1)`,
   `0` nebo jiná hodnota znamená `ID0_SUPERVISOR_SETUP_FAILED`. Parent v takovém
   případě neodešle `START_BROWSER`, požádá o bounded ukončení Job Objectu a
   konkrétního procesu a nikdy se nepokusí o druhé resume. Po úspěšném návratu
   parent primary-thread handle okamžitě zavře.
9. První spuštěný worker kód ověří dva decimal IPC handly a standardní `NUL` handly a
   přes `SetHandleInformation(..., HANDLE_FLAG_INHERIT, 0)` nastaví všechny své
   kopie jako non-inheritable. Teprve potom bounded čeká nejvýše pět sekund na
   exact `START_BROWSER`, který je jedinou protokolovou `START` branou. Parent
   jej smí odeslat až po úspěšném `ResumeThread`; teprve po validním přijetí této
   zprávy smí worker importovat nebo inicializovat Playwright a otevřít Chromium.
   EOF, timeout nebo jiný command vede k exit bez Playwrightu. Žádný budoucí
   Playwright driver ani Chromium child proto nemůže zdědit ID0 IPC handly.

Normativní pořadí tedy je: vytvořit Job Object → vytvořit IPC → atomicky vytvořit
suspendovaný worker s Job attribute → ověřit členství → úspěšně resumovat →
worker čeká na `START_BROWSER` → parent pošle `START_BROWSER` → teprve potom
worker inicializuje Playwright/browser.

Failure paths jsou uzavřené takto:

- selhání inicializace attribute listu, jeho update nebo `CreateProcessW`, včetně
  nemožného atomického Job assignmentu, zavře všechny dosud parent-owned handly,
  nevytvoří použitelný worker a mapuje se na `ID0_SUPERVISOR_SETUP_FAILED`;
- assignment verification failure neodešle `START_BROWSER`, provede výše uvedený
  bounded termination postup a mapuje se na `ID0_SUPERVISOR_SETUP_FAILED`;
- `ResumeThread` failure neodešle `START_BROWSER`, zavře primary-thread handle,
  požádá o bounded ukončení Job Objectu i procesu a mapuje se na
  `ID0_SUPERVISOR_SETUP_FAILED`;
- zemře-li parent po úspěšném `CreateProcessW`, ale před `ResumeThread`, worker
  je již členem jobu a jeho Python kód ještě neběžel; uzavření jediného
  parent-owned Job handle aktivuje `KILL_ON_JOB_CLOSE` i pro suspendovaný proces;
  pokud creation call selhal, žádný vrácený worker neexistuje;
- zemře-li parent po creation, ale před `START_BROWSER`, worker buď vidí EOF a
  skončí bez Playwrightu, nebo jej ukončí Job Object; zemře-li parent po
  `START_BROWSER`, stejný Job Object zahrnuje worker, Playwright driver i Chromium;
- pokud parent žije a worker uvidí EOF před `START_BROWSER`, skončí rezervovaným
  bootstrap statusem bez result frame; parent jej mapuje na
  `ID0_WORKER_BOOTSTRAP_FAILED`.

Použité Win32 symboly skutečně existují na podporovaném systému:
`STARTUPINFOEXW`, `PROCESS_INFORMATION`, `InitializeProcThreadAttributeList`,
`UpdateProcThreadAttribute`, `DeleteProcThreadAttributeList`, `CreateProcessW`,
`PROC_THREAD_ATTRIBUTE_HANDLE_LIST` (`0x00020002`),
`PROC_THREAD_ATTRIBUTE_JOB_LIST` (`0x0002000D`, Windows 10+),
`EXTENDED_STARTUPINFO_PRESENT` (`0x00080000`), `CREATE_NO_WINDOW`
(`0x08000000`), `CREATE_SUSPENDED` (`0x00000004`),
`STARTF_USESTDHANDLES` (`0x00000100`) a
`HANDLE_FLAG_INHERIT` (`0x00000001`). Python 3.12 má pro jejich deklaraci
veřejné `ctypes.WinDLL`, `ctypes.Structure` a `ctypes.wintypes`; nejde o
neexistující `Popen` parametr ani o privátní `Popen._handle`. Dostupnost těchto
FFI primitives potvrzuje dokumentace
[`ctypes` pro Python 3.12](https://docs.python.org/3.12/library/ctypes.html).
Kontrakt odpovídá
dokumentaci Win32
[`STARTUPINFOEXW`](https://learn.microsoft.com/windows/win32/api/winbase/ns-winbase-startupinfoexw),
[`UpdateProcThreadAttribute`](https://learn.microsoft.com/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute),
[`CreateProcessW`](https://learn.microsoft.com/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw)
a
[`ResumeThread`](https://learn.microsoft.com/windows/win32/api/processthreadsapi/nf-processthreadsapi-resumethread),
[`AssignProcessToJobObject`](https://learn.microsoft.com/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject)
a
[`IsProcessInJob`](https://learn.microsoft.com/windows/win32/api/jobapi2/nf-jobapi2-isprocessinjob).
Vlastnosti `CREATE_SUSPENDED`, extended startup flags a ukončení všech členů při
zavření posledního handle s `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` potvrzují také
[`Process Creation Flags`](https://learn.microsoft.com/windows/win32/procthread/process-creation-flags),
[`Suspending Thread Execution`](https://learn.microsoft.com/windows/win32/procthread/suspending-thread-execution)
a
[`Job Objects`](https://learn.microsoft.com/windows/win32/procthread/job-objects).
Overlapped named-pipe volba vychází z Win32
[`CreateNamedPipeW`](https://learn.microsoft.com/windows/win32/api/winbase/nf-winbase-createnamedpipew)
a
[`CancelIoEx`](https://learn.microsoft.com/windows/win32/api/ioapiset/nf-ioapiset-cancelioex)
API; synchronní anonymous-pipe write není použit jako host-enforced deadline.

#### Přesné vlastnictví handlů

- Parent vlastní Job handle, profile-lease mutex, control-write, result-read,
  worker process handle, interrupt event a všechny OVERLAPPED event handly až do
  příslušných `finally` bloků.
- Parent vlastní primary-thread handle od úspěšného `CreateProcessW` přes
  membership verification a jediný `ResumeThread` do bezprostředního
  `CloseHandle`. Na každé failure cestě jej rovněž zavře právě jednou.
- Dočasné parent kopie control-read, result-write, `NUL-read` a `NUL-write`
  existují jen přes creation bootstrap a parent je po návratu callu zavře.
- Worker vlastní své zděděné control-read, result-write a standardní `NUL`
  handly; hned na začátku zruší jejich inheritability a ve `finally` zavře oba
  IPC handly. Standardní handly zavře runtime při process exit.
- Attribute-list buffer a pole handle/job hodnot vlastní parent pouze do
  `DeleteProcThreadAttributeList`; jejich backing storage zůstává živé přes celý
  `CreateProcessW` call.
- Job handle nikdy není inherited. Členství v jobu a vlastnictví Job handle jsou
  odlišné věci.
- BrowserContext vlastní výhradně worker. Persistent profile lease vlastní
  výhradně parent podle následující sekce.

#### Vlastnictví persistentního profilu

Nejdříve se vždy použije existující `safe_profile_dir()`: canonical resolved
cesta ani žádný její rodič nesmí být Git repository. Parent potom před vytvořením
workeru získá single-owner Windows named mutex odvozený z SHA-256 canonical
case-normalized profile path; digest profilu se nevypisuje a nesouvisí s
candidate values. `WAIT_TIMEOUT` znamená `ID0_PROFILE_IN_USE` a worker nevznikne;
`WAIT_ABANDONED` znamená úspěšně převzatou lease. Mutex vlastní parent od prelaunch
do potvrzeného `ActiveProcesses == 0`, nebo při nepotvrzeném hard shutdownu do
zavření Job handle ve `finally`.

Mutex koordinuje všechny budoucí Termino Exporter příkazy používající tentýž
profil. Jiný, nekooperující Chromium proces mutex respektovat nemusí; neexistuje
bezpečný textově nezávislý preflight jeho interního locku. Pokud proto
`launch_persistent_context` po získání mutexu vyhodí libovolnou výjimku, worker
neinterpretuje její text a vrátí širší fixed
`ID0_PROFILE_IN_USE_OR_UNAVAILABLE`. `ID0_BROWSER_FAILED` je vyhrazen jen pro
selhání Playwright bootstrapu před tímto callem nebo pro chybu po již vráceném
BrowserContextu; rozhoduje operation boundary, nikdy exception message. Žádný
druhý BrowserContext se nepovažuje za otevřený. Worker je jediný vlastník
BrowserContextu a jediný proces ID0, který profil používá; parent vlastní pouze
profilovou lease. Pokud se lease po nepotvrzeném hard konci uvolní s parent
procesem, nový ID0 běh musí znovu projít mutexem i persistent-context launch;
stále živý nekooperující Chromium profile lock vede znovu fail-closed k
`ID0_PROFILE_IN_USE_OR_UNAVAILABLE`.

### IPC framing a stavové automaty

Oba kanály přenášejí přesně jeden frame pro jeden command/response. Parent smí mít
nejvýše jeden outstanding command a každý command má právě jeden expected
response type. Frame je:

```text
4-byte unsigned big-endian payload_length || payload_length bytes UTF-8 JSON
```

`payload_length` musí být `1..32768`; parent ani worker před validací délky
nealokuje body buffer a nikdy nedrží více než `32772` frame bajtů plus fixní
parser state. JSON musí být právě jeden object bez duplicate keys a mít přesně
keys `protocol_version`, `message_type`, `sequence_id`, `payload`; neznámé i
chybějící keys se odmítají. `protocol_version` je integer `1`, `message_type` je
fixed enum a `sequence_id` unsigned 32bit integer v rozsahu `1..4294967295`.
Response musí mít stejný sequence ID a očekávaný response type. Counter se v
jednom bounded běhu nesmí přetočit.
Candidate raw values ani jejich hash, část, délka či odvozenina nejsou v žádném
IPC schema.

| Command | Exact payload | Právě očekávaná response |
| --- | --- | --- |
| `START_BROWSER` | canonical `profile_dir` jako `1..8192` UTF-8 bajtů a `timeout_ms` jako integer `1..300000` | `START_BROWSER_RESULT`: pouze fixed `code` a boolean `context_created` |
| `NAVIGATE` | `url` jako `1..2048` UTF-8 bajtů a `timeout_ms` jako integer `1..300000` | `NAVIGATE_RESULT`: pouze fixed `code` a boolean `navigated` |
| `BASELINE_DETAIL_CHECK` | přesně prázdný object | `BASELINE_DETAIL_RESULT`: fixed `code` a fixed `detail_state` |
| `BASELINE_REGISTER` | přesně prázdný object | `BASELINE_REGISTER_RESULT`: fixed `code`, `post_baseline_t0_ns` a exact sanitized baseline projection |
| `OPEN_DETAIL_CHECK` | přesně prázdný object | `OPEN_DETAIL_RESULT`: fixed `code` a fixed `detail_state` |
| `OPEN_CENSUS` | přesně prázdný object | `OPEN_CENSUS_RESULT`: fixed `code` a exact sanitized observation projection |
| `CLOSE_DETAIL_CHECK` | přesně prázdný object | `CLOSE_DETAIL_RESULT`: fixed `code` a fixed `detail_state` |
| `CLOSE_CENSUS` | přesně prázdný object | `CLOSE_CENSUS_RESULT`: fixed `code` a exact sanitized observation projection |
| `CLEAR` | přesně prázdný object | `CLEAR_RESULT`: přesně `code: ID0_PRIVATE_STATE_CLEARED`, `cleared: true` |
| `CLOSE_CONTEXT` | přesně prázdný object | `CLOSE_CONTEXT_RESULT`: fixed `code` a boolean `closed` |
| `SHUTDOWN` | přesně prázdný object | `SHUTDOWN_RESULT`: fixed `code` a boolean `exiting`; success je přesně `ID0_WORKER_SHUTDOWN_ACKNOWLEDGED` + `true` |

Každý vnořený payload má rovněž exact allowlist, typové a délkové bounds; odkaz
na sanitized projection neumožňuje generic mapping ani dodatečný key. Browser,
profile ani URL hodnoty se nikdy neechojí v response nebo outputu. Pokud se
`START_BROWSER` nebo `NAVIGATE` s povolenými argumenty nevejde do frame limitu,
jde před workerem o `ID0_INVALID_ARGUMENTS`.

`detail_state` je právě jeden z fixed enums `KNOWN_DETAIL_PRESENT`,
`KNOWN_DETAIL_ABSENT` a `UNKNOWN_OR_AMBIGUOUS`; Playwright/check failure používá
fixed response `code`, nikoli vymyšlený stav „all details closed“.
`KNOWN_DETAIL_ABSENT` znamená výhradně přesný `DETAIL_STRUCTURE_NOT_FOUND` pro
podporovaný resolver a nic netvrdí o unknown/nonclient surface.

Worker command automat je normativně
`WAIT_START_BROWSER → BROWSER_READY → NAVIGATED → BASELINE_DETAIL_CHECKED →
BASELINE_REGISTERED → OPEN_DETAIL_CHECKED → OPEN_CENSUS_DONE →
CLOSE_DETAIL_CHECKED → CLOSE_CENSUS_DONE → CLEARED → CONTEXT_CLOSED →
SHUTDOWN_ACKNOWLEDGED → EXITED`. `START_BROWSER` smí inicializovat Playwright a
otevřít právě jeden persistentní BrowserContext/profile, ale nesmí volat
`page.goto()` ani jinak navigovat kalendář. `NAVIGATE` smí provést právě jednu
navigaci na zadanou URL a nesmí otevřít další context. Každý jiný command nebo
command mimo svůj stage je schema/state failure bez provedení požadované
browserové operace.

Po primary failure se automat smí přesunout pouze dopřednými cleanup hranami,
které dávají smysl pro skutečně vytvořené resources: `CLEAR`, pokud mohl vzniknout
private state, potom `CLOSE_CONTEXT`, pokud vznikl context, a nakonec `SHUTDOWN`.
`SHUTDOWN` není fire-and-forget. Worker nejdříve dokončí celý
`SHUTDOWN_RESULT` write, potom zavře result-write/control-read a skončí; response
potvrzuje jen přijetí shutdown commandu, nikoli worker exit ani prázdný Job
Object. Ty parent ověřuje zvlášť.

Parent read automat je `READ_PREFIX → READ_BODY → VALIDATE_FRAME →
ACCEPT_RESPONSE`. Overlapped `ReadFile` průběžně čte pouze zbývající část prefixu
nebo body; nečeká na dostupnost celého frame a nepoužívá `PeekNamedPipe` jako
podmínku celého readu. Parent v každém nejvýše 50ms ticku současně sleduje I/O
event, worker process handle, interrupt event, local stage deadline a obě aktivní
post-baseline lhůty.

Write automat je `WRITE_PREFIX → WRITE_BODY → COMPLETE`. Parent i worker používají
overlapped `WriteFile`, postupují podle skutečného počtu zapsaných bajtů a každý
pending write čeká nejvýše do stejného local/global deadline jako zpráva. Při
deadline zavolají `CancelIoEx`; nedokončený write je `ID0_IPC_WRITE_TIMEOUT`.
Broken pipe je `ID0_IPC_CHANNEL_BROKEN`. Úspěšně dokončený control write dokazuje
jen zápis frame do kanálu, nikoli jeho provedení workerem. Worker stdout/stderr a
potomci používají explicitní `NUL` standard handles, takže jejich běh nezávisí na
kapacitě standardních stream pipes.

Každá response po přijetí expected response uzavře daný sequence ID. Před
odesláním dalšího commandu musí být result channel bez dalších buffered bajtů.
Druhá response stejného ID, unsolicited response, response pro jiné ID/type a
response starého stage přijatá před vznikem primary code jsou
`ID0_INVALID_SANITIZED_PAYLOAD`. Pozdní zpráva se nikdy nepoužije jako odpověď na
`CLEAR`, `CLOSE_CONTEXT` nebo `SHUTDOWN`; každý cleanup command má nové sequence
ID.

### Autoritativní frame-versus-exit priorita

Pro jeden očekávaný response platí právě toto pořadí; parent nikdy nekombinuje
exit status a frame do dvou public codes:

1. Pokud je při signalizaci worker process handle už kompletní právě jeden frame
   a za ním nejsou další bajty, parent jej nejdříve validuje. Validní expected
   response je autoritativní i při současném worker exit; invalid frame je
   `ID0_INVALID_SANITIZED_PAYLOAD`.
2. Pokud byl přijat alespoň jeden byte, ale nejsou celé čtyři prefix bajty, jde o
   truncated prefix a `ID0_IPC_CHANNEL_BROKEN`. Celý prefix a neúplné body je
   truncated body a stejný code. Exit status v obou případech nic nepřebíjí.
3. Pokud nebyl přijat ani jeden response byte, parent teprve po potvrzeném worker
   exit načte přes `GetExitCodeProcess` validovaný reserved status. Status `71`
   mapuje na `ID0_IPC_WRITE_TIMEOUT` pouze po validním `START_BROWSER` a pouze
   tehdy, když buffer očekávané response zůstal prázdný. Při jediném přijatém
   bajtu už vždy vyhraje `ID0_IPC_CHANNEL_BROKEN`. Bootstrap status `70` před
   `START_BROWSER` mapuje na `ID0_WORKER_BOOTSTRAP_FAILED`. Libovolný jiný nebo
   neznámý status bez response po `START_BROWSER` mapuje na
   `ID0_WORKER_EXITED_WITHOUT_RESPONSE`; status `0` je validní jen po přijatém
   `SHUTDOWN_RESULT`.
4. Broken result pipe/EOF při živém workeru a bez kompletního frame je
   `ID0_IPC_CHANNEL_BROKEN`. Broken control pipe při command write je také
   `ID0_IPC_CHANNEL_BROKEN`.
5. Zero/oversized length, invalid UTF-8/JSON, duplicate keys, invalid schema,
   protocol, type nebo sequence v kompletním frame jsou
   `ID0_INVALID_SANITIZED_PAYLOAD`.
6. Duplicate nebo unsolicited response a jakékoli bajty v result kanálu v době,
   kdy žádná response není expected, jsou `ID0_INVALID_SANITIZED_PAYLOAD`.
   Response, která se stane kompletní až po vypršení svého stage deadline, je
   late: autoritativní deadline code už je primary, frame se zahodí a nesmí jej
   změnit. Pokud stará response dorazí až během nového stage bez dřívějšího
   primary, její type/sequence mismatch je `ID0_INVALID_SANITIZED_PAYLOAD`.

| Interní IPC/bootstrap stav | Public fixed code |
| --- | --- |
| Worker EOF/exit před validním `START_BROWSER`, zatímco parent žije | `ID0_WORKER_BOOTSTRAP_FAILED` |
| Worker exit po `START_BROWSER` bez jediného response bajtu a bez statusu `71` | `ID0_WORKER_EXITED_WITHOUT_RESPONSE` |
| Status `71` bez jediného response bajtu po `START_BROWSER` | `ID0_IPC_WRITE_TIMEOUT` |
| Broken control/result pipe; truncated prefix; truncated body; jiný partial frame | `ID0_IPC_CHANNEL_BROKEN` |
| Zero nebo oversized length; invalid UTF-8/JSON; duplicate/unknown/missing key; wrong schema/protocol/type/sequence; duplicate/unsolicited response nebo stale response bez dřívějšího deadline primary | `ID0_INVALID_SANITIZED_PAYLOAD` |
| Response dokončená až po svém deadline | Zachovat již vybraný operation-specific timeout; frame zahodit |
| Command/response write nedokončený do local/global deadline | `ID0_IPC_WRITE_TIMEOUT` |
| Worker žije, ale celý očekávaný frame nepřišel do stage deadline | browser start → `ID0_BROWSER_START_TIMEOUT`; navigation → `ID0_CALENDAR_OPEN_TIMEOUT`; detail → příslušný detail timeout; census/private-state → `ID0_CENSUS_TIMEOUT`; cleanup/close/shutdown → jejich timeout |

Žádná větev nepřenáší `OSError`, `JSONDecodeError`, Playwright text, frame content,
traceback ani `repr`; parent dostane nebo sám vytvoří pouze public fixed code.

### Job Object termination a pravdivý shutdown kontrakt

Job Object vlastní výhradně parent a jeho handle není inheritable. Worker,
Playwright driver a všechny Chromium procesy musí být členy téhož jobu;
breakaway je zakázán. Worker exit, graceful `BrowserContext.close()`, volání
`TerminateJobObject` a potvrzený prázdný job jsou čtyři odlišné stavy.

Po potvrzeném `CLEAR` a `BrowserContext.close()` parent odešle `SHUTDOWN`, přijme
a validuje `SHUTDOWN_RESULT` a v témže nejvýše dvousekundovém budgetu,
oříznutém operational deadline, čeká na worker exit a dotazuje
`QueryInformationJobObject(JobObjectBasicAccountingInformation)`. Běžný shutdown
je potvrzen jen při validním `SHUTDOWN_RESULT`, worker exit statusu `0` a
`ActiveProcesses == 0`. Jinak se buffered
candidate result zahodí, nastaví se pouze interní `shutdown_required` a parent
přejde na hard termination. Pokud hard termination následně potvrdí nulu, bez
dřívějšího primary vznikne `ID0_WORKER_SHUTDOWN_FAILED` při explicitním fixed
failure resultu, jinak `ID0_WORKER_SHUTDOWN_TIMEOUT`; pokud nulu nepotvrdí,
vznikne přesnější `ID0_PROCESS_TREE_TERMINATION_UNCONFIRMED`.

Hard termination vždy znamená explicitní `TerminateJobObject` s kontrolou
návratové hodnoty, nikoli pouhé zavření handle. Parent pak až do supervisor
deadline v bounded ticku opakuje
`QueryInformationJobObject(JobObjectBasicAccountingInformation)` a pouze
`ActiveProcesses == 0` nastaví interní fixed stav
`PROCESS_TREE_TERMINATION_CONFIRMED`. `TerminateJobObject` je termination request,
nikoli synchronní potvrzení. Pokud nula nepřijde, parent ve `finally` zavře Job
handle a smí tvrdit pouze: "forced process-tree termination was requested but
completion was not confirmed within the supervisor deadline." Bez dřívějšího
primary je public code `ID0_PROCESS_TREE_TERMINATION_UNCONFIRMED`; s primary se
zachová první code. `KILL_ON_JOB_CLOSE` zůstává poslední fallback při každém
parent exit.

Normativní význam těchto kroků odpovídá Win32
[`TerminateJobObject`](https://learn.microsoft.com/windows/win32/api/jobapi2/nf-jobapi2-terminatejobobject),
[`QueryInformationJobObject`](https://learn.microsoft.com/windows/win32/api/jobapi2/nf-jobapi2-queryinformationjobobject)
a
[`JOBOBJECT_BASIC_ACCOUNTING_INFORMATION`](https://learn.microsoft.com/windows/win32/api/winnt/ns-winnt-jobobject_basic_accounting_information)
API. Selhání termination nebo query callu se nikdy neinterpretuje jako potvrzená
nula a bez dřívějšího primary vede k
`ID0_PROCESS_TREE_TERMINATION_UNCONFIRMED`.

Úspěšný diagnostický result se publikuje pouze po potvrzeném `CLEAR`, graceful
context close, graceful worker exit a `ActiveProcesses == 0` bez potřeby hard
termination. Hard termination nebo nepotvrzený prázdný job vždy zahodí buffered
success. Fixed error lze po supervisor deadline vypsat i bez potvrzené nuly;
takový error netvrdí, že process tree již skončil. Job handle, worker process
handle, parent pipe ends a profile lease se zavřou ve všech případech ve
vlastních `finally` blocích v tomto pořadí: cancel pending I/O, zavřít všechny
OVERLAPPED event handly a parent pipe ends, zavřít interrupt event, zavřít Job
handle, zavřít worker process handle a uvolnit profile lease. Primary-thread
handle už byl zavřen bezprostředně po úspěšném `ResumeThread`, nebo na failure
cestě bez resume. Žádný `Popen` objekt ani privátní process handle v tomto
mechanismu neexistuje.

## Immutable návrhové typy

Budoucí Python modely budou `@dataclass(frozen=True, slots=True)` nebo `Enum`:

| Typ | Pole | Bezpečnost `repr` |
| --- | --- | --- |
| `IdentityCandidateStatus` | fixed enum hodnoty `TECHNICALLY_STABLE_UNAPPROVED` a rejection codes | Bez raw value; bezpečný. |
| `IdentityCandidateObservation` | `attribute_name`, presence/nonempty/shape/unique booleany pro tři censusy, set/order stability booleany, `technically_stable`, tuple fixed rejection codes | Obsahuje pouze exact source-controlled allowlisted název a booleany; žádná value. |
| `IdentityDomContinuityObservation` | node-set a node-order booleany po open/close | Pouze booleany; nikdy identity. |
| `IdentityCandidateDiagnosticResult` | terminal result code, bounded event/candidate counts a číselný `ignored_root_attribute_count`, tuple observations, DOM continuity, manual acknowledgements, `baseline_known_detail_absent_confirmed`, `manual_open_known_detail_confirmed`, `manual_close_known_detail_absent_confirmed`, `identity_approved=False`, `blocker_code` | Bez raw values, runtime-discovered names a event textu; vznikne až po potvrzeném cleanup, graceful context close, `SHUTDOWN_RESULT`, worker exit statusu `0` a `ActiveProcesses == 0`. |
| `IdentityCandidateDiagnosticError` | jeden fixed error code | Message je přesně code; původní výjimka pouze nevypsaná cause. |

Privátní browser state nemá Python handle, dataclass ani result objekt; existuje
jen v lexical closure registrovaného browser listeneru.
Deserializer přijme pouze přesně povolené keys, typy, délky, exact členství
candidate name ve source-controlled allowlistu, fixed enums a bounded čísla.
Jakákoli neznámá nebo neplatná hodnota se
mapuje na `ID0_INVALID_SANITIZED_PAYLOAD` bez payload `repr`.

## Terminal result codes ID0

ID0 má přesně dva úspěšně dokončené výsledky:

| Result code | Podmínka | Co znamená |
| --- | --- | --- |
| `ID0_TECHNICALLY_STABLE_CANDIDATES_FOUND_UNAPPROVED` | Alespoň jeden candidate splnil celý technický kontrakt. | Lze zahájit explicitní výběr a návrh ID1. Identita není schválena. |
| `ID0_NO_TECHNICALLY_STABLE_CANDIDATE` | Všechny tři censusy byly platné, ale žádný candidate nesplnil technický kontrakt. | Legitimní negativní výsledek; Phase 4C2 zůstává blokována. |

Oba výsledky mají `identity_approved: false` a
`blocker_code: EVENT_STABLE_IDENTITY_UNKNOWN`. ID0 nemá result code `PROVEN`.

## Fixed error codes ID0

Žádný error code nepřipojuje text Playwright výjimky, DOM data, candidate name
ani value.

| Error code | Situace |
| --- | --- |
| `ID0_INVALID_ARGUMENTS` | Neplatná syntaxe/rozsah ID0 CLI nebo bounded `START_BROWSER`/`NAVIGATE` argumenty nelze zakódovat do povoleného frame. |
| `ID0_DUMMY_ONLY_ACK_REQUIRED` | Chybí povinné CLI potvrzení. |
| `ID0_INTERACTIVE_STDIN_REQUIRED` | `STD_INPUT_HANDLE` je neplatný nebo není `FILE_TYPE_CHAR`; redirected/non-interactive stdin je odmítnut před baseline. |
| `ID0_CONSOLE_MODE_QUERY_FAILED` | `GetConsoleMode` selhal bez raw Win32 detailu. |
| `ID0_CONSOLE_MODE_SET_FAILED` | Před waitem se nepodařilo zapnout `ENABLE_PROCESSED_INPUT`; handler/wait nezačne. |
| `ID0_CONSOLE_MODE_RESTORE_FAILED` | `finally` neobnovil přesný původní console mode; cleanup pokus o odregistraci handleru přesto proběhne. |
| `ID0_CONSOLE_HANDLER_REGISTRATION_FAILED` | `SetConsoleCtrlHandler(handler, TRUE)` selhal; wait nezačne a console mode se obnoví. |
| `ID0_CONSOLE_HANDLER_CLEANUP_FAILED` | `SetConsoleCtrlHandler(handler, FALSE)` selhal po povinném restore pokusu. |
| `ID0_MANUAL_INPUT_FAILED` | Win32 console read/wait selhal po úspěšném interactivity preflightu. |
| `ID0_UNSAFE_PROFILE_DIR` | Browser profil není bezpečný. |
| `ID0_PROFILE_IN_USE` | Termino Exporter profile lease už vlastní jiný proces. |
| `ID0_PROFILE_IN_USE_OR_UNAVAILABLE` | Persistent context profil odmítl nebo nelze potvrdit jeho výhradní použití; příčina se neurčuje z textu výjimky. |
| `ID0_SUPERVISOR_SETUP_FAILED` | Job/IPC/attribute list/`CreateProcessW`, suspended membership verification nebo jediný `ResumeThread` selhal. |
| `ID0_WORKER_BOOTSTRAP_FAILED` | Worker viděl EOF nebo skončil před validním `START_BROWSER`, zatímco parent stále běžel. |
| `ID0_WORKER_EXITED_WITHOUT_RESPONSE` | Worker po `START_BROWSER` skončil bez jediného bajtu očekávané response a neměl použitelný reserved status `71`. |
| `ID0_IPC_CHANNEL_BROKEN` | Control/result channel se rozpojil nebo skončil EOF/truncated framem. |
| `ID0_IPC_WRITE_TIMEOUT` | Bounded command/response write nebyl dokončen do příslušného deadline. |
| `ID0_BROWSER_FAILED` | Playwright bootstrap selhal před persistent launch callem nebo nastala chyba až po vrácení BrowserContextu. |
| `ID0_BROWSER_START_TIMEOUT` | Živý worker nedodal celý `START_BROWSER_RESULT` do host deadline. |
| `ID0_CALENDAR_OPEN_FAILED` | Navigace na zadanou URL selhala. |
| `ID0_CALENDAR_OPEN_TIMEOUT` | Živý worker nedodal celý `NAVIGATE_RESULT` do host deadline. |
| `ID0_BASELINE_DETAIL_ALREADY_OPEN` | Baseline precheck nalezl právě jeden známý detail. |
| `ID0_BASELINE_DETAIL_STATE_AMBIGUOUS` | Baseline detail structure není jednoznačně nalezená ani nepřítomná. |
| `ID0_BASELINE_DETAIL_CHECK_FAILED` | Playwright chyba znemožnila baseline detail-state check. |
| `ID0_BASELINE_DETAIL_CHECK_TIMEOUT` | Host nedostal celou validní odpověď baseline detail checku do pěti sekund. |
| `ID0_BASELINE_CENSUS_FAILED` | Playwright selhání prvního census. |
| `ID0_MANUAL_OPEN_CENSUS_FAILED` | Listener byl dosažen, ale browser-side resolver druhého census vrátil fixed failure. |
| `ID0_MANUAL_CLOSE_CENSUS_FAILED` | Listener byl dosažen, ale browser-side resolver třetího census vrátil fixed failure. |
| `ID0_CENSUS_LIMIT_EXCEEDED` | Překročen bounded DOM resolver limit. |
| `ID0_CENSUS_TIMEOUT` | Interní 3sekundový CPU budget nebo pětisekundový host deadline census/private-state commandu vypršel. |
| `ID0_BASELINE_STRUCTURE_INVALID` | Po validním census není právě jeden context a grid, nebo existuje více než jedna event layer. Nula event-layer kandidátů sem nepatří. |
| `ID0_CALENDAR_STRUCTURE_CHANGED` | Po baseline se změnil nebo znejasnil context/grid/event layer či fingerprint. |
| `ID0_REQUIRES_DAY_VIEW` | Baseline není právě jednosloupcový pohled Den. |
| `ID0_EMPTY_EVENT_LAYER_UNPROVEN` | Po jednoznačném contextu, gridu a pohledu Den nebyl nalezen žádný neprázdný event-layer kandidát; prázdný den nelze odlišit od nerozpoznané vrstvy. |
| `ID0_EVENT_COUNT_TOO_SMALL` | Baseline obsahuje právě jeden event; ID0 vyžaduje nejméně dva. |
| `ID0_EVENT_LIMIT_EXCEEDED` | Baseline obsahuje více než deset eventů. |
| `ID0_EVENT_COUNT_CHANGED` | Jednoznačná event layer má po baseline jiný nenulový počet eventů. |
| `ID0_ATTRIBUTE_LIMIT_EXCEEDED` | Překročen limit počtu root atributů nebo source-controlled allowlistu. |
| `ID0_BROWSER_STATE_REGISTRATION_FAILED` | Baseline closure/listener nevznikl s validní fixed response. |
| `ID0_BROWSER_STATE_LOST` | Private closure chybí, je v jiném stage nebo zanikl její execution context. |
| `ID0_MANUAL_OPEN_TIMEOUT` | Uživatel nepotvrdil manual-open krok do 120 sekund od validní baseline response. |
| `ID0_MANUAL_OPEN_DETAIL_NOT_CONFIRMED` | Po Enter není nalezen známý rezervační detail. |
| `ID0_MANUAL_OPEN_DETAIL_UNKNOWN_OR_AMBIGUOUS` | Detailový resolver po Enter vrátil jiný strukturální stav než právě jeden známý detail nebo jasné not-found. |
| `ID0_MANUAL_OPEN_DETAIL_CHECK_FAILED` | Playwright chyba znemožnila manual-open detail check. |
| `ID0_MANUAL_OPEN_DETAIL_CHECK_TIMEOUT` | Host nedostal celou validní odpověď manual-open detail checku do pěti sekund. |
| `ID0_MANUAL_CLOSE_TIMEOUT` | Uživatel nepotvrdil manual-close krok do 60 sekund. |
| `ID0_MANUAL_CLOSE_DETAIL_STILL_OPEN` | Po Enter je stále potvrzen právě jeden známý detail. |
| `ID0_MANUAL_CLOSE_DETAIL_UNKNOWN_OR_AMBIGUOUS` | Detailový resolver po close Enter neprokázal jasné not-found ani právě jeden stále otevřený známý detail. |
| `ID0_MANUAL_CLOSE_DETAIL_CHECK_FAILED` | Playwright chyba znemožnila manual-close detail check. |
| `ID0_MANUAL_CLOSE_DETAIL_CHECK_TIMEOUT` | Host nedostal celou validní odpověď manual-close detail checku do pěti sekund. |
| `ID0_POST_BASELINE_OPERATIONAL_DEADLINE_EXCEEDED` | Od `post_baseline_t0` vypršel 220sekundový operational deadline; další graceful čekání skončilo. |
| `ID0_PRIVATE_STATE_CLEANUP_FAILED` | Cleanup selhal bez dřívější primární chyby. |
| `ID0_PRIVATE_STATE_CLEANUP_TIMEOUT` | `CLEAR` nebyl potvrzen do pěti sekund bez dřívější primární chyby. |
| `ID0_BROWSER_CLOSE_FAILED` | `BrowserContext.close()` selhal bez dřívější primární chyby. |
| `ID0_BROWSER_CLOSE_TIMEOUT` | Korektní context close nebyl potvrzen do pěti sekund bez dřívější primární chyby. |
| `ID0_WORKER_SHUTDOWN_FAILED` | Worker vrátil validní fixed failure na `SHUTDOWN` nebo po validním `SHUTDOWN_RESULT` skončil jiným statusem než `0`, bez dřívějšího primary code. |
| `ID0_WORKER_SHUTDOWN_TIMEOUT` | Worker neskončil graceful nebo job nebyl prázdný před hard termination, bez dřívějšího primary code. |
| `ID0_PROCESS_TREE_TERMINATION_UNCONFIRMED` | Forced process-tree termination byla vyžádána, ale `ActiveProcesses == 0` nebylo potvrzeno do supervisor deadline, bez dřívějšího primary code. |
| `ID0_INVALID_SANITIZED_PAYLOAD` | Browser/worker vrátil neplatný public payload nebo IPC frame/schema; jeho obsah se nevypíše. |
| `ID0_OUTPUT_LIMIT_EXCEEDED` | Sanitizovaný stdout by překročil line/byte limit. |
| `ID0_OUTPUT_FAILED` | Zápis sanitizovaného výstupu selhal. |
| `ID0_INTERRUPTED` | Uživatel přerušil workflow. |
| `ID0_INTERNAL_ERROR` | Neočekávaná interní výjimka zachycená outermost boundary. |

Detail wrapper rozhoduje pouze podle návratového `DetailStructure`, přesného
`ReservationExtractionError.code` a typu `playwright.sync_api.Error` v cause
chain. Nikdy nerozhoduje podle textu výjimky. Neznámý structure code se mapuje na
`ID0_BASELINE_DETAIL_STATE_AMBIGUOUS` v baseline nebo příslušný
`*_UNKNOWN_OR_AMBIGUOUS` kód v manuální stage; neznámá ne-detailová výjimka
propadne do sanitizovaného `ID0_INTERNAL_ERROR`.

## Rozhodovací tabulka ID0

Následující tabulka je jediná autoritativní validace a terminal priorita. Každý
řádek se vyhodnotí až po globálním supervisor pořadí pod tabulkou. První fixed
stage error se uloží jako immutable `primary_code`; pozdější bezpečnostní chyby
se provedou a zaznamenají interně, ale kód nepřepíší. Jedinou výjimkou jsou
ordered per-candidate rejection codes, které nejsou terminal errors.
Každá cesta vybere právě jeden fixed terminal state. Pokud selže samotný output
transport, nelze pravdivě garantovat, že pozorovatel tento vybraný code obdrží;
nikdy se však nevybere ani nevypíše druhý konkurenční terminal code.

| Pořadí | Stage a kontrola | Výsledek při neúspěchu / úspěchu |
| ---: | --- | --- |
| 1 | CLI syntax, rozsahy a serializovatelnost bounded `START_BROWSER`/`NAVIGATE` argumentů; `--help` je oddělený fixed text. | `ID0_INVALID_ARGUMENTS` / help exit `0`. |
| 2 | Povinný `--dummy-only`. | `ID0_DUMMY_ONLY_ACK_REQUIRED`; worker nevznikne. |
| 3 | `GetStdHandle(STD_INPUT_HANDLE)` + `GetFileType` + preflight `GetConsoleMode`. | Redirected/neplatný/neinteraktivní vstup → `ID0_INTERACTIVE_STDIN_REQUIRED` nebo `ID0_CONSOLE_MODE_QUERY_FAILED`; worker nevznikne. |
| 4 | `safe_profile_dir()`. | `ID0_UNSAFE_PROFILE_DIR`; worker nevznikne. |
| 5 | Profile lease. | Cooperating owner → `ID0_PROFILE_IN_USE`; lease/setup failure → `ID0_PROFILE_IN_USE_OR_UNAVAILABLE`; worker nevznikne. |
| 6 | Jediný zápis a flush pevného třířádkového workflow plánu. | Write/flush failure → `ID0_OUTPUT_FAILED`; worker ani browser nevznikne. |
| 7 | Job Object, interrupt/OVERLAPPED events, dva IPC kanály a `NUL` standard handles. | Create/configure failure → `ID0_SUPERVISOR_SETUP_FAILED`. |
| 8 | Attribute list s exact `HANDLE_LIST` + `JOB_LIST` a atomický suspended `CreateProcessW`. | Init/update/create failure, včetně nemožného Job assignmentu → `ID0_SUPERVISOR_SETUP_FAILED`; worker Python neběží a všechny temporary handly se zavřou. |
| 9 | `IsProcessInJob` verification, jediný `ResumeThread` a worker bootstrap. | False/API/resume failure → neposlat command, bounded termination, `ID0_SUPERVISOR_SETUP_FAILED`; až po pass worker běží a čeká na `START_BROWSER`; EOF/exit status `70` před ním → `ID0_WORKER_BOOTSTRAP_FAILED`. |
| 10 | Framed `START_BROWSER` write. | Broken/EOF → `ID0_IPC_CHANNEL_BROKEN`; write deadline → `ID0_IPC_WRITE_TIMEOUT`; jinak worker smí inicializovat Playwright a otevřít context/profile, ale nesmí navigovat. |
| 11 | `START_BROWSER_RESULT` do `--timeout-seconds`. | Živý worker bez celého frame → `ID0_BROWSER_START_TIMEOUT`; exception/fixed failure z `launch_persistent_context` → `ID0_PROFILE_IN_USE_OR_UNAVAILABLE`; Playwright bootstrap failure před callem nebo chyba po vrácení contextu → `ID0_BROWSER_FAILED`. |
| 12 | Framed `NAVIGATE` a `NAVIGATE_RESULT`. | Write failure → obecný IPC code; živý worker bez frame do deadline → `ID0_CALENDAR_OPEN_TIMEOUT`; validní fixed navigation failure → `ID0_CALENDAR_OPEN_FAILED`; success znamená právě jednu dokončenou navigation. |
| 13 | Obecná IPC kontrola každého command/response podle autoritativní frame-versus-exit priority. | Truncated prefix/body, partial frame nebo broken pipe → `ID0_IPC_CHANNEL_BROKEN`; zero/oversized/UTF-8/JSON/schema/version/type/sequence/duplicate/unsolicited chyba → `ID0_INVALID_SANITIZED_PAYLOAD`; write deadline nebo status `71` bez jediného response byte → `ID0_IPC_WRITE_TIMEOUT`; jiný worker exit bez response bytes po startu → `ID0_WORKER_EXITED_WITHOUT_RESPONSE`; late frame zachová už vybraný stage timeout. |
| 13a | Pre-baseline manual Enter wait v console-mode/handler `try/finally`. | Neomezený čas, ale interrupt event → `ID0_INTERRUPTED`; mode query/set/handler setup/restore/cleanup → příslušný exact fixed console code; Enter je jediný pass. |
| 14 | Baseline detail response do 5 s. | Živý worker bez celého frame → `ID0_BASELINE_DETAIL_CHECK_TIMEOUT`; jinak pokračovat. |
| 15 | Baseline known-detail result. | Playwright failure → `ID0_BASELINE_DETAIL_CHECK_FAILED`; právě jeden známý detail → `ID0_BASELINE_DETAIL_ALREADY_OPEN`; přesný `DETAIL_STRUCTURE_NOT_FOUND` → `baseline_known_detail_absent_confirmed=true`; jinak `ID0_BASELINE_DETAIL_STATE_AMBIGUOUS`. Not-found netvrdí absenci unknown surface. |
| 16 | Baseline census, bounds a struktura. | Host/JS timeout → `ID0_CENSUS_TIMEOUT`; resolver failure → `ID0_BASELINE_CENSUS_FAILED`; limity → `ID0_CENSUS_LIMIT_EXCEEDED`/`ID0_ATTRIBUTE_LIMIT_EXCEEDED`; context/grid/layer → `ID0_BASELINE_STRUCTURE_INVALID`; jiný než jeden sloupec → `ID0_REQUIRES_DAY_VIEW`; nula layer candidates → `ID0_EMPTY_EVENT_LAYER_UNPROVEN`; event count `1`/`>10` → příslušný count kód. |
| 17 | Private closure/listener registration a exact response. | Fixed registration failure → `ID0_BROWSER_STATE_REGISTRATION_FAILED`; invalid payload → řádek 13; success vytvoří jediný `post_baseline_t0`, operational `+220 s` a supervisor `+222 s`. |
| 18 | Manual-open Win32 Enter wait v console-mode/handler `try/finally`. | Query/set/handler/restore/cleanup → příslušný exact fixed console code; read/wait API failure → `ID0_MANUAL_INPUT_FAILED`; interrupt → `ID0_INTERRUPTED`; worker exit → řádek 13; operational deadline → `ID0_POST_BASELINE_OPERATIONAL_DEADLINE_EXCEEDED`; jinak po 120 s `ID0_MANUAL_OPEN_TIMEOUT`. |
| 19 | Manual-open detail response/result. | Živý worker bez frame po 5 s → `ID0_MANUAL_OPEN_DETAIL_CHECK_TIMEOUT`; Playwright failure → `ID0_MANUAL_OPEN_DETAIL_CHECK_FAILED`; not-found → `ID0_MANUAL_OPEN_DETAIL_NOT_CONFIRMED`; jiná structure chyba → `ID0_MANUAL_OPEN_DETAIL_UNKNOWN_OR_AMBIGUOUS`; právě jeden known detail → dispose a pass. |
| 20 | Open census/private-state response. | Živý worker bez frame/JS budget → `ID0_CENSUS_TIMEOUT`; listener/stage loss → `ID0_BROWSER_STATE_LOST`; transport frame chyba → řádek 13; resolver failure → `ID0_MANUAL_OPEN_CENSUS_FAILED`; limit → příslušný limit kód. |
| 21 | Open fingerprint, event count a bounds. | Structure rozdíl → `ID0_CALENDAR_STRUCTURE_CHANGED`; count rozdíl → `ID0_EVENT_COUNT_CHANGED`; bounds → `ID0_ATTRIBUTE_LIMIT_EXCEEDED`; jinak raw open values zahodit. |
| 22 | Manual-close Win32 Enter wait v console-mode/handler `try/finally`. | Query/set/handler/restore/cleanup → příslušný exact fixed console code; read/wait API failure → `ID0_MANUAL_INPUT_FAILED`; interrupt → `ID0_INTERRUPTED`; worker exit → řádek 13; operational deadline → `ID0_POST_BASELINE_OPERATIONAL_DEADLINE_EXCEEDED`; jinak po 60 s `ID0_MANUAL_CLOSE_TIMEOUT`. |
| 23 | Manual-close known-detail response/result. | Živý worker bez frame po 5 s → `ID0_MANUAL_CLOSE_DETAIL_CHECK_TIMEOUT`; Playwright failure → `ID0_MANUAL_CLOSE_DETAIL_CHECK_FAILED`; known detail → `ID0_MANUAL_CLOSE_DETAIL_STILL_OPEN`; jiná structure chyba → `ID0_MANUAL_CLOSE_DETAIL_UNKNOWN_OR_AMBIGUOUS`; přesný not-found → `manual_close_known_detail_absent_confirmed=true`. Not-found netvrdí absenci unknown surface. |
| 24 | Close census/private-state response. | Živý worker bez frame/JS budget → `ID0_CENSUS_TIMEOUT`; listener/stage loss → `ID0_BROWSER_STATE_LOST`; transport frame chyba → řádek 13; resolver failure → `ID0_MANUAL_CLOSE_CENSUS_FAILED`; limit → příslušný limit kód. |
| 25 | Close fingerprint, event count a bounds. | Structure rozdíl → `ID0_CALENDAR_STRUCTURE_CHANGED`; count rozdíl → `ID0_EVENT_COUNT_CHANGED`; bounds → `ID0_ATTRIBUTE_LIMIT_EXCEEDED`; jinak raw close values zahodit. |
| 26 | Candidate presence, empty, shape, duplicate a set equality. | Přidat v pořadí `ID0_CANDIDATE_MISSING`, `ID0_CANDIDATE_EMPTY`, `ID0_CANDIDATE_VALUE_SHAPE_REJECTED`, `ID0_CANDIDATE_DUPLICATED`, `ID0_CANDIDATE_VALUE_SET_CHANGED`; nejsou terminal. |
| 27 | Candidate order, DOM continuity a stable count. | Order/continuity jsou pouze booleany; nula stable → buffered no-candidate, jinak buffered found-unapproved; nic se automaticky nevybere. |
| 28 | `CLEAR`/`CLEAR_RESULT`, pokud state mohl vzniknout. | Zachovat primary; bez primary fixed failure → `ID0_PRIVATE_STATE_CLEANUP_FAILED`, timeout → `ID0_PRIVATE_STATE_CLEANUP_TIMEOUT`, operational deadline → `ID0_POST_BASELINE_OPERATIONAL_DEADLINE_EXCEEDED`; transport podle řádku 13. |
| 29 | `CLOSE_CONTEXT`/`CLOSE_CONTEXT_RESULT`, pokud context vznikl. | Zachovat primary; bez primary fixed failure → `ID0_BROWSER_CLOSE_FAILED`, timeout → `ID0_BROWSER_CLOSE_TIMEOUT`, operational deadline → `ID0_POST_BASELINE_OPERATIONAL_DEADLINE_EXCEEDED`; transport podle řádku 13. |
| 30 | `SHUTDOWN`/`SHUTDOWN_RESULT`, worker exit status `0` a job query v jednom 2s budgetu. | Zachovat primary; bez primary fixed response nebo nonzero exit → `ID0_WORKER_SHUTDOWN_FAILED`; timeout/bez ack/worker exit/job stále neprázdný → interní `shutdown_required`, zahodit buffered success a po potvrzeném hard konci `ID0_WORKER_SHUTDOWN_TIMEOUT`; transport podle řádku 13. |
| 31 | `TerminateJobObject` a polling `ActiveProcesses`. | Zachovat primary; bez primary a s potvrzenou nulou po vynuceném zásahu → shutdown code z řádku 30; bez potvrzené nuly do supervisor deadline → `ID0_PROCESS_TREE_TERMINATION_UNCONFIRMED`. Samotný termination request není pass. |
| 32 | Supervisor deadline. | Vyhodnotit řádek 31 před interruptem, zrušit pending I/O a zavřít Job handle ve `finally`; netvrdit dokončenou termination. |
| 33 | Unexpected parent/worker exception. | Zachovat primary; bez primary → `ID0_INTERNAL_ERROR`; žádný exception text ani `repr`. |
| 34 | Po shutdownu sestavit a validovat celý bounded output. | S primary pouze fixed error line. Bez primary a pouze po graceful shutdown + `ActiveProcesses == 0` sestavit non-terminal informational lines a zvlášť poslední terminal result line; nadlimit → `ID0_OUTPUT_LIMIT_EXCEEDED`. |
| 35 | Zapsat a flushnout všechny non-terminal informational stdout lines. | Jakýkoli partial/write/flush failure před terminal resultem → `ID0_OUTPUT_FAILED`; success code nebyl publikován, smí následovat jediný fixed stderr pokus. |
| 36 | Jako poslední zapsat a flushnout jediný terminal result line. | Write/flush failure vybere interní terminal state `ID0_OUTPUT_FAILED` a exit `1`; success se nepovažuje za kontraktně publikovaný a žádný druhý public terminal code na stderr/stdout už nesmí následovat. Potvrzený write+flush → result publikován. |
| 37 | Zápis fixed error line na stderr. | Jediný bounded write+flush pokus; při failure nic dalšího a exit `1`. Po potvrzeném success se nikdy nevolá. |
| 38 | Procesní návrat. | Potvrzeně publikovaný result → `0`; `ID0_INTERRUPTED` → `130`; `ID0_INVALID_ARGUMENTS` → `2`; každý jiný error nebo nepotvrzený terminal write → `1`. |

### Autoritativní supervisor a terminal priority

V každém supervisor ticku se události pozorované v témže ticku vyhodnotí přesně
v tomto pořadí:

1. již uložený `primary_code` zůstává immutable;
2. aktivní post-baseline supervisor deadline podle řádku 31;
3. `KeyboardInterrupt`;
4. aktivní post-baseline operational deadline;
5. local stage deadline;
6. worker process a IPC event podle řádku 13; při současném worker exit se nejprve
   přijme právě jeden už kompletní očekávaný frame, partial frame je broken channel
   a bez bajtů jde o worker exit without response;
7. validní stage response.

Proto při současném supervisor deadline a interruptu bez primary vznikne podle
stavu jobu `ID0_WORKER_SHUTDOWN_TIMEOUT` nebo
`ID0_PROCESS_TREE_TERMINATION_UNCONFIRMED`; při současném interruptu a
operational/stage deadline vznikne `ID0_INTERRUPTED`. Pokud primary vznikl v
předchozím ticku, žádná z těchto událostí jej nepřepíše. Před `post_baseline_t0`
jsou obě globální deadline neaktivní.

Cleanup, close a shutdown se i po primary provedou v pořadí, které dovolí
zbývající global time. Jejich failure primary nepřepisuje. Bez primary se první z
nich stane primary a zabrání publikaci success: cleanup code má přednost před
close code. Worker/job failure se odloží do výsledku hard fáze: potvrzená nula po
vynuceném zásahu znamená obecnější `ID0_WORKER_SHUTDOWN_TIMEOUT`, nepotvrzená
nula přesnější `ID0_PROCESS_TREE_TERMINATION_UNCONFIRMED`. Interní výjimka v
cleanupu bez primary je `ID0_INTERNAL_ERROR`; s primary se pouze interně
zaznamená fixed secondary stav.

Worker-side overlapped response write timeout ukončí worker rezervovaným
sanitizovaným process exit statusem `71`. Tento status smí přebít obecný
worker-exit code pouze po validním `START_BROWSER` a jen když parent nepřijal ani
jeden byte právě očekávané response; potom vznikne `ID0_IPC_WRITE_TIMEOUT`.
Jakýkoli partial frame má před statusem `71` přednost a je
`ID0_IPC_CHANNEL_BROKEN`. Status `70` je vyhrazen pouze pro bootstrap EOF/timeout
před `START_BROWSER`. Každý jiný neočekávaný worker exit bez kompletního frame se
mapuje podle řádků 9 nebo 13. Exit status ani interní detail se nevypisují.

Outermost parent `main()` zachytí `KeyboardInterrupt` samostatně a všechny ostatní
`Exception` mapuje na `ID0_INTERNAL_ERROR`. Worker zachytí totéž, ale do parentu
smí poslat pouze fixed code. Worker standardní streamy vedou na zděděné `NUL`
handly a parent nikdy nevypíše exception cause, Playwright message, traceback,
worker IPC `repr` ani interní objekt.

## Povolený výstup

Parent ještě před vytvořením workeru zapíše a flushne jediným zápisem tři pevné
očíslované workflow instrukce, každou jako právě jeden předem zakódovaný řádek
bez DOM dat. Selhání je `ID0_OUTPUT_FAILED` a browser se neotevře. Od odeslání
baseline commandu do dokončení bounded supervisor shutdownu parent na
stdout/stderr nic nezapisuje; deadline loop proto neblokuje na výstupním I/O.
Success block sestaví jen po potvrzeném cleanupu, graceful context close,
validním `SHUTDOWN_RESULT`, graceful worker exit statusu `0` a
`ActiveProcesses == 0`. Fixed error block smí sestavit po
ukončení bounded shutdown postupu i tehdy, když nula potvrzena nebyla; takový
výstup tvrdí jen příslušný fixed error. Celý stdout včetně instrukcí smí obsahovat
nejvýše `64` řádků a `32 768` UTF-8 bajtů.
Source-controlled allowlist smí mít nejvýše `32` názvů po nejvýše `64` ASCII
znacích; tento kontrakt obsahuje přesně dva a jeden candidate se formátuje na
právě jeden řádek. Parent vede kumulativní line/byte counter;
celý informational payload i zvláštní terminal line nejprve sestaví, striktně
zvaliduje a UTF-8 zakóduje v paměti a před prvním jejich bytem ověří oba limity.
Stejné dva stdout limity platí pro samostatný fixed `--help` výstup.

Pozitivní publikace má přesně toto pořadí:

1. zapsat všechny bounded **non-terminal** informational lines a potvrdit jejich
   flush;
2. pouze po jejich úplném write+flush zapsat terminal result code jako poslední
   samostatný řádek jediným bounded write;
3. potvrdit flush terminal řádku a teprve potom považovat success za publikovaný
   kontrakt a vrátit exit `0`.

Selže-li informational write nebo flush, terminal result line se vůbec nepokusí
zapsat; parent nastaví `ID0_OUTPUT_FAILED`, může provést jediný bounded fixed
stderr pokus a vrátí `1`. Selže-li write nebo flush samotného posledního terminal
řádku, parent zvolí interní terminal state `ID0_OUTPUT_FAILED` a vrátí `1`, ale
už nevypíše `ID0_OUTPUT_FAILED` ani jiný druhý public terminal code na stdout nebo
stderr. Windows stream write ani flush neposkytuje
transakční atomicitu: při ohlášené chybě mohl být viditelný prefix, nebo dokonce
celý řádek. Takový řádek se podle kontraktu nepovažuje za potvrzeně publikovaný
success; dokument netvrdí, že jej lze odvolat nebo že pozorovatel nemohl bajty
zahlédnout. Po potvrzeném terminal write+flush se už žádný další public terminal
code na jiném streamu nikdy nevydá.

Běžný stdout smí obsahovat pouze:

- fixed instrukce bez DOM dat;
- terminal result code pouze jako poslední samostatný stdout řádek;
- `event_count` v rozsahu 2..10;
- bounded `candidate_count`, `technically_stable_candidate_count` a číselný
  `ignored_root_attribute_count` bez názvů ignorovaných atributů;
- pouze source-controlled allowlisted candidate attribute names v
  lexikografickém pořadí;
- presence, nonempty, shape, uniqueness, value-set stability a order stability
  booleany;
- pomocné DOM node continuity booleany;
- fixed candidate rejection codes;
- `manual_open_acknowledged`, `manual_close_acknowledged`;
- `baseline_known_detail_absent_confirmed`,
  `manual_open_known_detail_confirmed` a
  `manual_close_known_detail_absent_confirmed`; u terminal result jsou všechny
  `true`;
- `identity_approved: false`;
- `blocker_code: EVENT_STABLE_IDENTITY_UNKNOWN`;
- `tool_click_count: 0` a `candidate_values_printed: false`.

Stderr smí obsahovat nejvýše jeden ASCII řádek a `128` UTF-8 bajtů ve tvaru
`Chyba: <FIXED_ID0_CODE>`. Chyba zápisu se řídí terminal priority; stderr failure
se dále nereportuje a proces skončí `1`.

Nikdy se nesmí vypsat candidate value, její část, délka, prefix/suffix, hash,
digest, event text, accessible name, klientská data, detailový text, selector,
locator, HTML, DOM `repr`, raw payload nebo text Playwright výjimky. Debug mód
nesmí toto pravidlo oslabit. ID0 nemá verbose/debug volbu a logging workeru je
vypnutý; parent formátuje pouze striktně validované modely, nikdy obecnou mapping,
výjimku nebo Playwright objekt.

## Co ID0 může a nemůže prokázat

ID0 může prokázat pouze to, že určitý předem schválený allowlisted attribute name
měl v jednom dummy-only běhu na strukturálně rozpoznaných event rootech bounded,
neprázdné, unikátní hodnoty a stejnou množinu přes tři censusy. Může samostatně
ukázat změnu pořadí a výměnu DOM uzlů. Nemůže objevit ani publikovat nový runtime
attribute name.

ID0 nemůže prokázat:

- význam nebo původ hodnoty;
- absenci PII či provozně citlivého identifikátoru;
- stabilitu mezi přihlášeními, relacemi, dny nebo verzemi Termino;
- bezpečnost budoucího lookupu nebo click loopu;
- kdo provedl ruční akci nebo že datum je obsahově dummy-only; prokazuje pouze
  DOM přechod bez známého detailu → jeden známý detail → bez známého detailu;
- že kandidát je `stable_event_key`;
- připravenost Phase 4C2.

## Exit criteria ID0 -> ID1

Do samostatného ID1 návrhu lze přejít pouze tehdy, když:

1. ID0 implementace, unit testy, syntetické browser testy a privacy/interaction
   audit prošly;
2. manuální běh použil výhradně zjevně dummy-only den se 2..10 eventy;
3. terminal result je
   `ID0_TECHNICALLY_STABLE_CANDIDATES_FOUND_UNAPPROVED`;
4. `baseline_known_detail_absent_confirmed`,
   `manual_open_known_detail_confirmed` a
   `manual_close_known_detail_absent_confirmed` jsou všechny `true`;
5. private-state `CLEAR` a context close byly potvrzeny před vydáním výsledku;
6. alespoň jeden source-controlled allowlisted candidate name má
   `technically_stable=true`;
7. člověk v novém explicitním design/implementation kroku zvolí právě jeden
   candidate name; ID0 jej nevybere automaticky;
8. do Pythonu, repozitáře ani reportu se nedostala žádná candidate value.

Pokud ID0 nenajde kandidáta, skončí chybou nebo má neplatný privacy audit,
`EVENT_STABLE_IDENTITY_UNKNOWN` zůstává blocker a ID1 se nezahájí.

## Požadavky ID1 a exit criteria ID1 -> Phase 4C2

ID1 smí vytvořit `approved stable_event_key` jen při současném splnění dvou
nezávislých skupin důkazů.

### Technický důkaz ID1

- konkrétní name je explicitně zapsán v reviewovaném ID1 kontraktu, ne převzat
  automaticky z runtime;
- je na všech eventech, neprázdný a unikátní v každém census;
- jeho value set je shodný přes baseline/manual open/manual close;
- porovnání zůstává správné při syntetické změně pořadí a nepoužívá ordinal;
- nový census a budoucí lookup jsou atomické a hledají právě jeden root podle
  stejného explicitního name/value kontraktu;
- missing, duplicate, set change nebo více targetů vždy fail-closed před clickem;
- testy pokrývají rerender s novými DOM uzly a stejnými keys;
- alespoň dva oddělené dummy-only ID0 běhy potvrdily stejný candidate name bez
  persistování jeho values.

### Semantic/privacy důkaz ID1

Reviewovaný dokument musí popsat známého producenta atributu, význam hodnoty,
zdroj/odvození, životnost, scope unikátnosti a možnost korelace. Musí existovat
pozitivní důkaz, že hodnota:

- není odvozena z klientského jména, e-mailu, telefonu, poznámky, služby,
  zaměstnance, času ani jiného event textu;
- není backend reservation ID, customer ID, veřejný/privátní token ani jiný
  provozně citlivý identifikátor;
- není CSS/framework generated class, element `id`, geometrie, barva,
  souřadnice ani ordinal;
- je určena pouze k bezpečnému rozlišení event rootů v požadovaném runtime
  scope.

Přijatelným semantic důkazem je autoritativní dokumentace producenta nebo
reviewovatelný data-flow/zdrojový kontrakt, který původ a necitlivost hodnoty
výslovně dokládá. Název atributu, opaque vzhled, entropy, UUID/hash formát,
sanitizovaný výstup ani experimentální stabilita nejsou takovým důkazem.

Phase 4C2 lze navrhnout až poté, co:

1. technický i semantic/privacy důkaz ID1 jsou explicitně schváleny;
2. jeden candidate name je označen jako approved a všechny ostatní zůstávají
   neschválené;
3. jsou definovány fresh census a atomický fresh lookup podle approved key;
4. raw key je skrytý z `repr`, výstupu, errors a persistence;
5. duplicate/missing/change/count/structure failure jsou fatal před clickem;
6. produkční interaction audit stále povoluje pouze existující tři typy clicků
   a samostatné review výslovně povolí použití event clicku v Phase 4C2;
7. `EVENT_STABLE_IDENTITY_UNKNOWN` je odstraněn explicitním ID1 rozhodnutím,
   nikoli samotným výsledkem ID0.

Bez kteréhokoli bodu zůstává Phase 4C2 blokována.

## Testovací strategie budoucí ID0 implementace

### Unit testy

- immutable result/observation modely a striktní sanitized deserializer;
- exact source-controlled allowlist membership, root-only scope a odmítnutí
  všech runtime names mimo allowlist bez jejich přenosu;
- bounded name/value/attribute/candidate limity;
- stable unique candidate přes tři syntetické census payloady;
- missing, empty, shape-invalid, duplicate a changed-set candidate;
- změna pořadí se projeví pouze v order booleans a nezmění set-based technical
  status;
- změna event count a fingerprintu skončí fixed error;
- více stabilních kandidátů se seřadí podle name a žádný se nevybere;
- ID0 nikdy nevytvoří `PROVEN` ani approved key;
- baseline/open/close detail-state checky vyžadují pořadí známý detail
  nepřítomen → právě jeden known detail → známý detail nepřítomen; pouhé Enter
  nikdy nestačí a not-found nic netvrdí o unknown surface;
- raw synthetic values nejsou v Pythonu, IPC, `repr`, outputu, erroru ani
  exception message a candidate cesta nevytvoří `JSHandle`;
- invalid public payload se odmítne bez svého `repr`;
- autoritativní validace vybírá deterministický kód pro každý překryv;
- cleanup a context close zachovají primární fixed error;
- fake-clock testy všech stage deadline, supervisor priority a post-baseline
  `220 s` operational / `222 s` supervisor hranic bez skutečného čekání;
- oddělené integrační scénáře zablokují census `page.evaluate()`, `CLEAR` a
  `BrowserContext.close()`; supervisor v každém vyžádá ukončení smyšleného
  worker/driver/browser jobu, polluje `ActiveProcesses` a rozliší potvrzenou nulu
  od nepotvrzeného konce;
- bootstrap testy ověří `PROC_THREAD_ATTRIBUTE_JOB_LIST` assignment přímo v
  suspended `CreateProcessW`, přesný full argv s executable v `argv[0]`, Windows
  quoting a mutable command buffer, přesný čtyřhandle child allowlist včetně
  standardních `NUL` handlů, non-inheritable Job/IPC handly,
  creation/verification/`ResumeThread` failure, parent crash před resume i po
  resume před `START_BROWSER`, EOF před `START_BROWSER`, profile lease a zákaz
  otevření Playwrightu před validním `START_BROWSER`;
- IPC testy fragmentují prefix i body po jednotlivých bajtech a pokryjí partial
  reads/writes, zero/oversized length, invalid UTF-8/JSON/schema/version/sequence,
  duplicate/unsolicited/late response, oba broken channels, worker exit bez
  payloadu, write/read timeout a truncated frame;
- supervisor priority testy pokryjí primary + cleanup/close/shutdown failure,
  cleanup/close/process-tree failure bez primary, output failure po validním
  výsledku a současný deadline + `KeyboardInterrupt`;
- Win32 console wait testy pokryjí Enter, nerelevantní `INPUT_RECORD`, worker
  exit podle existující tabulky, Ctrl+C s původně zapnutým i vypnutým
  `ENABLE_PROCESSED_INPUT`, redirected stdin, query/set/restore i handler
  registration/cleanup failure, pre-baseline neomezený ale přerušitelný wait a
  všechny manual/global deadline ties bez background input threadu;
- output line/byte limity, failure před terminal line, partial/final terminal
  write/flush failure a zákaz druhého public code po pokusu o terminal success.

### Syntetické browser testy

Testy používají pouze `page.set_content()`, zjevně smyšlené HTML a context route,
která abortuje každý síťový request. Nepoužívají produkční HTML, screenshot,
trace, video, HAR ani persistentní profil.

Minimální scénáře:

- dva event rooty s unikátními syntetickými `data-event-key` values;
- baseline bez detailu, ruční signál bez otevření a close signál se stále
  otevřeným detailem skončí fixed fatal kódy bez candidate verdictu;
- baseline/open/close se strukturálně potvrzeným známým syntetickým detailem a
  stejnými event roots a values;
- neznámý a ambiguous detail po manual-open potvrzení jsou fatal a nic se
  automaticky nezavře;
- ekvivalentní rerender s novými DOM uzly a stejným value setem;
- prohození rootů se stejnými values: set stability `true`, order stability
  `false`, technically stable `true`;
- jedna value změněna;
- candidate chybí na jednom rootu;
- duplicate value;
- event count se zvýší nebo sníží;
- druhá event layer nebo změněný fingerprint;
- root attributes mimo allowlist, včetně syntetického názvu nesoucího canary
  osobní/provozní text, se nevrátí ani neobjeví v žádném public payloadu;
  allowlisted atributy pouze na descendants se nehodnotí;
- skutečné synthetic candidate values nejsou v žádném public payloadu, Python
  procesu, IPC, modelu, `repr`, stdout, stderr ani fixed error;
- candidate cesta nevolá `evaluate_handle`, `get_property`, `get_properties` ani
  `json_value` a nevytváří remote-object preview;
- privátní closure state je po úspěchu i chybě cleared a listener odstraněn;
- reload/navigation odstraní execution context a vede výhradně k
  `ID0_BROWSER_STATE_LOST`;
- `window.syntheticClicks` zůstane `0` ve všech scénářích;
- `BrowserContext.close()` se vyžádá při success, fixed error i
  `KeyboardInterrupt`; success vyžaduje potvrzený graceful close, zatímco
  zablokovaný/error close přechází do Job termination bez falešného potvrzení.

`data-event-key` je pouze zjevně syntetický allowlisted testovací název. Test jeho
mechaniky nepředstavuje tvrzení, že stejný atribut existuje v Termino.

## Interaction audit

Před a po budoucí implementaci se zaznamená počet a lokace produkčních
`.click(`. Očekávání zůstává přesně tři současná místa: calendar event Phase 4B,
`Více` a ověřený close. ID0 nepřidá žádné další.

Diff se staticky prohledá na:

```text
force=
dispatch_event
mouse.
keyboard.
press(
screenshot
trace
video
har
```

ID0 nesmí zavést `evaluate_handle` vracející calendar event, persistentní event
handle, candidate-state `JSHandle`, JavaScript click, souřadnice, `Escape`,
automatický close ani multi-event loop. Dočasné detail handly smějí vzniknout
jen uvnitř existujícího `find_detail_structure()` pro state proof a musí se uvolnit
před následujícím census. ID0 nevlastní žádný dlouhodobý Playwright handle.

## Privacy audit

Před review se všechny změněné a nové soubory zkontrolují na jména, e-maily,
telefony, klientská data, auth state, cookies, tokeny, produkční URL s
identifikátory, skutečné event texty, candidate values, produkční HTML a runtime
artefakty.

Testy musí používat pouze jednoznačně syntetické názvy a hodnoty. Výstupní testy
vloží do privátní closure výrazné canary hodnoty a ověří jejich nepřítomnost
v jakémkoli browser return value, Python procesu, IPC, public payloadu, modelu,
`repr`, stdout, stderr i error paths. Aplikace nebude
nabízet uložení diagnostiky a nevytvoří HTML, screenshot, trace, video, HAR ani
jiný soubor.

## Rozhodnutí

Phase 4C-ID0 je bezpečně implementovatelný bez tvrzení o existenci konkrétního
Termino atributu, protože technicky porovná pouze dva předem schválené generické
root-only names ze source-controlled allowlistu. Jiné runtime names neobjevuje
ani nepublikuje a raw values ponechá uvnitř transientní browserové paměti. Jeho
pozitivní výsledek je vždy pouze `TECHNICALLY_STABLE_UNAPPROVED`.

Phase 4C-ID1 musí být další samostatný explicitní krok. Dokud neprokáže význam,
původ a necitlivost právě jednoho konkrétního kandidáta vedle jeho technické
stability, `EVENT_STABLE_IDENTITY_UNKNOWN` zůstává `BLOCKER` a Phase 4C2 se
nesmí implementovat.

## Self-review čtvrtých oprav

- **A — worker command line skutečně spustí Python modul: PASS.**
  `lpApplicationName` je canonical `sys.executable`; `lpCommandLine` vzniká přes
  Windows quoting z full argv začínajícího stejným `sys.executable`, pokračuje
  `-m termino_exporter.identity_candidate_worker` a je předán v mutable
  `ctypes.create_unicode_buffer`. `-m` tedy není `argv[0]`.
- **B — bootstrap je race-safe i při parent crash: PASS.** Jediný normativní
  mechanismus je suspended `CreateProcessW` s atomickým
  `PROC_THREAD_ATTRIBUTE_JOB_LIST`. Membership se ověří před jediným
  `ResumeThread`; parent crash před resume ukončí již přiřazený suspendovaný
  proces přes `KILL_ON_JOB_CLOSE`, po resume a před `START_BROWSER` jej ukončí
  Job Object nebo worker skončí na EOF. Python nikdy neběží mimo job a Playwright
  ani Chromium se neotevře před validním `START_BROWSER`.
- **C — candidate names jsou fail-closed privacy safe: PASS.** ID0 adresuje a
  publikuje pouze dva exact předem reviewované generické názvy ze
  source-controlled allowlistu. Ostatní runtime attribute names se neenumerují,
  nehashují, nepseudonymizují a neopouštějí browser context. ID0 pouze technicky
  ověřuje kandidáta; ID1 nadále vyžaduje oddělený semantic/privacy proof a ID0
  nikdy nevytvoří approved key.
- **D — Ctrl+C funguje nezávisle na původním console mode: PASS.** Každý manual
  wait uloží původní mode, v případě potřeby zapne `ENABLE_PROCESSED_INPUT`,
  nainstaluje handler signalizující parent-owned event a sleduje jej spolu s
  console inputem, workerem a deadlines. `finally` vždy zkusí přesný restore i
  odregistraci a všechny setup/cleanup chyby mají fixed sanitizované mapování.
  I neomezený pre-baseline wait zůstává přerušitelný; není použit `input()` ani
  neomezený background thread.
- **E — všechny dříve PASS invarianty zůstaly PASS.** Exact handle inheritance a
  ownership, úplný IPC state machine, worker-exit/frame mapping, terminal-result
  output kontrakt, known-detail terminologie, operational/supervisor deadline
  `220/222 s`, global timeout clipping, browser-only raw candidate values, zákaz
  candidate `JSHandle`/`evaluate_handle`, nulový tool click, zákaz ordinalu jako
  identity, bounded output/resources a pravdivé potvrzení ukončení výhradně přes
  `ActiveProcesses == 0` zůstávají normativní. ID0/ID1 jsou oddělené,
  `EVENT_STABLE_IDENTITY_UNKNOWN` zůstává blocker a Phase 4C2 zůstává blokována.
