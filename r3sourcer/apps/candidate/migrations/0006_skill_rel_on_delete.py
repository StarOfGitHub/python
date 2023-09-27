# -*- coding: utf-8 -*-
# Generated by Django 1.10.7 on 2018-04-24 11:33
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('candidate', '0005_update_candidaterel'),
    ]

    operations = [
        migrations.AlterField(
            model_name='skillrel',
            name='skill',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='candidate_skills', to='skills.Skill', verbose_name='Skill'),
        ),
    ]