# -*- coding: utf-8 -*-
# Generated by Django 1.11.17 on 2020-11-06 14:53
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('candidate', '0037_auto_20201106_1335'),
    ]

    operations = [
        migrations.AlterField(
            model_name='taxnumbertype',
            name='country',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='core.Country', verbose_name='Country'),
        ),
    ]
