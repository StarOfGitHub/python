from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0011_ratecoefficientrel'),
    ]

    operations = [
        migrations.AddField(
            model_name='timeofdayworkrule',
            name='used',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='allowanceworkrule',
            name='used',
            field=models.BooleanField(default=False),
            ),
        migrations.AddField(
            model_name='overtimeworkrule',
            name='used',
            field=models.BooleanField(default=False),
            ),
    ]
