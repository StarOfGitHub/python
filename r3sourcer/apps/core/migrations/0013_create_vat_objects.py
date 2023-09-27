# -*- coding: utf-8 -*-
# Generated by Django 1.10.7 on 2018-01-23 09:41
from __future__ import unicode_literals

import datetime
from django.db import migrations


def create_vat_objects(apps, schema_editor):
    Country = apps.get_model("core", "Country")
    VAT = apps.get_model("core", "VAT")
    country, _ = Country.objects.get_or_create(name="Australia", code2='AU')

    VAT.objects.create(
        country=country,
        name='GST',
        rate=0.1,
        start_date=datetime.date(2017, 1, 1)
    )
    VAT.objects.create(
        country=country,
        name='GNR',
        rate=0,
        start_date=datetime.date(2017, 1, 1)
    )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_create_rules'),
    ]

    operations = [
        migrations.RunPython(create_vat_objects)
    ]
