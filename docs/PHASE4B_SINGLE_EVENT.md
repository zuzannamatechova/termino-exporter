# Phase 4B — jedna testovací událost

Tato omezená fáze automaticky otevře a zpracuje právě jednu testovací klientskou rezervaci
v ručně zvoleném pohledu Den. Nezpracovává celý den, více událostí ani rozsah dat.

## Bezpečný ruční postup

Použijte pouze datum obsahující právě jednu zjevně smyšlenou klientskou rezervaci, například
`TEST OSOBA`, a spusťte:

```powershell
python -m termino_exporter inspect-single-event
```

Ve viditelném prohlížeči se ručně přihlaste, zvolte pohled Den a přejděte na připravené
datum. Detail události neotvírejte. Vraťte se do terminálu a stiskněte Enter.

## Bezpečnostní tok

Program vyžaduje právě jeden kalendářní kontext, jednu gridcell vrstvu, jednu event layer,
jeden sloupec a jeden obecný event block. Z anonymního snapshotu vytvoří interní neměnný
plán. Poté ověří, že detail není otevřený. Druhý nezávislý census znovu provede celé
jednoznačné rozpoznání a porovná pouze anonymní významový fingerprint: počet sloupců a bloků
a omezené číselné a booleanové strukturální metriky vybrané grid a event vrstvy. Snapshotové
ordinaly se mezi censy nepoužívají jako identita. Atomický poslední DOM průchod pak znovu
určí aktuální vrstvy bez starého ordinalu, ověří stejný fingerprint a vrátí jediný živý
event block, který dostane právě jeden pokus o kliknutí.

Phase 4B přebírá kanonizovaný census z Phase 4A. V pohledu Den se vnořené vnější obaly
kolem stejného živého `gridcell` nepočítají jako další nezávislé vrstvy. Kanonizace je
povolena jen při shodě skutečné DOM identity všech buněk a neznamená pravidlo „vyber
nejhlubší“. Dva nezávislé kandidáty resolver nikdy nesloučí ani nezredukuje na první shodu.
Context root je rodičem kanonického anchoru a obsahuje každou skutečnou paralelní vrstvu
právě jednou. Počet těchto vrstev není počet dnů. Snapshot i atomické vyhledání handle
vyžadují, aby jediná event layer následovala za grid vrstvou; obsahové vrstvy před gridem
se ignorují.

Kalendářní blok se neklasifikuje podle textu, barvy, polohy ani vzhledu. Rezervace je
rozpoznána až podle jednoznačné existující struktury otevřeného detailu
HEADER–CONTENT–ACTION. Poté se použije stávající `inspect_open_detail`, včetně rozbalení
`Více`, extrakce, parseru, bezpečného výstupu a zavření.

Pokud detail nemá známou rezervační strukturu, operace skončí pevným bezpečným kódem.
Program netvrdí, že jde o blokaci nebo dovolenou, a nekliká na neověřený zavírací prvek.

Před event click se kontroluje, že nejsou viditelné popisky otevřeného detailu. Úplná
nepřítomnost obou popisků znamená zavřený kalendář; částečná, duplicitní nebo jinak
víceznačná struktura operaci bezpečně zastaví. Po kliknutí se podporovaný detail zpracuje
právě jednou funkcí `inspect_open_detail`. Zdrojový kód obsahuje tři interaktivní místa:
event, `Více` a ověřené zavření. Skutečný počet kliknutí za běh je jeden event, nula až více
bezpečných rozbalení a jedno zavření potvrzeného detailu; není vždy přesně tři.

Více událostí, automatické rozlišování blokací, zpracování celého dne, rozsah dat a Excel
patří do dalších fází. Phase 4 jako celek ještě není dokončená.
