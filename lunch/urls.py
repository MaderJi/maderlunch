from django.urls import path

from . import views

app_name = "lunch"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("plan/", views.mealplan_week, name="mealplan_week"),
    path("order/place/<int:slot_id>/", views.order_place, name="order_place"),
    path("order/<int:order_id>/cancel/", views.order_cancel, name="order_cancel"),
    path("my/", views.my_orders, name="my_orders"),

    # Admin
    path("pickup/", views.pickup, name="pickup"),
    path("pickup/<int:order_id>/serve/", views.pickup_serve, name="pickup_serve"),
    path("admin-cancel/<int:order_id>/", views.admin_cancel_order, name="admin_cancel_order"),
]
