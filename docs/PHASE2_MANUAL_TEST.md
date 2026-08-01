# Ruční test Phase 2

Tento postup ověřuje bezpečné rozbalení celého DOM obsahu jedné ručně otevřené
rezervace. Použijte pouze dummy rezervaci `Jana Nováková`; nevkládejte do dokumentace
telefon, e-mail, screenshot ani terminálový výstup rezervace.

## Předpoklady

- Projekt je nainstalovaný v aktivním virtuálním prostředí.
- Chromium je nainstalované příkazem `python -m playwright install chromium`.
- Dummy rezervace obsahuje dlouhou smyšlenou poznámku, kterou Termino zkrátí
  tlačítkem `Více`.

## Postup

1. Spusťte:

   ```powershell
   python -m termino_exporter inspect-one
   ```

2. Ve viditelném Chromium se ručně přihlaste.
3. Ručně přejděte na správné datum a otevřete dummy rezervaci.
4. Nechte detail otevřený, vraťte se do terminálu a stiskněte Enter.
5. Oveřte, že se každý prvek `Více` uvnitř rolovacího obsahu rozbalil a změnil
   na `Méně`.
6. Oveřte, že terminál vypsal text pouze jednou a až po rozbalení.
7. Oveřte, že detail byl nakonec zavřen jediným kliknutím na bezpečný křížek.

## Bezpečnost

- Kliká se pouze na viditelný `button` s přesným názvem `Více`, který je potomkem
  již ověřeného rolovacího kontejneru.
- Po každém kliknutí se DOM znovu načte a starý handle se pro další kliknutí
  nepoužije.
- Úspěch potvrzuje snížení počtu `Více`, změna právě kliknutého tlačítka
  na `Méně` nebo prodloužení textu kontejneru.
- Maximálně lze provést deset úspěšných rozbalení na jeden detail.
- Aplikace nikdy nekliká na `Méně`, `Upravit`, `Odstranit` ani
  `Zkopírovat rezervaci`.
- Nepoužívají se CSS třídy, ID, XPath, souřadnice, OCR, screenshoty, JavaScriptové
  kliknutí, `force=True` ani Escape.

## Známá omezení

- Rezervaci a datum vybírá uživatel ručně.
- Program neparsuje jednotlivá pole a nevytváří export.
- Pokud Termino změní přístupný název nebo DOM chování tlačítka, operace
  bezpečně skončí bez opakovaného kliknutí.
