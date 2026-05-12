"""Fachliche Services: Zuschuss-Resolver, Bestell-Anlage."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from accounts.models import UserProfile
from audit.services import log_event
from billing.models import SubsidyRule

from .models import MealSlot, Order


def resolve_subsidy(profile: UserProfile, on_date: date, gross_price: Decimal) -> Decimal:
    """Gibt den anwendbaren Zuschuss zurück.

    Auswahl-Logik:
    1. Filter aktiv + im Gültigkeitsfenster.
    2. Filter nach Standort/Kostenstelle (passend ODER global=NULL).
    3. Sortierung nach priority desc — höchste gewinnt.
    """
    qs = SubsidyRule.objects.filter(is_active=True)
    qs = qs.filter(
        models_q_valid_at(on_date)
    )
    # Standort/Kostenstelle: NULL = "gilt für alle"
    qs = qs.filter(
        models_q_match_location(profile.location_id) | models_q_no_location()
    ).filter(
        models_q_match_cc(profile.cost_center_id) | models_q_no_cc()
    )
    rule = qs.order_by("-priority").first()
    if not rule:
        return Decimal("0.00")
    return rule.calculate(gross_price)


# --- Q-Helfer ausgelagert für Lesbarkeit ---
from django.db.models import Q  # noqa: E402


def models_q_valid_at(d: date) -> Q:
    return (Q(valid_from__lte=d) | Q(valid_from__isnull=True)) & (
        Q(valid_to__gte=d) | Q(valid_to__isnull=True)
    )


def models_q_match_location(loc_id):
    if loc_id is None:
        return Q(applies_to_location__isnull=True)
    return Q(applies_to_location_id=loc_id)


def models_q_no_location():
    return Q(applies_to_location__isnull=True)


def models_q_match_cc(cc_id):
    if cc_id is None:
        return Q(applies_to_cost_center__isnull=True)
    return Q(applies_to_cost_center_id=cc_id)


def models_q_no_cc():
    return Q(applies_to_cost_center__isnull=True)


# --- Bestellungen ---

class OrderError(Exception):
    pass


@transaction.atomic
def place_order(*, request, profile: UserProfile, slot: MealSlot, quantity: int = 1) -> Order:
    """Erstellt eine Bestellung mit allen Plausibilitätsprüfungen.

    Wirft OrderError mit deutschem Text bei Verstoß.
    """
    if not slot.is_active:
        raise OrderError("Diese Mahlzeit ist nicht verfügbar.")
    if not slot.order_window_open():
        raise OrderError("Die Bestellfrist ist abgelaufen.")
    if slot.available_qty is not None and slot.served_count + quantity > slot.available_qty:
        raise OrderError("Diese Mahlzeit ist ausverkauft.")
    if Order.objects.filter(user_profile=profile, meal_slot=slot, status=Order.STATUS_PLACED).exists():
        raise OrderError("Du hast diese Mahlzeit bereits bestellt.")

    gross = slot.effective_price
    subsidy = resolve_subsidy(profile, slot.mealplan.serving_date, gross)
    net = (gross * quantity) - (subsidy * quantity)
    if net < 0:
        net = Decimal("0.00")

    order = Order.objects.create(
        user_profile=profile,
        meal_slot=slot,
        quantity=quantity,
        unit_price_gross=gross,
        subsidy_amount=subsidy,
        net_to_employee=net,
    )
    log_event(request, "order.place", target=order, meta={
        "slot_id": slot.pk, "quantity": quantity,
        "gross": str(gross), "subsidy": str(subsidy), "net": str(net),
    })
    return order


@transaction.atomic
def cancel_order_by_user(*, request, order: Order) -> Order:
    if order.status != Order.STATUS_PLACED:
        raise OrderError("Diese Bestellung kann nicht mehr storniert werden.")
    if not order.meal_slot.cancel_window_open():
        raise OrderError("Die Storno-Frist ist abgelaufen.")
    order.status = Order.STATUS_CANCELLED
    order.cancelled_at = timezone.now()
    order.save(update_fields=["status", "cancelled_at"])
    log_event(request, "order.cancel.user", target=order)
    return order


@transaction.atomic
def cancel_order_by_admin(*, request, order: Order, note: str) -> Order:
    if order.status == Order.STATUS_CANCELLED:
        raise OrderError("Bereits storniert.")
    order.status = Order.STATUS_CANCELLED
    order.cancelled_at = timezone.now()
    order.cancel_note = note[:200]
    order.save(update_fields=["status", "cancelled_at", "cancel_note"])
    log_event(request, "order.cancel.admin", target=order, meta={"note": note})
    return order


@transaction.atomic
def mark_served(*, request, order: Order) -> Order:
    if order.status == Order.STATUS_CANCELLED:
        raise OrderError("Stornierte Bestellung kann nicht ausgegeben werden.")
    if order.status == Order.STATUS_SERVED:
        return order
    order.status = Order.STATUS_SERVED
    order.served_at = timezone.now()
    order.save(update_fields=["status", "served_at"])
    # served_count am Slot fortschreiben
    slot = order.meal_slot
    slot.served_count = slot.served_count + order.quantity
    slot.save(update_fields=["served_count"])
    log_event(request, "order.serve", target=order)
    return order
