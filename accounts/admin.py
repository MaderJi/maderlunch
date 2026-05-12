from django.contrib import admin

from .models import EntraGroupMapping, EntraIdentity, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "employee_id", "location", "cost_center", "is_active_employee", "must_change_password")
    list_filter = ("is_active_employee", "must_change_password", "location")
    search_fields = ("user__username", "user__first_name", "user__last_name", "employee_id")
    autocomplete_fields = ("user", "location", "cost_center")


@admin.register(EntraIdentity)
class EntraIdentityAdmin(admin.ModelAdmin):
    list_display = ("profile", "tenant_id", "object_id", "upn_at_link", "linked_at", "last_login_at")
    search_fields = ("profile__user__username", "upn_at_link", "object_id")
    readonly_fields = ("linked_at", "last_login_at")


@admin.register(EntraGroupMapping)
class EntraGroupMappingAdmin(admin.ModelAdmin):
    list_display = ("entra_group_object_id", "django_group", "is_active")
    list_filter = ("is_active",)
