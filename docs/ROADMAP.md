# Plán vývoje

## Phase 0 — Repozitář a nástroje

Hotovo, když lze projekt nainstalovat, funguje nápověda CLI, procházejí testy, lint,
kontrola formátování a typová kontrola a je nakonfigurované CI.

## Phase 1 — Prohlédnout jednu ručně vybranou rezervaci

Hotovo, když se otevře viditelný prohlížeč Playwright, uživatel se může ručně přihlásit,
ručně přejde na správné datum a sám otevře jednu známou rezervaci, aktuálně dostupný text
detailu lze lokálně vypsat a žádná data se neuloží do Gitu. Termino nepoužívá standardní
dialogovou roli, proto se obsah bezpečně určí přes jedinečné statické popisky `Datum` a
`Čas` a jejich společného skutečně scrollovatelného DOM předka, bez CSS tříd a ID.
Uživatel detail stále otevírá ručně; program jej neposouvá ani nekliká na `Více`.

## Phase 2 — Načíst celý obsah jednoho detailu

Hotovo, když je nalezen rolovací kontejner detailu, všechny přesně pojmenované prvky
`button` s názvem `Více` uvnitř kontejneru jsou postupně a ověřeně rozbaleny, finální
`inner_text` se vypíše pouze jednou a detail se bezpečně zavře. Běžný `inner_text`
načte celý aktuální DOM rolovacího panelu; tlačítko `Méně` se nikdy nepoužívá ke
zpětnému sbalení.

## Phase 3 — Zpracovat jednu rezervaci

Hotovo: jeden ručně otevřený detail se strukturálně extrahuje, převede čistým parserem
na `Reservation`, vypíše bezpečným allowlistem a zavře jedním ověřeným kliknutím.
Podporují se chybějící hodnoty a testy používají pouze smyšlené vstupy.

### Phase 3A — Model a čistý parser strukturovaných polí

Model obsahuje celý `client_name`, neutrální `service_or_package`, počet osob,
zaměstnance, typ rezervace a čas vytvoření. Čistý parser bez závislosti na Playwrightu
přijímá strukturovanou mapu popisků a hodnot; jméno nedělí a službu ani balíček
heuristicky neklasifikuje. `created_at` představuje lokální čas Termino bez informace o
časové zóně a `raw_detail` zůstává pouze v paměti.

### Phase 3B — Bezpečná DOM extrakce

Strukturální extrakce získává mapu popisků a hodnot přímo z DOM a název klienta z
jednoznačně ověřené `HEADER_BRANCH`. Nepoužívá plochý text jako zdroj polí. Bezpečné
zavření i extrakce sdílejí jediný resolver struktury HEADER–CONTENT–ACTION. Před předáním
`raw_detail` odstraní pouze ze svého paměťového klonu skutečný button `Méně`; živý DOM,
obyčejný text v poznámce ani jiné elementy nezmění.

### Phase 3C — Napojení parseru

Po rozbalení se struktura povinně načte znovu. Strukturovaná mapa, `client_name` a
očištěný `raw_detail` se předají čistému parseru a výsledný `Reservation` se vypíše jen
přes explicitně povolená pole. `raw_detail` zůstává v paměti. Navigace přes všechny
rezervace dne zůstává součástí Phase 4.

### Bezpečnostní zpevnění před Phase 4

Profil prohlížeče je odmítnut uvnitř libovolného Git repozitáře. Každý bezpečný kandidát
`Více` dostane nejvýše jeden click a aplikace poté omezenou dobu čeká na potvrzenou změnu
čerstvého DOM. `raw_detail` zůstává pouze v paměti, není v `repr` a neovlivňuje rovnost
objektů. Phase 4 tímto zpevněním nebyla zahájena.

## Phase 4 — Zpracovat jeden celý den

Hotovo, když se zpracují všechny klientské rezervace dne, přeskočí se blokace a
neklientské události, jedna chyba nezastaví ostatní rezervace a zabrání se duplicitám.

### Phase 4A — Bezpečná diagnostika kalendáře

Probíhá pouze strukturální diagnostika celého aktuálně zobrazeného pohledu Den, 3 dny,
Týden nebo Agenda, který uživatel zvolí ručně. Počet sloupců není natvrdo omezen na sedm.
Program události neotevírá, neklasifikuje ani nezpracovává a na nic nekliká. Phase 4 jako
celek ještě není hotová.

První živý test bezpečně nepotvrdil očekávaný semantický kořen. Diagnostika proto používá
přesnější strukturální kotvu `gridcell`; při nule nebo více platných vrstvách skončí
pevným bezpečným kódem a nikdy nevybere první shodu.

Aktuální anonymní DOM pozorování ukotvuje diagnostiku přes jednoznačnou vrstvu denních
větví s rolí `gridcell`. Vedle ní existují pravidelná časová mřížka a prázdné pomocné
vrstvy. Event layer musí mít stejný počet větví a jako jediná obsahovat alespoň jeden malý
neprázdný obsahový blok; element bez textu se nepočítá. Nerozpoznaná záhlaví mimo společný
předek neblokují anonymní výstup. Zcela prázdné období zatím nelze bezpečně rozlišit.
Phase 4A bloky pouze počítá; rezervace a blokace nerozlišuje.

### Phase 4B — Jedna testovací událost v pohledu Den

Program v ručně zvoleném pohledu Den vyžaduje právě jeden obecný calendar event block.
Z čerstvého anonymního snapshotu vytvoří neměnný plán, druhým nezávislým rozpoznáním ověří
stejný anonymní významový fingerprint a na jediný atomicky znovunalezený DOM element klikne
nejvýše jednou. Snapshotové ordinaly nejsou identitou mezi censy. Kalendářní blok se
neklasifikuje podle textu ani vzhledu. Rezervaci potvrzuje až známá struktura otevřeného
detailu; poté se znovu použije existující zpracování jednoho detailu. Neznámá struktura
skončí bezpečně. Více událostí, blokace a celý den zůstávají pro další fázi a Phase 4 jako
celek ještě není dokončená.

## Phase 5 — Zpracovat rozsah dat

Hotovo, když uživatel zadá počáteční a koncové datum, aplikace prochází kalendář, každé
relevantní datum zpracuje právě jednou a hlásí průběh.

## Phase 6 — Export do Excelu

Hotovo, když se úspěšné rezervace zapíší do XLSX, datumy a časy používají nativní
excelové hodnoty, první řádek je ukotvený, filtry jsou zapnuté, chyby jsou na samostatném
listu a lokální exporty Git ignoruje.

## Phase 7 — Spolehlivost a diagnostika

Hotovo, když jsou definované časové limity a opakování, chyby jsou srozumitelné,
diagnostické artefakty jsou volitelné a lokální a diagnostický výstup se neukládá do
Gitu.

## Phase 8 — Uživatelské rozhraní

Hotovo, když uživatel zvolí období a cestu výstupu, vidí průběh a může výsledný soubor
otevřít z aplikace.

## Phase 9 — Spustitelná aplikace pro Windows

Hotovo, když lze aplikaci zabalit, je otestovaná na čistém systému Windows a existují
pokyny pro instalaci a aktualizace.
