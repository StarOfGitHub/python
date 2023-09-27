from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import easy_thumbnails.fields
import r3sourcer.apps.hr.models


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0039_added_client_company_favourite_list'),
    ]

    operations = [
        migrations.AlterField(
            model_name='TimeSheet',
            name='supervisor_signature',
            field=easy_thumbnails.fields.ThumbnailerImageField(blank=True, null=True, max_length=255, upload_to=r3sourcer.apps.hr.models.TimeSheet.supervisor_signature_path, verbose_name='Supervisor signature'),
        ),
    ]
