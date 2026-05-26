"""Bestell- und Storno-Fristen für MaderLunch.

Regeln (Wochenblock-Logik):
- Montag + Dienstag (Servier-Tag) → Cutoff: Freitag 13:00 der Vorwoche
- Mittwoch–Freitag (Servier-Tag)   → Cutoff: Dienstag 13:00 derselben Woche

Storno-Frist ist identisch mit Bestell-Frist (gleicher Cutoff).

Feiertage werden bewusst NICHT berücksichtigt — fällt der Cutoff-Tag auf
einen Feiertag, gilt er trotzdem (Stand: Produktentscheidung MVP).

Wochenenden als Servier-Tag sind außerhalb des Geltungsbereichs; die Funktion
wirft dafür eine `ValueError`, weil ein Speiseplan an Sa/So nicht vorgesehen ist.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.utils import timezone


CUTOFF_HOUR = 13
CUTOFF_MINUTE = 0


def get_order_deadline(serving_date: date) -> datetime:
    """Liefert den letztmöglichen Bestell-/Storno-Zeitpunkt (aware datetime, lokale TZ).

    Der zurückgegebene Zeitpunkt ist *inklusive* — Bestellungen sind erlaubt,
    solange `now() <= get_order_deadline(serving_date)`.
    """
    weekday = serving_date.weekday()  # Mo=0, Di=1, Mi=2, Do=3, Fr=4, Sa=5, So=6

    if weekday in (0, 1):
        # Servier-Tag Mo/Di → vorheriger Freitag 13:00
        monday_of_week = serving_date - timedelta(days=weekday)
        cutoff_date = monday_of_week - timedelta(days=3)  # Mo - 3 = Freitag der Vorwoche
    elif weekday in (2, 3, 4):
        # Servier-Tag Mi/Do/Fr → Dienstag 13:00 derselben Woche
        monday_of_week = serving_date - timedelta(days=weekday)
        cutoff_date = monday_of_week + timedelta(days=1)  # Dienstag
    else:
        raise ValueError(
            f"Servier-Tag {serving_date.isoformat()} ist ein Wochenende — "
            "Speisepläne sind nur Mo–Fr vorgesehen."
        )

    naive = datetime.combine(cutoff_date, time(CUTOFF_HOUR, CUTOFF_MINUTE))
    return timezone.make_aware(naive, timezone.get_current_timezone())


def is_order_window_open(serving_date: date, now: datetime | None = None) -> bool:
    """True, solange für den gegebenen Servier-Tag bestellt/storniert werden darf."""
    now = now or timezone.localtime()
    try:
        deadline = get_order_deadline(serving_date)
    except ValueError:
        return False
    return now <= deadline
