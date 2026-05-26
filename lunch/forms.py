"""Forms für das Lunch-Modul.

Drei Formulare:
  - MealSlotAddForm: Gericht in Speiseplan eintragen
  - ProductQuickAddForm: Neues Gericht schnell anlegen (Name/Beschreibung/Preis)
  - ProductEditForm: Bestehendes Gericht bearbeiten
"""
from __future__ import annotations

from decimal import Decimal

from django import forms

from .models import Category, Product


# Standard-Preis für neu angelegte Gerichte (Mader-Preis 2026)
DEFAULT_PRODUCT_PRICE = Decimal("4.57")

# Standard-Kategorie, der ein neues Gericht zugewiesen wird, wenn der Manager
# über den Quick-Add anlegt. Wird bei Bedarf automatisch erzeugt.
DEFAULT_CATEGORY_NAME = "Hauptgericht"


def _get_or_create_default_category() -> Category:
    """Holt die Standard-Kategorie 'Hauptgericht', legt sie bei Bedarf an."""
    cat, _ = Category.objects.get_or_create(
        name=DEFAULT_CATEGORY_NAME,
        defaults={"display_order": 10},
    )
    return cat


class MealSlotAddForm(forms.Form):
    """Formular zum Hinzufügen eines Gerichts in einen MealPlan."""

    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_active=True)
            .select_related("category")
            .order_by("name"),
        label="Gericht",
        empty_label="-- Gericht wählen --",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    price_override = forms.DecimalField(
        max_digits=7,
        decimal_places=2,
        required=False,
        min_value=0,
        label="Preis (optional)",
        help_text="Leer = Standardpreis des Gerichts",
        widget=forms.NumberInput(attrs={
            "class": "form-control form-control-sm",
            "step": "0.01",
            "placeholder": "z.B. 4,57",
        }),
    )
    available_qty = forms.IntegerField(
        required=False,
        min_value=1,
        label="Kontingent (optional)",
        help_text="Leer = unbegrenzt",
        widget=forms.NumberInput(attrs={
            "class": "form-control form-control-sm",
            "placeholder": "z.B. 30",
        }),
    )


class ProductQuickAddForm(forms.Form):
    """Schnell-Anlegen eines neuen Gerichts.

    Kategorie wird automatisch auf 'Hauptgericht' gesetzt. Allergene/Nährwerte
    sind nicht Teil dieses Forms und müssen ggf. später per Django-Admin ergänzt
    werden.
    """

    name = forms.CharField(
        max_length=120,
        label="Gericht",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "z.B. Salat alla Szilvi",
            "autofocus": "autofocus",
        }),
    )
    description = forms.CharField(
        required=False,
        label="Beschreibung",
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Zutaten und Beschreibung",
        }),
    )
    price_gross = forms.DecimalField(
        max_digits=7,
        decimal_places=2,
        min_value=0,
        initial=DEFAULT_PRODUCT_PRICE,
        label="Preis (€)",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "step": "0.01",
        }),
    )

    def save(self) -> Product:
        cat = _get_or_create_default_category()
        return Product.objects.create(
            name=self.cleaned_data["name"].strip(),
            description=self.cleaned_data.get("description", "").strip(),
            category=cat,
            price_gross=self.cleaned_data["price_gross"],
            is_active=True,
        )


class ProductEditForm(forms.ModelForm):
    """Bearbeiten eines bestehenden Gerichts (begrenzt auf die drei Hauptfelder)."""

    class Meta:
        model = Product
        fields = ["name", "description", "price_gross"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "price_gross": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01",
                "min": "0",
            }),
        }
        labels = {
            "name": "Gericht",
            "description": "Beschreibung",
            "price_gross": "Preis (€)",
        }
