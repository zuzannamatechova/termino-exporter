# Ruční test Phase 1

Tento postup ověřuje pouze bezpečné vypsání momentálně dostupného textu jednoho ručně
otevřeného detailu rezervace. Nepoužívejte při dokumentování testu skutečná klientská
data.

Pro lokální ruční test použijte pouze dummy rezervaci `Jana Nováková`.

## Předpoklady

- Aktivní virtuální prostředí s instalací `python -m pip install -e ".[dev]"`.
- Chromium nainstalované příkazem `python -m playwright install chromium`.
- Přístup k Termino a oprávnění zobrazit testovanou rezervaci.
- Čistý pracovní strom bez lokálních profilů nebo autentizačních dat.

## Bezpečnost

- Přihlášení provádí uživatel ručně ve viditelném prohlížeči.
- Heslo nezadávejte do terminálu, argumentů, konfigurace ani zdrojového kódu.
- Neklikejte na `Upravit`, `Odstranit` ani `Zkopírovat rezervaci`.
- Nevytvářejte screenshot, HTML snapshot, trace, video ani log s obsahem rezervace.
- Výstup terminálu nekopírujte do repozitáře, issue ani pull requestu.
- Test nepoužívá OCR, obrazové rozpoznávání, pevné souřadnice ani vynucené kliknutí.

## Postup

1. Spusťte:

   ```powershell
   python -m termino_exporter inspect-one
   ```

2. Ve viditelném Chromium se ručně přihlaste, pokud je to potřeba.
3. Ručně přejděte na správné datum.
4. Ručně klikněte na požadovanou rezervaci a nechte její detail otevřený.
5. Vraťte se do terminálu a stiskněte Enter.
6. Ověřte, že se v terminálu objeví pouze momentálně dostupný text jednoho detailu.
7. Ověřte, že se detail zavřel jediným kliknutím na ikonový křížek.
8. Ověřte, že se prohlížeč po dokončení ukončil.

Program rezervaci automaticky nehledá ani na ni nekliká. Termino otevřený detail
neoznačuje standardní dialogovou rolí. Obsah se určí pouze přes právě jeden viditelný
přesný popisek `Datum` a `Čas` a jejich nejbližší společný, skutečně scrollovatelný DOM
předek. Detekce nepoužívá CSS třídy ani ID.

Termino používá nepojmenovaný ikonový křížek. Program jej přijme pouze jako jediný
viditelný strukturální kandidát, který v DOM předchází rolovacímu obsahu, obsahuje SVG
a jeho trimovaný textový obsah je prázdný. Akce `Zkopírovat rezervaci`, `Odstranit` a `Upravit`
pod obsahem jsou výslovně vyloučeny. K nalezení ani kliknutí se nepoužívají souřadnice,
ID nebo CSS třídy.
Program navíc vyžaduje tři jednoznačné přímé sourozenecké větve stejného kořene
v pořadí hlavička, rolovací obsah a akce. Křížek musí být v hlavičce a všechny tři
zakázané akce v následující akční větvi.

## Očekávané řízené chyby

- Při žádném nebo více viditelných popiscích `Datum` či `Čas` aplikace skončí chybou.
- Pokud popisky nemají společný skutečně scrollovatelný DOM předek, aplikace skončí
  chybou.
- Pokud nelze najít právě jeden bezpečný zavírací prvek, aplikace na jiný prvek
  neklikne. Browser context se přesto korektně ukončí.
- Pokud po jediném kliknutí nelze potvrdit zmizení detailu, aplikace kliknutí neopakuje
  a skončí řízenou chybou.

## Známá omezení

- Příkaz zpracuje pouze jednu ručně vybranou rezervaci.
- Rezervaci musí otevřít uživatel ručně.
- Automatické hledání rezervace a klikání na ni není součástí Phase 1.
- Neposouvá vnitřní obsah detailu a nekliká na `Více`.
- Vypisuje jen aktuálně dostupný text bez parsování jednotlivých polí.
- Nevytváří `Reservation`, Excel ani jiný soubor.
- Skutečné chování lokátorů je nutné ověřit ručním testem proti aktuálnímu DOM; v
  repozitáři se nesmějí ukládat produkční zachycená data.
