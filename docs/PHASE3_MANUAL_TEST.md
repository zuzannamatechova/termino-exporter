# Ruční test Phase 3

Tento test ověřuje zpracování jedné ručně otevřené dummy rezervace přes tok DOM →
strukturální extrakce → čistý parser → `Reservation` → bezpečný terminálový výstup.

## Bezpečnostní podmínky

- Použijte pouze rezervaci se zjevně smyšleným klientem `TEST OSOBA`.
- Nepoužívejte údaje jiných rezervací.
- Nevytvářejte ani neukládejte screenshot, HTML, trace, video nebo terminálový výstup.
- Nevkládejte obsah rezervace ani autentizační stav do repozitáře.
- Neklikejte na `Upravit`, `Odstranit` ani `Zkopírovat rezervaci`.

## Postup

1. Spusťte:

   ```powershell
   .\.venv\Scripts\python.exe -m termino_exporter inspect-one
   ```

2. Ručně se přihlaste a přejděte na datum dummy rezervace.
3. Ručně otevřete detail `TEST OSOBA` a nechte jej otevřený.
4. Vraťte se do terminálu a stiskněte Enter.
5. Ověřte, že se všechny zkrácené části `Více` rozbalily.
6. Ověřte jeden blok mezi značkami `Strukturovaná rezervace` a
   `Konec strukturované rezervace`.
7. Ověřte deterministické formáty data, času, ceny a času vytvoření.
8. Ověřte, že víceřádková testovací poznámka zůstala víceřádková.
9. Ověřte, že se nevytiskl celý surový detail ani označení `raw_detail`.
10. Ověřte, že se detail jednou zavřel ověřeným křížkem a browser context skončil.

## Očekávané omezení

Phase 3 zpracuje právě jednu rezervaci, kterou uživatel ručně otevře. Automatické
procházení všech rezervací jednoho dne začne až v Phase 4. Výsledek se zatím neukládá
do Excelu ani jiného souboru.
