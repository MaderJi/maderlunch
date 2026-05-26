# MaderLunch — Patch: Wochenblock-Bestellfristen + Wochen-Überblick

## Was sich ändert

**Neue Fristen-Logik** (ersetzt die alten Cutoff-Felder am `Canteen`):
- Servier-Tag Montag oder Dienstag → Bestell-/Storno-Frist: Freitag 13:00 der Vorwoche
- Servier-Tag Mittwoch bis Freitag → Bestell-/Storno-Frist: Dienstag 13:00 derselben Woche

Feiertage werden bewusst ignoriert. Storno- und Bestell-Frist sind identisch.

**UI-Ergänzungen**:
- Slot-Karten zeigen die Frist und deaktivieren den Bestellen/Stornieren-Button nach Ablauf
- Wochenplan zeigt oben eine kompakte Tagesleiste „Mo Bestellt / Di Keine Bestellung / Mi Bestellt / ..."

## Dateien in diesem Patch

| Datei | Aktion |
|---|---|
| `lunch/deadlines.py` | **neu** — zentrale Cutoff-Logik |
| `lunch/tests/test_deadlines.py` | **neu** — 15 Tests, alle grün |
| `lunch/models.py` | **ersetzen** — `MealSlot.order_window_open` ruft neue Logik; `Canteen.cutoff_order_time` und `cancel_cutoff_minutes_before_serving` entfernt |
| `lunch/migrations/0002_remove_canteen_cutoff_fields.py` | **neu** — entfernt die zwei Felder |
| `lunch/admin.py` | **ersetzen** — `cutoff_order_time` aus `list_display` raus |
| `lunch/views.py` | **ersetzen** — `mealplan_week` liefert `my_order_summary` mit |
| `lunch/management/commands/seed_dev.py` | **ersetzen** — zwei entfernte Default-Felder raus |
| `templates/lunch/_slot.html` | **ersetzen** — Frist-Anzeige, Button-Disable |
| `templates/lunch/mealplan.html` | **ersetzen** — Tagesleiste oben |

## Anwendung

```bash
# Im Projekt-Root
cp lunch/deadlines.py            <repo>/lunch/deadlines.py
mkdir -p <repo>/lunch/tests && touch <repo>/lunch/tests/__init__.py
cp lunch/tests/test_deadlines.py <repo>/lunch/tests/test_deadlines.py
cp lunch/models.py               <repo>/lunch/models.py
cp lunch/admin.py                <repo>/lunch/admin.py
cp lunch/views.py                <repo>/lunch/views.py
cp lunch/seed_dev.py             <repo>/lunch/management/commands/seed_dev.py
cp lunch/migrations/0002_*       <repo>/lunch/migrations/
cp templates/lunch/_slot.html    <repo>/templates/lunch/_slot.html
cp templates/lunch/mealplan.html <repo>/templates/lunch/mealplan.html

# Migration ausführen
python manage.py migrate lunch
```

## Was du noch prüfen solltest

1. **`services.py` Zeile 86 und 117** — die nutzen `slot.order_window_open()` bzw.
   `slot.cancel_window_open()`. Beide funktionieren weiter, weil die Methoden-Signatur
   identisch geblieben ist. Die Fehlertexte („Die Bestellfrist ist abgelaufen.") passen.

2. **Zeitzone** — in `config/settings.py` ist `TIME_ZONE = "Europe/Berlin"` und
   `USE_TZ = True` bereits korrekt gesetzt. Nichts zu tun.

3. **`my_orders.html`** — bleibt unverändert. Die Seite zeigt schon eine
   vollständige Bestellhistorie. Du kannst dort optional einen Filter „Nur zukünftige
   Bestellungen" ergänzen — habe ich bewusst nicht angefasst, weil du gesagt hast,
   die Wochenplan-Ansicht ist der Haupteinstieg.

4. **Bestehende `Canteen`-Daten** — die Migration entfernt nur Felder, keine Zeilen.
   Bestehende Kantinen bleiben erhalten.

5. **Bestehende `MealPlan`-Daten mit Servier-Datum am Wochenende** — falls jemand
   versehentlich einen Plan für Sa/So angelegt hat, wirft `get_order_deadline()` einen
   `ValueError`. Das fängt `is_order_window_open()` ab (gibt False zurück), aber der
   `order_deadline`-Property im Template würde knallen. Wenn unsicher: prüfe einmalig
   `MealPlan.objects.filter(serving_date__week_day__in=[1, 7])` (Django: 1=So, 7=Sa).

## Tests laufen lassen

```bash
pytest lunch/tests/test_deadlines.py -v
```

15 Tests sollten grün sein. Sie decken ab:
- alle 5 Werktage als Servier-Tag
- Wochenenden (Fehler)
- DST-Übergänge Frühjahr & Herbst (Zeitzone lokal korrekt)
- Jahreswechsel
- Feiertag als Cutoff-Tag (wird ignoriert)
- Grenze des Bestellfensters (vor/an/nach Cutoff)

## Bewusste Auslassungen (gemäß deiner Vorgaben)

- Keine E-Mail-Benachrichtigungen
- Keine Feiertags-Sonderlogik
- Keine getrennte Storno-Frist
