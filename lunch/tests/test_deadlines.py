"""Tests für lunch.deadlines.

Wichtig: Die App läuft auf TIME_ZONE = 'Europe/Berlin'. Die Tests prüfen,
dass Cutoffs *lokal* in dieser Zone berechnet werden (sonst rutscht der
13:00-Cutoff bei DST-Umstellung).
"""
from datetime import date, datetime, timezone as dt_timezone

import pytest
from django.utils import timezone
from zoneinfo import ZoneInfo

from lunch.deadlines import get_order_deadline, is_order_window_open


BERLIN = ZoneInfo("Europe/Berlin")


# ─── get_order_deadline ─────────────────────────────────────────

class TestGetOrderDeadline:
    def test_monday_serving_cutoff_is_previous_friday_13(self):
        # Mo 03.11.2025 → Cutoff Fr 31.10.2025 13:00 lokal
        deadline = get_order_deadline(date(2025, 11, 3))
        assert deadline == datetime(2025, 10, 31, 13, 0, tzinfo=BERLIN)

    def test_tuesday_serving_cutoff_is_previous_friday_13(self):
        # Di 04.11.2025 → Cutoff Fr 31.10.2025 13:00
        deadline = get_order_deadline(date(2025, 11, 4))
        assert deadline == datetime(2025, 10, 31, 13, 0, tzinfo=BERLIN)

    def test_wednesday_serving_cutoff_is_same_week_tuesday_13(self):
        # Mi 05.11.2025 → Cutoff Di 04.11.2025 13:00
        deadline = get_order_deadline(date(2025, 11, 5))
        assert deadline == datetime(2025, 11, 4, 13, 0, tzinfo=BERLIN)

    def test_thursday_serving_cutoff_is_same_week_tuesday_13(self):
        # Do 06.11.2025 → Cutoff Di 04.11.2025 13:00
        deadline = get_order_deadline(date(2025, 11, 6))
        assert deadline == datetime(2025, 11, 4, 13, 0, tzinfo=BERLIN)

    def test_friday_serving_cutoff_is_same_week_tuesday_13(self):
        # Fr 07.11.2025 → Cutoff Di 04.11.2025 13:00
        deadline = get_order_deadline(date(2025, 11, 7))
        assert deadline == datetime(2025, 11, 4, 13, 0, tzinfo=BERLIN)

    def test_saturday_raises(self):
        with pytest.raises(ValueError):
            get_order_deadline(date(2025, 11, 8))

    def test_sunday_raises(self):
        with pytest.raises(ValueError):
            get_order_deadline(date(2025, 11, 9))

    def test_dst_transition_spring_forward(self):
        """30.03.2025 = Sommerzeit-Beginn (CET→CEST). Cutoff für Mo 31.03.
        muss lokal 13:00 sein, nicht 12:00 oder 14:00 UTC-verschoben."""
        # Mo 31.03.2025 → Cutoff Fr 28.03.2025 13:00 (noch CET, UTC+1)
        deadline = get_order_deadline(date(2025, 3, 31))
        assert deadline.hour == 13
        assert deadline.minute == 0
        # UTC-Äquivalent: 12:00 UTC (CET = UTC+1)
        assert deadline.astimezone(dt_timezone.utc).hour == 12

    def test_dst_transition_fall_back(self):
        """26.10.2025 = Winterzeit-Beginn (CEST→CET). Cutoff für Mi 29.10.
        muss lokal 13:00 sein."""
        # Mi 29.10.2025 → Cutoff Di 28.10.2025 13:00 (schon CET, UTC+1)
        deadline = get_order_deadline(date(2025, 10, 29))
        assert deadline.hour == 13
        assert deadline.astimezone(dt_timezone.utc).hour == 12

    def test_cutoff_crosses_year_boundary(self):
        """Mo 05.01.2026 → Cutoff Fr 02.01.2026 13:00."""
        deadline = get_order_deadline(date(2026, 1, 5))
        assert deadline == datetime(2026, 1, 2, 13, 0, tzinfo=BERLIN)

    def test_monday_after_holiday_week_still_uses_previous_friday(self):
        """Feiertage werden bewusst ignoriert — 01.05.2026 ist Tag d. Arbeit
        (Freitag). Cutoff für Mo 04.05.2026 ist trotzdem Fr 01.05. 13:00."""
        deadline = get_order_deadline(date(2026, 5, 4))
        assert deadline == datetime(2026, 5, 1, 13, 0, tzinfo=BERLIN)


# ─── is_order_window_open ───────────────────────────────────────

class TestIsOrderWindowOpen:
    def test_open_before_cutoff(self):
        # 1 Minute vor Cutoff
        serving = date(2025, 11, 3)  # Mo
        now = datetime(2025, 10, 31, 12, 59, tzinfo=BERLIN)
        assert is_order_window_open(serving, now=now) is True

    def test_open_at_cutoff(self):
        # genau am Cutoff (inklusiv)
        serving = date(2025, 11, 3)
        now = datetime(2025, 10, 31, 13, 0, tzinfo=BERLIN)
        assert is_order_window_open(serving, now=now) is True

    def test_closed_after_cutoff(self):
        # 1 Minute nach Cutoff
        serving = date(2025, 11, 3)
        now = datetime(2025, 10, 31, 13, 1, tzinfo=BERLIN)
        assert is_order_window_open(serving, now=now) is False

    def test_closed_for_weekend_serving_date(self):
        # Servier-Tag Samstag → niemals offen
        serving = date(2025, 11, 8)
        now = datetime(2025, 10, 31, 9, 0, tzinfo=BERLIN)
        assert is_order_window_open(serving, now=now) is False
