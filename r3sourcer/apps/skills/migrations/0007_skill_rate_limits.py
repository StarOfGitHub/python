# -*- coding: utf-8 -*-
# Generated by Django 1.10.7 on 2018-05-10 06:56
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('skills', '0006_skill_on_delete'),
    ]

    operations = [
        migrations.AddField(
            model_name='skill',
            name='default_rate',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=16, null=True),
        ),
        migrations.AddField(
            model_name='skill',
            name='lower_rate_limit',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=16, null=True),
        ),
        migrations.AddField(
            model_name='skill',
            name='upper_rate_limit',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=16, null=True),
        ),
    ]