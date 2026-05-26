from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("lunch", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="canteen",
            name="cutoff_order_time",
        ),
        migrations.RemoveField(
            model_name="canteen",
            name="cancel_cutoff_minutes_before_serving",
        ),
    ]
