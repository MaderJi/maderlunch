from django.contrib import admin

from .models import EntraIdentity, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "employee_id",
        "role",
        "auth_source",
        "location",
        "cost_center",
        "is_active_employee",
        "must_change_password",
    )
    list_filter = ("role", "auth_source", "is_active_employee", "must_change_password", "location")
    search_fields = ("user__username", "user__first_name", "user__last_name", "employee_id", "user__email")
    autocomplete_fields = ("user", "location", "cost_center")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (None, {
            "fields": ("user", "employee_id", "is_active_employee"),
        }),
        ("Rolle & Auth", {
            "fields": ("role", "auth_source", "must_change_password"),
            "description": (
                "Bei Entra-Logins wird die Rolle bei jedem Login aus dem 'roles'-Claim "
                "überschrieben. Manuelle Änderungen sind dort sinnlos."
            ),
        }),
        ("Zuordnung", {
            "fields": ("location", "cost_center"),
        }),
        ("Metadaten", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


@admin.register(EntraIdentity)
class EntraIdentityAdmin(admin.ModelAdmin):
    list_display = ("profile", "tenant_id", "object_id", "upn_at_link", "linked_at", "last_login_at")
    search_fields = ("profile__user__username", "upn_at_link", "object_id")
    readonly_fields = ("linked_at", "last_login_at", "last_roles_claim")
