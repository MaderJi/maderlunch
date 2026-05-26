from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lunch", "0002_remove_canteen_cutoff_fields"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="order",
            name="uniq_order_per_user_slot",
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.UniqueConstraint(
                fields=("user_profile", "meal_slot"),
                condition=models.Q(status="placed"),
                name="uniq_active_order_per_user_slot",
            ),
        ),
    ]
