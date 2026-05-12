from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("export/", views.export_form, name="export_form"),
    path("export/orders.csv", views.export_orders, name="export_orders"),
]
