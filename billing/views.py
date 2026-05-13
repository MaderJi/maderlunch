from datetime import date, datetime, timedelta

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse
from django.shortcuts import render

from audit.services import log_event
from lunch.models import Order

from .exporters import export_orders_csv


def _is_admin(user):
    return user.is_authenticated and user.groups.filter(name="Admin").exists()


@login_required
@user_passes_test(_is_admin, login_url="account_login")
def export_form(request):
    today = date.today()
    default_from = (today - timedelta(days=30)).isoformat()
    default_to = today.isoformat()
    return render(request, "billing/export.html", {
        "default_from": default_from,
        "default_to": default_to,
    })


@login_required
@user_passes_test(_is_admin, login_url="account_login")
def export_orders(request):
    try:
        d_from = datetime.fromisoformat(request.GET["from"]).date()
        d_to = datetime.fromisoformat(request.GET["to"]).date()
    except (KeyError, ValueError):
        return HttpResponse("Ungültige Datumsangabe.", status=400)

    qs = Order.objects.filter(
        meal_slot__mealplan__serving_date__gte=d_from,
        meal_slot__mealplan__serving_date__lte=d_to,
    )
    csv_bytes = export_orders_csv(qs, period_from=d_from, period_to=d_to)

    log_event(request, "export.csv", meta={
        "type": "orders",
        "from": d_from.isoformat(),
        "to": d_to.isoformat(),
        "rows": qs.count(),
    })

    fname = f"maderlunch_orders_{d_from.isoformat()}_{d_to.isoformat()}.csv"
    resp = HttpResponse(csv_bytes, content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{fname}"'
    return resp
