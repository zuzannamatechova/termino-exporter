# Termino Exporter

Termino Exporter je připravovaná lokální aplikace pro Windows, která bude z kalendáře
Termino načítat rezervace ve zvoleném období a exportovat je do souboru Excel.

## Stav projektu

Projekt obsahuje otestovaný základ a ruční kontrolní příkaz `inspect-one`. Tento
příkaz otevře viditelný prohlížeč a nechá uživatele ručně vybrat datum i otevřít detail
rezervace. Program bezpečně rozbalí zkrácený obsah, znovu načte aktuální strukturu DOM,
extrahuje známá pole a převede je na jeden objekt `Reservation`. Do terminálu vypíše
pouze explicitně povolené strukturované hodnoty. Procházení celého dne a export do
Excelu zatím nejsou implementovány.

Budoucí komunikace s Termino bude striktně **pouze pro čtení**. Aplikace nebude vytvářet,
upravovat, kopírovat, rušit ani mazat rezervace.

## Veřejný repozitář a osobní údaje

Tento repozitář je veřejný. Do Git historie nikdy nepatří skutečná klientská data,
produkční HTML, snímky obrazovky, záznamy Playwright, profily prohlížeče, cookies,
autentizační stav, exporty ani tajné údaje. Testy a dokumentace smějí používat pouze
zjevně smyšlená data. Lokální soubory vzniklé za běhu mohou obsahovat osobní údaje a
musí zůstat v ignorovaných adresářích.

## Požadavky

- Windows 10 nebo Windows 11
- Python 3.12
- Git

## Instalace ve Windows PowerShell

```powershell
git clone https://github.com/zuzannamatechova/termino-exporter.git
Set-Location termino-exporter
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m playwright install chromium
```

Poslední příkaz připraví Chromium pro příkaz `inspect-one`.

## Příkazová řádka

```powershell
python -m termino_exporter
python -m termino_exporter --help
python -m termino_exporter --version
python -m termino_exporter inspect-one --help
termino-exporter --help
termino-exporter --version
```

Spuštění bez argumentů zobrazí nápovědu. Příkaz `inspect-one` jako jediný spouští
prohlížeč a otevírá zadanou adresu. Nevytváří Excel ani neukládá text rezervace.

## Ruční prohlédnutí jedné rezervace

Před prvním použitím nainstalujte Chromium:

```powershell
python -m playwright install chromium
```

Potom spusťte kontrolu:

```powershell
python -m termino_exporter inspect-one
```

Prohlížeč používá persistentní profil mimo repozitář. Ve Windows je výchozí cesta
`%LOCALAPPDATA%\TerminoExporter\browser-profile`; pokud `LOCALAPPDATA` není dostupné,
použije se `~/.termino-exporter/browser-profile`. Cestu lze změnit pomocí
`--profile-dir`, adresu pomocí `--url` a časový limit pomocí `--timeout-seconds`.

Po otevření prohlížeče se uživatel ručně přihlásí, přejde na správné datum, klikne na
požadovanou rezervaci a nechá detail otevřený. Teprve potom se vrátí do terminálu a
stiskne Enter. Program automaticky nehledá ani neotevírá události.

Termino otevřený detail neoznačuje standardní dialogovou rolí. Program proto vyžaduje
právě jeden viditelný přesný popisek `Datum` a `Čas` a najde jejich nejbližší společný,
skutečně scrollovatelný DOM předek. Detekce nepoužívá CSS třídy ani ID. Detail zavře
pomocí nepojmenovaného ikonového křížku, pouze pokud právě jeden viditelný element
`button` bezpečně strukturálně odpovídá: v DOM předchází rolovacímu obsahu, obsahuje
SVG a jeho trimovaný textový obsah je prázdný. Akce `Zkopírovat rezervaci`, `Odstranit` a
`Upravit` pod obsahem jsou výslovně vyloučeny. Nepoužívají se souřadnice, ID ani CSS
třídy. Před kliknutím musí být jednoznačně potvrzeny sourozenecké větve v pořadí
hlavička, rolovací obsah a zakázané akce.

Běžný `inner_text` načte celý aktuální DOM rolovacího panelu, ale dlouhou poznámku
Termino zkracuje už v DOM. Program proto před finálním čtením postupně rozbalí
viditelné prvky `button` s přesným přístupným názvem `Více`, pouze uvnitř rolovacího
obsahu. Po úspěchu se tlačítko změní na `Méně`; aplikace na `Méně` nikdy nekliká.
Po rozbalení program znovu rozpozná strukturu detailu, protože Termino může původní DOM
nahradit. Ze strukturálních vztahů popisek → hodnota vytvoří mapu polí, název klienta
načte z ověřené hlavičky a data převede čistým parserem na `Reservation`. Očištěný
`raw_detail` zůstává pouze v paměti a nikdy se nevypisuje. Terminálový výstup obsahuje
jen pevný allowlist strukturovaných hodnot v deterministickém formátu.

Příkaz je určen výhradně pro čtení. Nesmí se používat k vytváření, úpravám, kopírování,
rušení ani mazání rezervací. Podrobný bezpečný postup je v
[manuálním testu Phase 1](docs/PHASE1_MANUAL_TEST.md).

## Vývoj a kontroly

```powershell
python -m pytest
python -m pytest --cov=termino_exporter --cov-report=term-missing
python -m ruff check .
python -m ruff format --check .
python -m ruff format .
python -m mypy src
```

## Dokumentace

- [Funkční specifikace](docs/SPEC.md)
- [Plán vývoje](docs/ROADMAP.md)
- [Datový model](docs/DATA_MODEL.md)
- [Bezpečnost a soukromí](docs/SECURITY.md)
- [Ruční test Phase 1](docs/PHASE1_MANUAL_TEST.md)
- [Ruční test Phase 2](docs/PHASE2_MANUAL_TEST.md)
- [Ruční test Phase 3](docs/PHASE3_MANUAL_TEST.md)

Licence zatím nebyla vlastníkem repozitáře zvolena.
