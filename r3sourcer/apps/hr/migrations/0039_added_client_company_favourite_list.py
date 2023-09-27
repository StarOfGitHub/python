from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0038_timesheet_supervisor_modified_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='favouritelist',
            name='client_contact',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.CASCADE, related_name='favouritelist_client', to='core.CompanyContact', verbose_name='Favourite list client'),
        ),
        migrations.AddField(
            model_name='blacklist',
            name='client_contact',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.CASCADE,
                                    related_name='blacklists_client', to='core.CompanyContact',
                                    verbose_name='Company Client'),
            ),

    ]
