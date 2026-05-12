"""Reproduzierbarer CSV-Export.

Schema-Version wird mitexportiert. Spaltenkopf, Reihenfolge und Trennzeichen
sind hier deklariert und versioniert. Änderung am Schema → CSV_SCHEMA_VERSION
erhöhen + dokumentieren.
"""
from __future__ import annotations

import csv
import io
from datetime import date

from django.db.models import QuerySet

CSV_SCHEMA_VERSION = "1.0.0"
CSV_DELIMITER = ";"  # Excel-DE-freundlich

ORDER_COLUMNS = [
    "schema_version",
    "order_id",
    "serving_date",
    "location_code",
    "canteen_code",
    "employee_id",
    "username",
    "cost_center_code",
    "product_name",
    "quantity",
    "unit_price_gross",
    "subsidy_amount",
    "net_to_employee",
    "status",
    "placed_at_iso",
    "served_at_iso",
]


def export_orders_csv(orders: QuerySet, *, period_from: date, period_to: date) -> bytes:
    """Liefert CSV-Bytes (UTF-8 mit BOM für Excel-DE)."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=CSV_DELIMITER, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(ORDER_COLUMNS)

    # Deterministische Sortierung für Reproduzierbarkeit
    qs = (
        orders
        .select_related(
            "user_profile__user",
            "user_profile__cost_center",
            "meal_slot__product",
            "meal_slot__mealplan__canteen__location",
        )
        .order_by("meal_slot__mealplan__serving_date", "user_profile__user__username", "pk")
    )

    for o in qs:
        slot = o.meal_slot
        plan = slot.mealplan
        canteen = plan.canteen
        loc = canteen.location
        cc = o.user_profile.cost_center
        writer.writerow([
            CSV_SCHEMA_VERSION,
            o.pk,
            plan.serving_date.isoformat(),
            loc.code if loc else "",
            canteen.code,
            o.user_profile.employee_id or "",
            o.user_profile.user.username,
            cc.code if cc else "",
            slot.product.name,
            o.quantity,
            f"{o.unit_price_gross:.2f}",
            f"{o.subsidy_amount:.2f}",
            f"{o.net_to_employee:.2f}",
            o.status,
            o.placed_at.isoformat() if o.placed_at else "",
            o.served_at.isoformat() if o.served_at else "",
        ])

    # BOM, damit Excel-DE UTF-8 erkennt
    return ("\ufeff" + buf.getvalue()).encode("utf-8")
