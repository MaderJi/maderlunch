from django.contrib import admin

from .models import CostCenter, SubsidyRule


@admin.register(CostCenter)
class CostCenterAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(SubsidyRule)
class SubsidyRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "mode", "value", "applies_to_location", "applies_to_cost_center", "priority", "is_active")
    list_filter = ("mode", "is_active")
    search_fields = ("name",)
