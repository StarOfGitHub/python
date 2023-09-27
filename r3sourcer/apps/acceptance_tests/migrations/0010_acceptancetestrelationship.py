# -*- coding: utf-8 -*-
# Generated by Django 1.11.16 on 2018-11-12 09:52
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0072_set_contact_relations'),
        ('acceptance_tests', '0009_valid_until_nullable'),
    ]

    operations = [
        migrations.CreateModel(
            name='AcceptanceTestRelationship',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created at')),
                ('acceptance_test', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='acceptance_test_relations', to='acceptance_tests.AcceptanceTest', verbose_name='Acceptance Test')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='acceptance_test_relations', to='core.Company', verbose_name='Company')),
            ],
            options={
                'verbose_name_plural': 'Acceptance Test Relations',
                'verbose_name': 'Acceptance Test Relation',
            },
        ),
    ]