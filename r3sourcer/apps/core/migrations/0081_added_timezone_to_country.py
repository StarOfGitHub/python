from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0080_added_trial_start_date_field'),
    ]

    operations = [
        migrations.AddField(
            model_name='country',
            name='country_timezone',
            field=models.CharField(blank=True, null=True, verbose_name='Country Timezone', max_length=255),
        ),
    ]
