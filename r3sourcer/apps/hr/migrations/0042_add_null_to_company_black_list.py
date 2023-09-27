from __future__ import unicode_literals

from django.db import migrations, models
import easy_thumbnails.fields
import r3sourcer.apps.hr.models


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0041_add_new_choice'),
    ]

    operations = [
        migrations.AlterField(
            model_name='blacklist',
            name='company',
            field=models.ForeignKey(on_delete=models.deletion.PROTECT, related_name='blacklists',
                       to='core.Company', verbose_name='Company', null=True, blank=True)
        ),
    ]
