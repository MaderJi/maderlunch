from decimal import Decimal

from django.db import models


class CostCenter(models.Model):
    code = models.CharField("Kostenstelle (Code)", max_length=20, unique=True)
    name = models.CharField("Bezeichnung", max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Kostenstelle"
        verbose_name_plural = "Kostenstellen"
        ordering = ("code",)

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class SubsidyRule(models.Model):
    """Zuschuss-Regel. Resolver wählt anwendbare Regel mit höchster Priorität."""

    MODE_FIXED = "fixed"
    MODE_PERCENT = "percent"
    MODE_CHOICES = [
        (MODE_FIXED, "Fester Betrag (€)"),
        (MODE_PERCENT, "Prozent vom Bruttopreis"),
    ]

    name = models.CharField(max_length=100)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES)
    value = models.DecimalField(
        max_digits=8, decimal_places=2,
        help_text="Bei 'fixed' = Euro-Betrag pro Mahlzeit. Bei 'percent' = 0..100.",
    )

    applies_to_location = models.ForeignKey(
        "lunch.Location", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="subsidy_rules",
    )
    applies_to_cost_center = models.ForeignKey(
        CostCenter, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="subsidy_rules",
    )

    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)

    priority = models.PositiveIntegerField(default=0, help_text="Höhere Zahl gewinnt.")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Zuschussregel"
        verbose_name_plural = "Zuschussregeln"
        ordering = ("-priority", "name")

    def __str__(self) -> str:
        return f"{self.name} ({self.get_mode_display()} {self.value})"

    def calculate(self, gross_price: Decimal) -> Decimal:
        if self.mode == self.MODE_FIXED:
            return min(Decimal(self.value), Decimal(gross_price))
        # percent
        return (Decimal(gross_price) * Decimal(self.value) / Decimal(100)).quantize(Decimal("0.01"))
