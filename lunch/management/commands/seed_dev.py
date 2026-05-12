"""Dev-Seed: Standorte, Kategorien, Allergene, Beispielmenü, Demo-Admin und Demo-User.

NIE in Produktion ausführen. Idempotent: kann mehrfach laufen, ohne Duplikate zu erzeugen.

Aufruf:
    python manage.py seed_dev
"""
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import UserProfile
from billing.models import CostCenter, SubsidyRule
from lunch.models import (
    Additive, Allergen, Canteen, Category, Location, MealPlan, MealSlot, Product,
)


MADER_LOCATIONS = [
    ("LE", "Leinfelden-Echterdingen", "Zentrale Mader"),
    ("DZ", "Ditzingen", "Service-Standort Ditzingen"),
    ("HD", "Heidenheim", "Service-Standort Heidenheim"),
    ("EI", "Eichenau", "Service-Standort Eichenau"),
]

CATEGORIES = [
    ("Vorspeise", 10),
    ("Hauptgericht", 20),
    ("Vegetarisch", 25),
    ("Vegan", 27),
    ("Beilage", 30),
    ("Dessert", 40),
    ("Getränk", 50),
]

ALLERGENS = [
    ("A", "Glutenhaltiges Getreide"),
    ("B", "Krebstiere"),
    ("C", "Eier"),
    ("D", "Fisch"),
    ("G", "Milch/Laktose"),
    ("H", "Schalenfrüchte"),
]

ADDITIVES = [
    ("1", "Farbstoff"),
    ("2", "Konservierungsstoff"),
    ("3", "Antioxidationsmittel"),
]

PRODUCTS = [
    # (name, category, price_gross, allergens, kcal)
    ("Spaghetti Bolognese", "Hauptgericht", "5.20", ["A", "G"], 720),
    ("Gemüsecurry mit Reis", "Vegan", "4.80", [], 580),
    ("Wiener Schnitzel mit Pommes", "Hauptgericht", "6.50", ["A", "C"], 880),
    ("Maultaschen in der Brühe", "Vegetarisch", "4.90", ["A", "C", "G"], 510),
    ("Salatteller mit Hähnchen", "Hauptgericht", "5.50", ["G"], 420),
    ("Tagessuppe", "Vorspeise", "1.90", [], 180),
    ("Apfelstrudel mit Vanillesauce", "Dessert", "2.20", ["A", "C", "G"], 320),
    ("Wasser still 0,5l", "Getränk", "1.20", [], 0),
]


class Command(BaseCommand):
    help = "Seed-Daten für Dev-Umgebung."

    @transaction.atomic
    def handle(self, *args, **opts):
        User = get_user_model()
        self.stdout.write("Standorte...")
        locations = {}
        for code, name, addr in MADER_LOCATIONS:
            loc, _ = Location.objects.get_or_create(code=code, defaults={"name": name, "address": addr})
            locations[code] = loc

        self.stdout.write("Kantinen (eine pro Standort)...")
        canteens = {}
        for code, loc in locations.items():
            canteen, _ = Canteen.objects.get_or_create(
                location=loc, code="K1",
                defaults={
                    "name": f"Kantine {loc.name}",
                    "cutoff_order_time": time(9, 0),
                    "serving_time": time(11, 30),
                    "cancel_cutoff_minutes_before_serving": 60,
                },
            )
            canteens[code] = canteen

        self.stdout.write("Kostenstellen...")
        for cc_code, cc_name in [
            ("4000", "Vertrieb"),
            ("5000", "Service"),
            ("6000", "Verwaltung"),
            ("7000", "Energieeffizienz"),
        ]:
            CostCenter.objects.get_or_create(code=cc_code, defaults={"name": cc_name})

        self.stdout.write("Kategorien / Allergene / Zusatzstoffe...")
        cat_objs = {}
        for name, order in CATEGORIES:
            obj, _ = Category.objects.get_or_create(name=name, defaults={"display_order": order})
            cat_objs[name] = obj
        all_objs = {}
        for code, name in ALLERGENS:
            obj, _ = Allergen.objects.get_or_create(code=code, defaults={"name": name})
            all_objs[code] = obj
        for code, name in ADDITIVES:
            Additive.objects.get_or_create(code=code, defaults={"name": name})

        self.stdout.write("Produkte...")
        prod_objs = {}
        for name, cat, price, allergens, kcal in PRODUCTS:
            p, created = Product.objects.get_or_create(
                name=name,
                defaults={
                    "category": cat_objs[cat],
                    "price_gross": Decimal(price),
                    "kcal": kcal,
                },
            )
            if created and allergens:
                p.allergens.set([all_objs[a] for a in allergens if a in all_objs])
            prod_objs[name] = p

        self.stdout.write("Speisepläne (heute + nächste 4 Werktage, je Kantine)...")
        today = date.today()
        days = []
        d = today
        while len(days) < 5:
            if d.weekday() < 5:  # Mo-Fr
                days.append(d)
            d += timedelta(days=1)

        sample_meals = [
            "Spaghetti Bolognese", "Gemüsecurry mit Reis", "Wiener Schnitzel mit Pommes",
            "Maultaschen in der Brühe", "Salatteller mit Hähnchen",
        ]
        for canteen in canteens.values():
            for i, day in enumerate(days):
                plan, _ = MealPlan.objects.get_or_create(
                    canteen=canteen, serving_date=day,
                    defaults={"is_published": True},
                )
                if not plan.slots.exists():
                    main = sample_meals[i % len(sample_meals)]
                    MealSlot.objects.create(mealplan=plan, product=prod_objs[main], available_qty=40)
                    MealSlot.objects.create(mealplan=plan, product=prod_objs["Tagessuppe"], available_qty=20)

        self.stdout.write("Zuschussregel (Default 30 % für alle)...")
        SubsidyRule.objects.get_or_create(
            name="Default 30%",
            defaults={
                "mode": SubsidyRule.MODE_PERCENT,
                "value": Decimal("30.00"),
                "priority": 0,
                "is_active": True,
            },
        )

        self.stdout.write("Demo-Gruppen...")
        admin_grp, _ = Group.objects.get_or_create(name="Admin")
        user_grp, _ = Group.objects.get_or_create(name="User")

        self.stdout.write("Demo-Admin (admin / Admin12345!)...")
        admin_user, created = User.objects.get_or_create(
            username="admin",
            defaults={"email": "admin@example.local", "is_staff": True, "is_superuser": True,
                      "first_name": "Anna", "last_name": "Admin"},
        )
        if created:
            admin_user.set_password("Admin12345!")
            admin_user.save()
        UserProfile.objects.get_or_create(
            user=admin_user,
            defaults={"location": locations["LE"], "must_change_password": False},
        )
        admin_user.groups.add(admin_grp)

        self.stdout.write("Demo-User (user / User12345!)...")
        normal, created = User.objects.get_or_create(
            username="user",
            defaults={"email": "user@example.local", "first_name": "Uwe", "last_name": "User"},
        )
        if created:
            normal.set_password("User12345!")
            normal.save()
        UserProfile.objects.get_or_create(
            user=normal,
            defaults={"location": locations["LE"], "must_change_password": False,
                      "employee_id": "12345"},
        )
        normal.groups.add(user_grp)

        self.stdout.write(self.style.SUCCESS("Seed abgeschlossen."))
        self.stdout.write(self.style.WARNING("Demo-Logins: admin/Admin12345! und user/User12345!"))
        self.stdout.write(self.style.WARNING("In Produktion NIEMALS dieses Skript verwenden."))
