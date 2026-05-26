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
from django.db import IntegrityError
from django.contrib.auth.decorators import login_required
from accounts.permissions import manager_required
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.urls import reverse

from .models import Canteen, Location, MealPlan, MealSlot, Product, Order, GuestOrder
from .services import (
    OrderError, cancel_order_by_admin, cancel_order_by_user,
    mark_served, place_order,
)
from .forms import MealSlotAddForm, ProductQuickAddForm, ProductEditForm

# ─── Helpers ────────────────────────────────────────────────────


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
    my_orders_by_slot: dict = {}
    my_order_summary: dict = {}  # {date: "Gerichtname"} für Tagesleiste oben
    if profile:
        my_orders_qs = (
            Order.objects.filter(
                user_profile=profile,
                meal_slot__mealplan__serving_date__in=week_days,
            )
            .select_related("meal_slot__product", "meal_slot__mealplan")
        )
        for o in my_orders_qs:
            my_orders_by_slot[o.meal_slot_id] = o
            if o.status == Order.STATUS_PLACED:
                my_order_summary[o.meal_slot.mealplan.serving_date] = o.meal_slot.product.name

    return render(request, "lunch/mealplan.html", {
        "monday": monday,
        "prev_week": (monday - timedelta(days=7)).isoformat(),
        "next_week": (monday + timedelta(days=7)).isoformat(),
        "week_days": week_days,
        "canteens": canteens,
        "selected_canteen": selected_canteen,
        "slots_by_day": slots_by_day,
        "my_orders_by_slot": my_orders_by_slot,
        "my_order_summary": my_order_summary,
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

@manager_required
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


@manager_required
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


@manager_required
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

# ─── Manager: Speiseplan- und Gerichte-Verwaltung ───────────────────
#
# Dieser Block wird ans Ende von lunch/views.py angehängt.
#
# Imports, die oben in views.py vorhanden sein müssen:
#
#   from datetime import date, timedelta
#   from django.contrib import messages
#   from django.shortcuts import render, redirect, get_object_or_404
#   from django.views.decorators.http import require_POST
#   from django.db import IntegrityError
#   from django.utils import timezone
#   from accounts.permissions import manager_required
#   from .models import MealPlan, MealSlot, Canteen, Product, Order, GuestOrder
#   from .forms import MealSlotAddForm, ProductQuickAddForm, ProductEditForm


# ── Speiseplan-Verwaltung ──────────────────────────────────────────

@manager_required
def manage_plan(request):
    """Wochenansicht für Manager: Mo-Fr × alle aktiven Kantinen.

    POST-Aktionen:
      - action=add_slot: Slot zum Speiseplan hinzufügen
      - action=quick_add_product: neues Gericht anlegen UND als Slot hinzufügen
    """
    today = timezone.localdate()
    base_week = _monday_of(today)

    week_param = request.GET.get("week")
    if week_param:
        try:
            requested = date.fromisoformat(week_param)
            base_week = _monday_of(requested)
        except ValueError:
            pass

    week_dates = _week_dates(base_week)
    prev_week = (base_week - timedelta(days=7)).isoformat()
    next_week = (base_week + timedelta(days=7)).isoformat()
    week_num = base_week.isocalendar().week

    # ── POST-Handling ─────────────────────────────────────────────
    if request.method == "POST":
        action = request.POST.get("action")
        canteen_id = request.POST.get("canteen_id")
        date_str = request.POST.get("serving_date")

        # 1) Quick-Add: neues Gericht anlegen und sofort in Plan eintragen
        if action == "quick_add_product":
            qa_form = ProductQuickAddForm(request.POST)
            if qa_form.is_valid() and canteen_id and date_str:
                try:
                    serving_date = date.fromisoformat(date_str)
                    canteen = Canteen.objects.get(pk=canteen_id)
                    product = qa_form.save()
                    mealplan, _ = MealPlan.objects.get_or_create(
                        canteen=canteen,
                        serving_date=serving_date,
                    )
                    MealSlot.objects.create(
                        mealplan=mealplan,
                        product=product,
                        is_active=True,
                    )
                    messages.success(
                        request,
                        f'Neues Gericht „{product.name}" angelegt und in den Plan eingetragen.',
                    )
                except (Canteen.DoesNotExist, ValueError) as exc:
                    messages.error(request, f"Konnte Gericht nicht anlegen: {exc}")
                except IntegrityError:
                    messages.warning(request, "Dieses Gericht ist bereits im Plan für diesen Tag.")
            else:
                error_summary = "; ".join(
                    f"{field}: {', '.join(errs)}"
                    for field, errs in qa_form.errors.items()
                )
                messages.error(request, f"Bitte Eingaben prüfen. {error_summary}")
            return redirect(f"{request.path}?week={base_week.isoformat()}")

        # 2) Bestehendes Gericht als Slot in den Plan eintragen
        if action == "add_slot":
            form = MealSlotAddForm(request.POST)
            if form.is_valid() and canteen_id and date_str:
                try:
                    serving_date = date.fromisoformat(date_str)
                    canteen = Canteen.objects.get(pk=canteen_id)
                    mealplan, _ = MealPlan.objects.get_or_create(
                        canteen=canteen,
                        serving_date=serving_date,
                    )
                    MealSlot.objects.create(
                        mealplan=mealplan,
                        product=form.cleaned_data["product"],
                        price_override=form.cleaned_data.get("price_override"),
                        available_qty=form.cleaned_data.get("available_qty"),
                        is_active=True,
                    )
                    messages.success(
                        request,
                        f'„{form.cleaned_data["product"].name}" hinzugefügt.',
                    )
                except (Canteen.DoesNotExist, ValueError) as exc:
                    messages.error(request, f"Konnte Gericht nicht hinzufügen: {exc}")
                except IntegrityError:
                    messages.warning(request, "Dieses Gericht ist bereits im Plan für diesen Tag.")
            else:
                messages.error(request, "Bitte Eingaben prüfen.")
            return redirect(f"{request.path}?week={base_week.isoformat()}")

    # ── GET: Daten für Wochenansicht aufbauen ─────────────────────
    canteens = list(Canteen.objects.filter(is_active=True).select_related("location"))
    plans_qs = (
        MealPlan.objects
        .filter(canteen__in=canteens, serving_date__in=week_dates)
        .select_related("canteen", "canteen__location")
        .prefetch_related("slots__product__category")
    )
    plan_map: dict[tuple[int, date], MealPlan] = {
        (p.canteen_id, p.serving_date): p for p in plans_qs
    }

    days = []
    for d in week_dates:
        day_entries = []
        for c in canteens:
            plan = plan_map.get((c.id, d))
            slots = list(plan.slots.all().order_by("product__name")) if plan else []
            day_entries.append({
                "canteen": c,
                "plan": plan,
                "slots": slots,
                "slot_form": MealSlotAddForm(),
                "quick_form": ProductQuickAddForm(),
            })
        days.append({
            "date": d,
            "entries": day_entries,
        })

    ctx = {
        "days": days,
        "week_num": week_num,
        "week_start": base_week,
        "week_end": base_week + timedelta(days=4),
        "prev_week": prev_week,
        "next_week": next_week,
        "today": today,
    }
    return render(request, "lunch/manage_plan.html", ctx)


@manager_required
@require_POST
def toggle_publish_day(request):
    """Tag pro Kantine veröffentlichen oder zurückziehen."""
    date_str = request.POST.get("serving_date")
    action = request.POST.get("publish_action", "publish")
    if not date_str:
        messages.error(request, "Kein Datum angegeben.")
        return redirect("lunch:manage_plan")
    try:
        serving_date = date.fromisoformat(date_str)
    except ValueError:
        messages.error(request, "Ungültiges Datum.")
        return redirect("lunch:manage_plan")

    canteen_id = request.POST.get("canteen_id")
    qs = MealPlan.objects.filter(serving_date=serving_date)
    if canteen_id:
        qs = qs.filter(canteen_id=canteen_id)

    new_state = (action == "publish")
    plans = [p for p in qs if p.slots.exists()] if new_state else list(qs)
    updated = 0
    for p in plans:
        if p.is_published != new_state:
            p.is_published = new_state
            p.save(update_fields=["is_published"])
            updated += 1

    verb = "veröffentlicht" if new_state else "zurückgezogen"
    if updated:
        messages.success(request, f"{updated} Speiseplan/-pläne {verb}.")
    else:
        messages.info(request, "Keine Änderung nötig.")

    week = request.POST.get("week") or _monday_of(serving_date).isoformat()
    return redirect(f"{reverse('lunch:manage_plan')}?week={week}")


@manager_required
@require_POST
def delete_slot(request, slot_id: int):
    """Slot hart löschen, falls keine Bestellungen — sonst soft-delete."""
    slot = get_object_or_404(MealSlot, pk=slot_id)
    has_orders = (
        Order.objects.filter(meal_slot=slot).exists()
        or GuestOrder.objects.filter(meal_slot=slot).exists()
    )
    product_name = slot.product.name

    if has_orders:
        if slot.is_active:
            slot.is_active = False
            slot.save(update_fields=["is_active"])
            messages.warning(
                request,
                f'„{product_name}" hat bereits Bestellungen und wurde nur '
                f'deaktiviert. Bestellungen bleiben erhalten.',
            )
        else:
            messages.info(request, f'„{product_name}" ist bereits inaktiv.')
    else:
        slot.delete()
        messages.success(request, f'„{product_name}" wurde entfernt.')

    week = request.POST.get("week") or _monday_of(timezone.localdate()).isoformat()
    return redirect(f"{reverse('lunch:manage_plan')}?week={week}")


@manager_required
@require_POST
def toggle_slot_active(request, slot_id: int):
    """Slot aktiv/inaktiv togglen."""
    slot = get_object_or_404(MealSlot, pk=slot_id)
    slot.is_active = not slot.is_active
    slot.save(update_fields=["is_active"])
    state = "aktiv" if slot.is_active else "inaktiv"
    messages.success(request, f'„{slot.product.name}" ist jetzt {state}.')

    week = request.POST.get("week") or _monday_of(timezone.localdate()).isoformat()
    return redirect(f"{reverse('lunch:manage_plan')}?week={week}")


# ── Gerichte-Verwaltung ────────────────────────────────────────────

@manager_required
def product_list(request):
    """Liste aller Gerichte mit Anlegen/Bearbeiten/Toggle."""
    products = Product.objects.select_related("category").order_by("name")

    ctx = {
        "products": products,
        "create_form": ProductQuickAddForm(),
    }
    return render(request, "lunch/product_list.html", ctx)


@manager_required
@require_POST
def product_create(request):
    """Neues Gericht über die Listen-Seite anlegen."""
    form = ProductQuickAddForm(request.POST)
    if form.is_valid():
        product = form.save()
        messages.success(request, f'Gericht „{product.name}" angelegt.')
    else:
        error_summary = "; ".join(
            f"{field}: {', '.join(errs)}"
            for field, errs in form.errors.items()
        )
        messages.error(request, f"Konnte Gericht nicht anlegen. {error_summary}")
    return redirect("lunch:product_list")


@manager_required
def product_edit(request, product_id: int):
    """Gericht bearbeiten (Name, Beschreibung, Preis)."""
    product = get_object_or_404(Product, pk=product_id)
    if request.method == "POST":
        form = ProductEditForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, f'„{product.name}" gespeichert.')
            return redirect("lunch:product_list")
        else:
            messages.error(request, "Bitte Eingaben prüfen.")
    else:
        form = ProductEditForm(instance=product)
    return render(request, "lunch/product_edit.html", {"form": form, "product": product})


@manager_required
@require_POST
def product_toggle_active(request, product_id: int):
    """Gericht aktivieren/deaktivieren.

    Achtung: Inaktive Gerichte können nicht mehr neu in Speisepläne eingetragen
    werden, bestehende Slots mit diesem Produkt bleiben unverändert.
    """
    product = get_object_or_404(Product, pk=product_id)
    product.is_active = not product.is_active
    product.save(update_fields=["is_active"])
    state = "aktiv" if product.is_active else "deaktiviert"
    messages.success(request, f'„{product.name}" ist jetzt {state}.')
    return redirect("lunch:product_list")
