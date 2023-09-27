# -*- coding: utf-8 -*-
# Generated by Django 1.11.16 on 2019-11-28 23:01
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sms_interface', '0006_smsmessage_segment_default'),
    ]

    operations = [
        migrations.AlterField(
            model_name='phonenumber',
            name='created_at',
            field=models.DateTimeField(editable=False, verbose_name='Created at'),
        ),
        migrations.AlterField(
            model_name='smsmessage',
            name='created_at',
            field=models.DateTimeField(editable=False, verbose_name='Created at'),
        ),
        migrations.AlterField(
            model_name='smsrelatedobject',
            name='created_at',
            field=models.DateTimeField(editable=False, verbose_name='Created at'),
        ),
        migrations.AlterField(
            model_name='smstemplate',
            name='created_at',
            field=models.DateTimeField(editable=False, verbose_name='Created at'),
        ),
    ]