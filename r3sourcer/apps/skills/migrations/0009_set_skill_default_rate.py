# -*- coding: utf-8 -*-
# Generated by Django 1.10.7 on 2018-06-29 12:12
from __future__ import unicode_literals

from django.db import migrations


def migrate_default_skill_rate(apps, schema_editor):
    Skill = apps.get_model("skills", "Skill")

    for skill in Skill.objects.all():
        default_base_rate = skill.skill_rate_defaults.filter(default_rate=True).first()
        if not default_base_rate:
            default_base_rate = skill.skill_rate_defaults.filter(
                hourly_rate__gt=0.0
            ).order_by('hourly_rate').first()

        if default_base_rate:
            skill.default_rate = default_base_rate.hourly_rate

        price_list_rate = skill.price_list_rates.filter(default_rate=True).first()
        if not price_list_rate:
            price_list_rate = skill.price_list_rates.all().first()

        if price_list_rate:
            skill.price_list_default_rate = price_list_rate.hourly_rate

        skill.save()


class Migration(migrations.Migration):

    dependencies = [
        ('skills', '0008_added_price_list_limits'),
    ]

    operations = [
        migrations.RunPython(migrate_default_skill_rate, migrations.RunPython.noop),
    ]
