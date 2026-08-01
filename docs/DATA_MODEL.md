# Datový model

`Reservation` je neměnný datový objekt. Všechny položky jsou volitelné a chybějící
hodnoty zůstávají prázdné.

| Pole v Pythonu | Význam | Typ v Pythonu | Sloupec v Excelu | Může chybět | Formátování |
|---|---|---|---|---|---|
| `reservation_id` | Identifikátor rezervace | `str \| None` | ID rezervace | ano | Text |
| `client_name` | Celý název klienta | `str \| None` | Klient | ano | Text, bez automatického dělení |
| `date` | Datum rezervace | `date \| None` | Datum | ano | Nativní datum, ne text |
| `start_time` | Čas začátku | `time \| None` | Začátek | ano | Nativní čas |
| `end_time` | Čas konce | `time \| None` | Konec | ano | Nativní čas |
| `first_name` | Jméno klienta | `str \| None` | Jméno | ano | Text |
| `last_name` | Příjmení klienta | `str \| None` | Příjmení | ano | Text |
| `phone` | Telefon | `str \| None` | Telefon | ano | Text, zachovat předvolbu |
| `email` | E-mail | `str \| None` | E-mail | ano | Text |
| `service` | Objednaná služba | `str \| None` | Služba | ano | Text |
| `package_name` | Název balíčku | `str \| None` | Balíček | ano | Text |
| `service_or_package` | Hodnota společného pole Služba nebo balíček | `str \| None` | Služba nebo balíček | ano | Text bez heuristické klasifikace |
| `people_count` | Počet osob na rezervaci | `int \| None` | Počet osob | ano | Kladné celé číslo |
| `workplace` | Pracoviště | `str \| None` | Pracoviště | ano | Text |
| `employee` | Zaměstnanec | `str \| None` | Zaměstnanec | ano | Text |
| `duration_minutes` | Délka v minutách | `int \| None` | Délka (min) | ano | Celé číslo |
| `price` | Cena | `Decimal \| None` | Cena | ano | Číselná buňka |
| `status` | Stav rezervace | `str \| None` | Stav | ano | Text |
| `source` | Zdroj rezervace | `str \| None` | Zdroj | ano | Text |
| `reservation_type` | Typ rezervace | `str \| None` | Typ | ano | Text |
| `created_at` | Čas vytvoření zobrazený Termino | `datetime \| None` | Vytvořena | ano | Lokální čas bez informace o časové zóně |
| `note` | Poznámka | `str \| None` | Poznámka | ano | Víceřádkový text |
| `raw_detail` | Očištěný text detailu | `str \| None` | Surový detail | ano | Pouze v paměti, bez UI prvku `Méně` |

`client_name` uchovává celý název klienta. Parser jej automaticky nerozděluje, protože
česká i zahraniční jména mohou mít více částí a jejich pořadí není spolehlivým podkladem
pro rozdělení. Pole `first_name` a `last_name` zůstávají dočasně zachována kvůli zpětné
kompatibilitě, ale čistý parser je nevyplňuje.

Termino zobrazuje společný popisek `Služba nebo balíček`, ze kterého nelze bezpečně
poznat druh položky. Hodnota se proto ukládá beze změny do `service_or_package` a parser
nevyplňuje starší pole `service` ani `package_name`. `duration_minutes` lze volitelně
odvodit pouze z jednoznačného koncového zápisu, například `(105 min.)`; původní text se
nikdy nemění.

Čistý parser Phase 3A přijímá již strukturovanou mapu popisků a hodnot. Nepoužívá plochý
text detailu, protože popisek může být samostatným řádkem také uvnitř poznámky a neznámé
pole nelze v plochém textu bezpečně rozpoznat. DOM extrakce strukturované mapy a názvu
klienta je proto oddělená v Phase 3B: mapu vytváří přímo ze strukturálních vztahů
popisek → následující hodnota uvnitř ověřené obsahové větve a plochý text neparsuje.

Název klienta se v Phase 3B čte pouze z jednoznačně ověřené `HEADER_BRANCH`. Z jejího
paměťového klonu se pomocí relativní cesty přímých potomků odstraní právě ověřený
zavírací button; jméno se nehledá podle hodnoty ani CSS selektoru. Stejnou společnou
strukturu HEADER–CONTENT–ACTION používá extrakce i bezpečné zavření detailu.

`created_at` je časově naivní `datetime`: představuje místní čas zobrazený Termino,
které v detailu neposkytuje informaci o časové zóně. `raw_detail` může obsahovat osobní
údaje, zůstává pouze v paměti, nesmí se logovat ani zapisovat do souboru a v Phase 3B do
něj vstoupí již očištěný text bez skutečného ovládacího buttonu `Méně`.
Očištění probíhá výhradně v paměťovém klonu obsahové větve: odstraní se pouze elementy
`button` s přesným trimovaným textem `Méně`. Živý DOM, obyčejný text `Méně`, jiné
elementy ani jiná tlačítka se nemění. Napojení extrakce na čistý parser a příkaz
`inspect-one` zajišťuje Phase 3C. Po rozbalení všech prvků `Více` se struktura znovu
načte a extrakce, parser i zavření používají výhradně čerstvé handly. `inspect-one`
vrací jeden `Reservation` a vypisuje pouze explicitní allowlist jeho polí; `raw_detail`
ani kompatibilní pole `first_name`, `last_name`, `service` a `package_name` se nevypisují.
