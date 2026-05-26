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
    # Manager: Speiseplan-Verwaltung
    path("manage/plan/", views.manage_plan, name="manage_plan"),
    path("manage/plan/toggle-publish/", views.toggle_publish_day, name="toggle_publish_day"),
    path("manage/plan/slot/<int:slot_id>/delete/", views.delete_slot, name="delete_slot"),
    path("manage/plan/slot/<int:slot_id>/toggle-active/", views.toggle_slot_active, name="toggle_slot_active"),
    # Manager: Gerichte-Verwaltung
    path("manage/products/", views.product_list, name="product_list"),
    path("manage/products/create/", views.product_create, name="product_create"),
    path("manage/products/<int:product_id>/edit/", views.product_edit, name="product_edit"),
    path("manage/products/<int:product_id>/toggle-active/", views.product_toggle_active, name="product_toggle_active"),
]
