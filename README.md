# Termino Exporter

Termino Exporter je připravovaná lokální aplikace pro Windows, která bude z kalendáře
Termino načítat rezervace ve zvoleném období a exportovat je do souboru Excel.

## Stav projektu

Projekt nyní obsahuje pouze otestovaný základ: Python balíček, příkazovou řádku, datový
model a vývojové nástroje. Čtení dat z Termino, ovládání prohlížeče ani export do Excelu
zatím nejsou implementovány. Nápověda příkazové řádky tuto skutečnost výslovně uvádí.

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

Poslední příkaz připraví Chromium pro budoucí vývoj. Současná aplikace prohlížeč
nespouští.

## Příkazová řádka

```powershell
python -m termino_exporter
python -m termino_exporter --help
python -m termino_exporter --version
termino-exporter --help
termino-exporter --version
```

Spuštění bez argumentů zobrazí nápovědu. Žádný současný příkaz nepřistupuje k internetu,
nespouští prohlížeč ani nevytváří Excel.

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

Licence zatím nebyla vlastníkem repozitáře zvolena.
