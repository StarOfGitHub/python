from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0017_added_fields_to_subscription_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriptiontype',
            name='percentage_discount',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
