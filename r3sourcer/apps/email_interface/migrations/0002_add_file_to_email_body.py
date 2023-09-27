# -*- coding: utf-8 -*-
# Generated by Django 1.11.16 on 2019-04-09 20:21
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('filer', '0007_auto_20161016_1055'),
        ('email_interface', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='emailbody',
            name='file',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='bodies', to='filer.File', verbose_name='File'),
        ),
        migrations.AlterField(
            model_name='emailbody',
            name='content',
            field=models.TextField(blank=True, null=True, verbose_name='Mail message body'),
        ),
    ]
