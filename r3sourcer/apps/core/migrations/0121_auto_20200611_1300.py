# -*- coding: utf-8 -*-
# Generated by Django 1.11.17 on 2020-06-11 13:00
from __future__ import unicode_literals
import datetime

from django.db import migrations


def change_contact_default_languages(apps, schema_editor):
    from r3sourcer.apps.core.models.core import ContactLanguage, Contact
    for contact in Contact.objects.all():
        contact.save()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0120_auto_20200611_1257'),
    ]

    operations = [
        # migrations.RunPython(change_contact_default_languages),
    ]