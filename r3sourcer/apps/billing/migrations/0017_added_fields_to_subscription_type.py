# -*- coding: utf-8 -*-
# Generated by Django 1.10.7 on 2018-08-13 10:54
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0016_remove_subscription_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriptiontype',
            name='discount_comment',
            field=models.CharField(max_length=255, blank=True, null=True),
        ),
        migrations.AddField(
            model_name='subscriptiontype',
            name='amount_comment',
            field=models.CharField(max_length=255, blank=True, null=True),
            ),
        migrations.AddField(
            model_name='subscriptiontype',
            name='heading_tag_line',
            field=models.CharField(max_length=255, blank=True, null=True),
            ),
    ]
