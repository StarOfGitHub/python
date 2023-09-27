# -*- coding: utf-8 -*-
# Generated by Django 1.11.29 on 2021-01-28 08:46
from __future__ import unicode_literals

import json
import os

from django.core.management import CommandError
from django.db import migrations


class Migration(migrations.Migration):

    def load_new_extranet_navigation_from_fixture(apps, schema_editor):
        ExtranetNavigation = apps.get_model("core", "ExtranetNavigation")
        entities = []
        try:
            basepath = os.path.dirname(__file__)
            filepath = os.path.abspath(os.path.join(
                basepath, "..", "fixtures", "extranet_navigation.json")
            )
            with open(filepath, 'r') as json_file:
                data = json.load(json_file)
                for el in data:
                    try:
                        template = el['fields']
                        ExtranetNavigation.objects.get(name=template['name'])
                    except ExtranetNavigation.DoesNotExist:
                        obj = ExtranetNavigation(
                            pk=el['pk'],
                            updated_at=template['updated_at'],
                            created_at=template['created_at'],
                            parent=template['parent'],
                            name=template['name'],
                            url=template['url'],
                            endpoint=template['endpoint'],
                            access_level=template['access_level'],
                            lft=template['lft'],
                            rght=template['rght'],
                            tree_id=template['tree_id'],
                            level=template['level'])
                        entities.append(obj)
            if len(entities) > 0:
                ExtranetNavigation.objects.bulk_create(entities)

        except Exception as e:
            raise CommandError(e)

    dependencies = [
        ('core', '0141_auto_20210108_1513'),
    ]

    operations = [
        # migrations.RunPython(load_new_extranet_navigation_from_fixture),
    ]
