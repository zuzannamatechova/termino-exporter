# Plán vývoje

## Phase 0 — Repozitář a nástroje

Hotovo, když lze projekt nainstalovat, funguje nápověda CLI, procházejí testy, lint,
kontrola formátování a typová kontrola a je nakonfigurované CI.

## Phase 1 — Prohlédnout jednu ručně vybranou rezervaci

Hotovo, když se otevře viditelný prohlížeč Playwright, uživatel se může ručně přihlásit,
jedna známá rezervace se bezpečně otevře, úplný text dialogu lze lokálně vypsat a žádná
data se neuloží do Gitu.

## Phase 2 — Načíst a posouvat jeden celý dialog

Hotovo, když je nalezen rolovací kontejner dialogu, relevantní prvky „Více“ jsou
rozbaleny, obsah se shromáždí bez zjevných duplicit a dialog se bezpečně zavře.

## Phase 3 — Zpracovat jednu rezervaci

Hotovo, když se získaný detail převede na `Reservation`, podporují se chybějící hodnoty
a jednotkové testy parseru používají smyšlené vstupy.

## Phase 4 — Zpracovat jeden celý den

Hotovo, když se zpracují všechny klientské rezervace dne, přeskočí se blokace a
neklientské události, jedna chyba nezastaví ostatní rezervace a zabrání se duplicitám.

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
