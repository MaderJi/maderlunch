"""Views für Lunch.

Designentscheidungen:
- Dashboard zeigt Wochenansicht (Mo-Fr) der aktuellen oder gewählten Woche
  für die Kantine(n) am Standort des Users.
- Bestellen / Stornieren via HTMX-POST → liefert ein Fragment zurück, das den
  Slot inline ersetzt. Fallback: normaler Redirect, falls JS aus.
- Server-seitige Autorisierung an JEDER View. UI-Ausblendung ist Komfort.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Canteen, Location, MealPlan, MealSlot, Order
from .services import (
    OrderError, cancel_order_by_admin, cancel_order_by_user,
    mark_served, place_order,
)


# ─── Helpers ────────────────────────────────────────────────────

def _is_admin(user) -> bool:
    return user.is_authenticated and user.groups.filter(name="Admin").exists()


def _monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _week_dates(monday: date) -> list[date]:
    return [monday + timedelta(days=i) for i in range(5)]  # Mo-Fr


def _parse_iso_date(s: str | None, default: date) -> date:
    if not s:
        return default
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return default


def _user_canteens(user):
    """Kantinen am Standort des Users; falls kein Standort gesetzt: alle aktiven."""
    profile = getattr(user, "profile", None)
    qs = Canteen.objects.filter(is_active=True).select_related("location")
    if profile and profile.location_id:
        qs = qs.filter(location_id=profile.location_id)
    return qs.order_by("name")


# ─── Dashboard / Speiseplan ─────────────────────────────────────

@login_required
def dashboard(request):
    """Heutiger Plan für den Standort des Users (Kurzform)."""
    today = timezone.localdate()
    canteens = list(_user_canteens(request.user))
    plans = (
        MealPlan.objects.filter(
            canteen__in=canteens, serving_date=today, is_published=True,
        )
        .select_related("canteen", "canteen__location")
        .prefetch_related("slots__product__category", "slots__product__allergens")
    )
    profile = getattr(request.user, "profile", None)
    my_today_orders = Order.objects.filter(
        user_profile=profile,
        meal_slot__mealplan__serving_date=today,
        status=Order.STATUS_PLACED,
    ).select_related("meal_slot__product") if profile else []

    return render(request, "lunch/dashboard.html", {
        "today": today,
        "plans": plans,
        "my_today_orders": my_today_orders,
    })


@login_required
def mealplan_week(request):
    """Wochenansicht Mo-Fr. Filter: ?week=YYYY-MM-DD (irgendein Datum der Woche), ?canteen=<id>."""
    today = timezone.localdate()
    base = _parse_iso_date(request.GET.get("week"), today)
    monday = _monday_of(base)
    week_days = _week_dates(monday)

    canteens = list(_user_canteens(request.user))
    canteen_id = request.GET.get("canteen")
    selected_canteen = None
    if canteen_id:
        selected_canteen = next((c for c in canteens if str(c.id) == canteen_id), None)

    canteens_for_query = [selected_canteen] if selected_canteen else canteens

    plans = (
        MealPlan.objects.filter(
            canteen__in=canteens_for_query,
            serving_date__in=week_days,
            is_published=True,
        )
        .select_related("canteen")
        .prefetch_related("slots__product__category", "slots__product__allergens", "slots__product__additives")
    )

    # Index: {date: [slots...]} – flach pro Tag, sortiert nach Kantine+Produkt
    slots_by_day: dict = {d: [] for d in week_days}
    for p in plans:
        for s in p.slots.all():
            if s.is_active:
                slots_by_day[p.serving_date].append(s)
    for d in slots_by_day:
        slots_by_day[d].sort(key=lambda s: (s.mealplan.canteen.name, s.product.name))

    profile = getattr(request.user, "profile", None)
    my_orders_by_slot = {}
    if profile:
        my_orders_by_slot = {
            o.meal_slot_id: o
            for o in Order.objects.filter(
                user_profile=profile,
                meal_slot__mealplan__serving_date__in=week_days,
            )
        }

    return render(request, "lunch/mealplan.html", {
        "monday": monday,
        "prev_week": (monday - timedelta(days=7)).isoformat(),
        "next_week": (monday + timedelta(days=7)).isoformat(),
        "week_days": week_days,
        "canteens": canteens,
        "selected_canteen": selected_canteen,
        "slots_by_day": slots_by_day,
        "my_orders_by_slot": my_orders_by_slot,
    })


# ─── Bestellung anlegen / stornieren ────────────────────────────

@login_required
@require_POST
def order_place(request, slot_id: int):
    profile = getattr(request.user, "profile", None)
    if profile is None:
        return HttpResponseBadRequest("Kein Profil vorhanden.")
    slot = get_object_or_404(MealSlot, pk=slot_id, is_active=True)
    try:
        order = place_order(request=request, profile=profile, slot=slot, quantity=1)
    except OrderError as e:
        if request.htmx:
            return _slot_fragment(request, slot, error=str(e))
        messages.error(request, str(e))
        return redirect(request.META.get("HTTP_REFERER") or "lunch:mealplan_week")

    if request.htmx:
        return _slot_fragment(request, slot, order=order, success="Bestellung angelegt.")
    messages.success(request, "Bestellung angelegt.")
    return redirect(request.META.get("HTTP_REFERER") or "lunch:mealplan_week")


@login_required
@require_POST
def order_cancel(request, order_id: int):
    profile = getattr(request.user, "profile", None)
    order = get_object_or_404(Order, pk=order_id, user_profile=profile)
    try:
        cancel_order_by_user(request=request, order=order)
    except OrderError as e:
        if request.htmx:
            return _slot_fragment(request, order.meal_slot, error=str(e))
        messages.error(request, str(e))
        return redirect(request.META.get("HTTP_REFERER") or "lunch:my_orders")

    if request.htmx:
        return _slot_fragment(request, order.meal_slot, success="Bestellung storniert.")
    messages.success(request, "Bestellung storniert.")
    return redirect(request.META.get("HTTP_REFERER") or "lunch:my_orders")


def _slot_fragment(request, slot: MealSlot, *, order: Order | None = None,
                   success: str = "", error: str = "") -> HttpResponse:
    profile = getattr(request.user, "profile", None)
    my_order = order or Order.objects.filter(
        user_profile=profile, meal_slot=slot,
    ).order_by("-placed_at").first()
    return render(request, "lunch/_slot.html", {
        "slot": slot,
        "my_order": my_order,
        "success": success,
        "error": error,
    })


# ─── Meine Bestellungen ─────────────────────────────────────────

@login_required
def my_orders(request):
    profile = getattr(request.user, "profile", None)
    if profile is None:
        orders = []
    else:
        orders = (
            Order.objects.filter(user_profile=profile)
            .select_related("meal_slot__product", "meal_slot__mealplan__canteen__location")
            .order_by("-meal_slot__mealplan__serving_date", "-placed_at")[:200]
        )
    return render(request, "lunch/my_orders.html", {"orders": orders})


# ─── Admin: Pickup-Ansicht ──────────────────────────────────────

@login_required
@user_passes_test(_is_admin, login_url="accounts:login")
def pickup(request):
    """Ausgabeansicht für die Kantine: heute + Filter Kantine."""
    today = timezone.localdate()
    d = _parse_iso_date(request.GET.get("date"), today)
    canteen_id = request.GET.get("canteen")

    canteens = Canteen.objects.filter(is_active=True).select_related("location").order_by("name")
    selected_canteen = canteens.filter(pk=canteen_id).first() if canteen_id else canteens.first()

    orders = []
    if selected_canteen:
        orders = (
            Order.objects.filter(
                meal_slot__mealplan__canteen=selected_canteen,
                meal_slot__mealplan__serving_date=d,
            )
            .exclude(status=Order.STATUS_CANCELLED)
            .select_related(
                "user_profile__user",
                "meal_slot__product",
            )
            .order_by("user_profile__user__last_name", "user_profile__user__first_name")
        )

    return render(request, "lunch/pickup.html", {
        "date": d,
        "canteens": canteens,
        "selected_canteen": selected_canteen,
        "orders": orders,
    })


@login_required
@user_passes_test(_is_admin, login_url="accounts:login")
@require_POST
def pickup_serve(request, order_id: int):
    order = get_object_or_404(Order, pk=order_id)
    try:
        mark_served(request=request, order=order)
    except OrderError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
    if request.htmx:
        return render(request, "lunch/_pickup_row.html", {"order": order})
    return redirect(request.META.get("HTTP_REFERER") or "lunch:pickup")


@login_required
@user_passes_test(_is_admin, login_url="accounts:login")
@require_POST
def admin_cancel_order(request, order_id: int):
    order = get_object_or_404(Order, pk=order_id)
    note = request.POST.get("note", "").strip()
    if not note:
        return HttpResponseBadRequest("Stornogrund (note) erforderlich.")
    try:
        cancel_order_by_admin(request=request, order=order, note=note)
    except OrderError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, f"Bestellung #{order.pk} storniert.")
    return redirect(request.META.get("HTTP_REFERER") or "lunch:pickup")
