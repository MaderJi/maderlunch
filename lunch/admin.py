from django.contrib import admin

from .models import (
    Additive, Allergen, Canteen, Category, GuestOrder,
    Location, MealPlan, MealSlot, Order, Product,
)


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code")


@admin.register(Canteen)
class CanteenAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "location", "cutoff_order_time", "serving_time", "is_active")
    list_filter = ("is_active", "location")
    search_fields = ("name", "code")
    autocomplete_fields = ("location",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "display_order")
    ordering = ("display_order", "name")


@admin.register(Allergen)
class AllergenAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


@admin.register(Additive)
class AdditiveAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price_gross", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("name",)
    filter_horizontal = ("allergens", "additives")


class MealSlotInline(admin.TabularInline):
    model = MealSlot
    extra = 1
    autocomplete_fields = ("product",)


@admin.register(MealPlan)
class MealPlanAdmin(admin.ModelAdmin):
    list_display = ("serving_date", "canteen", "is_published")
    list_filter = ("is_published", "canteen")
    date_hierarchy = "serving_date"
    autocomplete_fields = ("canteen",)
    inlines = [MealSlotInline]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("pk", "user_profile", "meal_slot", "status", "unit_price_gross",
                    "subsidy_amount", "net_to_employee", "placed_at")
    list_filter = ("status", "meal_slot__mealplan__canteen")
    search_fields = ("user_profile__user__username", "user_profile__user__last_name")
    readonly_fields = ("placed_at", "cancelled_at", "served_at",
                       "unit_price_gross", "subsidy_amount", "net_to_employee")
    date_hierarchy = "placed_at"


@admin.register(GuestOrder)
class GuestOrderAdmin(admin.ModelAdmin):
    list_display = ("pk", "guest_name", "guest_company", "host_profile", "meal_slot",
                    "status", "total_gross", "placed_at")
    list_filter = ("status",)
    search_fields = ("guest_name", "guest_company", "host_profile__user__username")
    date_hierarchy = "placed_at"
