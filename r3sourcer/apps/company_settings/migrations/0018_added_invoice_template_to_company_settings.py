from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('company_settings', '0017_companysettings_pre_shift_sms_delta'),
    ]

    operations = [
        migrations.AddField(
            model_name='companysettings',
            name='invoice_template',
            field=models.TextField(blank=True, default='', null=True),
        ),
    ]