# Funkční specifikace

## Účel a rozsah

Budoucí aplikace načte rezervace z kalendáře Termino ve zvoleném období a uloží je
lokálně do Excelu. Přístup k Termino bude vždy pouze pro čtení. Tato specifikace
neobsahuje skutečné selektory; ty vzniknou až při bezpečné implementaci a ověření DOM.

## Budoucí pracovní postup

1. Uživatel zvolí počáteční a koncové datum.
2. Aplikace spustí viditelný prohlížeč.
3. Použije vyhrazený lokální profil prohlížeče.
4. Uživatel se v případě potřeby přihlásí ručně.
5. Aplikace otevře kalendář Termino.
6. Vyhledá kandidátní události kalendáře.
7. Rozliší klientské rezervace od blokací a ostatních neklientských událostí.
8. Otevře jednu rezervaci.
9. Pomocí DOM rozpozná dialog detailu.
10. Rozbalí relevantní ovládací prvky označené „Více“.
11. Najde vnitřní rolovací kontejner dialogu.
12. Posouvá tento kontejner po krocích až na konec.
13. Z DOM získá viditelné popisky a hodnoty.
14. Odstraní duplicitní hodnoty vzniklé opakovaným posouváním.
15. Zavře detail pomocí zavíracího prvku dialogu.
16. Pokračuje další rezervací.
17. Selhání jedné rezervace nezastaví celý export.
18. Vyexportuje úspěšné výsledky a samostatný seznam chyb.

## Bezpečné ovládání

Je výslovně zakázáno:

- používat OCR pro získávání údajů rezervace;
- hledat prvky rozhraní rozpoznáváním obrazu;
- používat pevné souřadnice myši nebo předpoklady o rozlišení obrazovky;
- automaticky odesílat formuláře;
- vytvářet, kopírovat, upravovat, mazat nebo rušit rezervace;
- klikat na prvky označené `Upravit`, `Odstranit` nebo `Zkopírovat rezervaci`.

Lokátory mají v tomto pořadí preferovat:

1. přístupné role a přístupné názvy;
2. popisky formulářových polí;
3. stabilní viditelný text;
4. stabilní atributy DOM;
5. selektory CSS pouze tehdy, když robustnější lokátory nejsou dostupné.

Každá interakce musí zachovat stav Termino beze změny.
