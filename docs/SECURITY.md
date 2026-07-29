# Bezpečnost a soukromí

Repozitář je veřejný. V testech, příkladech a dokumentaci smějí být pouze smyšlená data.

- Program nikdy nesmí ukládat heslo do Termino. Přihlášení se očekává ručně ve
  viditelném prohlížeči.
- Profily prohlížeče, cookies a autentizační data jsou pouze lokální.
- Exporty za běhu mohou obsahovat osobní údaje a musí zůstat v adresářích ignorovaných
  Gitem.
- Produkční snímky, záznamy, HTML a logy mohou obsahovat osobní údaje. Ve výchozím
  nastavení musí být vypnuté, nebo se smějí ukládat jen lokálně do ignorovaných
  adresářů.
- Tajné údaje nesmějí být ve zdrojovém kódu, dokumentaci, commitech, popisech issues ani
  pull requestech.
- Aplikace musí vůči Termino zůstat pouze pro čtení. Nesmí vytvářet, upravovat,
  kopírovat, rušit ani mazat rezervace.
- Jakákoli budoucí zapisující akce vyžaduje samostatné výslovné návrhové rozhodnutí a
  nesmí vzniknout jako vedlejší efekt jiné úlohy.

Před commitem je nutné zkontrolovat změny i neznámé soubory a ověřit, že neobsahují
osobní, autentizační ani produkční data.
