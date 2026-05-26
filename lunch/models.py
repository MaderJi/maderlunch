from datetime import datetime, time
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from .deadlines import get_order_deadline, is_order_window_open


class Location(models.Model):
    name = models.CharField("Standort", max_length=100)
    code = models.CharField("Kürzel", max_length=20, unique=True)
    address = models.CharField("Adresse", max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Standort"
        verbose_name_plural = "Standorte"
        ordering = ("name",)

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class Canteen(models.Model):
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="canteens")
    name = models.CharField("Kantine", max_length=100)
    code = models.CharField("Kürzel", max_length=20)
    serving_time = models.TimeField("Ausgabezeit", default=time(11, 30))
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Kantine"
        verbose_name_plural = "Kantinen"
        constraints = [
            models.UniqueConstraint(fields=["location", "code"], name="uniq_canteen_per_location"),
        ]
        ordering = ("location__name", "name")

    def __str__(self) -> str:
        return f"{self.location.code}/{self.code} — {self.name}"


class Category(models.Model):
    name = models.CharField("Kategorie", max_length=50)
    display_order = models.PositiveSmallIntegerField(default=100)

    class Meta:
        verbose_name = "Kategorie"
        verbose_name_plural = "Kategorien"
        ordering = ("display_order", "name")

    def __str__(self) -> str:
        return self.name


class Allergen(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=50)

    class Meta:
        verbose_name = "Allergen"
        verbose_name_plural = "Allergene"
        ordering = ("code",)

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class Additive(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=50)

    class Meta:
        verbose_name = "Zusatzstoff"
        verbose_name_plural = "Zusatzstoffe"
        ordering = ("code",)

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class Product(models.Model):
    name = models.CharField("Bezeichnung", max_length=120)
    description = models.TextField(blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    price_gross = models.DecimalField(
        "Bruttopreis", max_digits=7, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    allergens = models.ManyToManyField(Allergen, blank=True)
    additives = models.ManyToManyField(Additive, blank=True)
    kcal = models.PositiveIntegerField(null=True, blank=True)
    protein_g = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    fat_g = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    carbs_g = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Gericht"
        verbose_name_plural = "Gerichte"
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class MealPlan(models.Model):
    canteen = models.ForeignKey(Canteen, on_delete=models.CASCADE, related_name="mealplans")
    serving_date = models.DateField("Ausgabedatum")
    is_published = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Speiseplan"
        verbose_name_plural = "Speisepläne"
        constraints = [
            models.UniqueConstraint(fields=["canteen", "serving_date"], name="uniq_plan_per_canteen_date"),
        ]
        ordering = ("-serving_date", "canteen__name")

    def __str__(self) -> str:
        return f"{self.canteen} — {self.serving_date.isoformat()}"


class MealSlot(models.Model):
    mealplan = models.ForeignKey(MealPlan, on_delete=models.CASCADE, related_name="slots")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="slots")
    price_override = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True,
        help_text="Falls leer, wird Product.price_gross verwendet.",
    )
    available_qty = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Leer = unbegrenzt verfügbar.",
    )
    served_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Speiseplan-Position"
        verbose_name_plural = "Speiseplan-Positionen"

    def __str__(self) -> str:
        return f"{self.product.name} @ {self.mealplan}"

    @property
    def effective_price(self) -> Decimal:
        return self.price_override if self.price_override is not None else self.product.price_gross

    @property
    def serving_datetime(self) -> datetime:
        d = self.mealplan.serving_date
        t = self.mealplan.canteen.serving_time
        naive = datetime.combine(d, t)
        return timezone.make_aware(naive, timezone.get_current_timezone())

    @property
    def order_deadline(self) -> datetime:
        """Letztmöglicher Bestell-/Storno-Zeitpunkt (Wochenblock-Logik)."""
        return get_order_deadline(self.mealplan.serving_date)

    def order_window_open(self, now=None) -> bool:
        return is_order_window_open(self.mealplan.serving_date, now=now)

    # Storno- und Bestellfrist sind identisch (Produktentscheidung MVP).
    cancel_window_open = order_window_open


class Order(models.Model):
    STATUS_PLACED = "placed"
    STATUS_CANCELLED = "cancelled"
    STATUS_SERVED = "served"
    STATUS_CHOICES = [
        (STATUS_PLACED, "Bestellt"),
        (STATUS_CANCELLED, "Storniert"),
        (STATUS_SERVED, "Ausgegeben"),
    ]

    user_profile = models.ForeignKey(
        "accounts.UserProfile", on_delete=models.PROTECT, related_name="orders"
    )
    meal_slot = models.ForeignKey(MealSlot, on_delete=models.PROTECT, related_name="orders")
    quantity = models.PositiveSmallIntegerField(default=1)
    unit_price_gross = models.DecimalField(max_digits=7, decimal_places=2)
    subsidy_amount = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0.00"))
    net_to_employee = models.DecimalField(max_digits=7, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PLACED)
    placed_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    served_at = models.DateTimeField(null=True, blank=True)
    cancel_note = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "Bestellung"
        verbose_name_plural = "Bestellungen"
        constraints = [
            models.UniqueConstraint(
                fields=["user_profile", "meal_slot"],
                name="uniq_order_per_user_slot",
            ),
        ]
        ordering = ("-placed_at",)

    def __str__(self) -> str:
        return f"#{self.pk} {self.user_profile} → {self.meal_slot.product.name}"


class GuestOrder(models.Model):
    """Bewirtung — Bestellung im Namen eines Gastes durch einen Mitarbeiter (Host)."""
    host_profile = models.ForeignKey(
        "accounts.UserProfile", on_delete=models.PROTECT, related_name="guest_orders"
    )
    meal_slot = models.ForeignKey(MealSlot, on_delete=models.PROTECT, related_name="guest_orders")
    guest_name = models.CharField(max_length=120)
    guest_company = models.CharField(max_length=120, blank=True)
    purpose = models.CharField(max_length=200, blank=True)
    cost_center = models.ForeignKey(
        "billing.CostCenter", on_delete=models.PROTECT, related_name="guest_orders",
    )
    quantity = models.PositiveSmallIntegerField(default=1)
    unit_price_gross = models.DecimalField(max_digits=7, decimal_places=2)
    subsidy_amount = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0.00"))
    total_gross = models.DecimalField(max_digits=8, decimal_places=2)
    status = models.CharField(max_length=20, choices=Order.STATUS_CHOICES, default=Order.STATUS_PLACED)
    placed_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    served_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Bewirtung"
        verbose_name_plural = "Bewirtungen"
        ordering = ("-placed_at",)

    def __str__(self) -> str:
        return f"Gast {self.guest_name} → {self.meal_slot.product.name}"
