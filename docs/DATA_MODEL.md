# Datový model

`Reservation` je neměnný datový objekt. Všechny položky jsou volitelné a chybějící
hodnoty zůstávají prázdné.

| Pole v Pythonu | Význam | Typ v Pythonu | Sloupec v Excelu | Může chybět | Formátování |
|---|---|---|---|---|---|
| `reservation_id` | Identifikátor rezervace | `str \| None` | ID rezervace | ano | Text |
| `date` | Datum rezervace | `date \| None` | Datum | ano | Nativní datum, ne text |
| `start_time` | Čas začátku | `time \| None` | Začátek | ano | Nativní čas |
| `end_time` | Čas konce | `time \| None` | Konec | ano | Nativní čas |
| `first_name` | Jméno klienta | `str \| None` | Jméno | ano | Text |
| `last_name` | Příjmení klienta | `str \| None` | Příjmení | ano | Text |
| `phone` | Telefon | `str \| None` | Telefon | ano | Text, zachovat předvolbu |
| `email` | E-mail | `str \| None` | E-mail | ano | Text |
| `service` | Objednaná služba | `str \| None` | Služba | ano | Text |
| `package_name` | Název balíčku | `str \| None` | Balíček | ano | Text |
| `workplace` | Pracoviště | `str \| None` | Pracoviště | ano | Text |
| `duration_minutes` | Délka v minutách | `int \| None` | Délka (min) | ano | Celé číslo |
| `price` | Cena | `Decimal \| None` | Cena | ano | Číselná buňka |
| `status` | Stav rezervace | `str \| None` | Stav | ano | Text |
| `source` | Zdroj rezervace | `str \| None` | Zdroj | ano | Text |
| `note` | Poznámka | `str \| None` | Poznámka | ano | Víceřádkový text |
| `raw_detail` | Nezpracovaný detail | `str \| None` | Surový detail | ano | Pouze volitelná lokální diagnostika |

`raw_detail` může obsahovat osobní údaje a nikdy se nesmí uložit do Gitu. Automatické
rozdělení celého jména na jméno a příjmení bude navrženo až po pochopení skutečného
chování rozhraní; současný model je neprovádí.
