# -*- coding: utf-8 -*-
# Generated by Django 1.11.29 on 2021-07-29 13:12
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0146_add_note_files'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='invoiceline',
            name='unit_type',
        ),
        migrations.RemoveField(
            model_name='orderline',
            name='unit_type',
        ),
        migrations.AddField(
            model_name='invoiceline',
            name='unit_name',
            field=models.CharField(default='hours', max_length=20, verbose_name='Unit Name'),
        ),
        migrations.AddField(
            model_name='orderline',
            name='unit_name',
            field=models.CharField(default='hours', max_length=20, verbose_name='Unit Name'),
        ),
        migrations.AlterField(
            model_name='invoiceline',
            name='vat',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='core.VAT', verbose_name='VAT'),
        ),
        migrations.AlterField(
            model_name='orderline',
            name='vat',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='core.VAT', verbose_name='VAT'),
        ),
    ]
