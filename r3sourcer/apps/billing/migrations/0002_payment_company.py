# -*- coding: utf-8 -*-
# Generated by Django 1.10.7 on 2018-07-09 11:20
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0049_tag_confidential'),
        ('billing', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='company',
            field=models.ForeignKey(default='', on_delete=django.db.models.deletion.CASCADE, to='core.Company'),
            preserve_default=False,
        ),
    ]
