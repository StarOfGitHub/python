from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('billing', '0018_added_percentage_discount_to_subscription_type'),
    ]

    operations = [
            migrations.CreateModel(
            name='StripeCountryAccount',
            fields=[
                ('stripe_public_key', models.CharField(blank=True, max_length=255, null=True)),
                ('stripe_secret_key', models.CharField(blank=True, max_length=255, null=True)),
                ('stripe_product_id', models.CharField(blank=True, max_length=255, null=True)),
                ('country',
                 models.ForeignKey(on_delete=models.deletion.CASCADE,
                                   to='core.Country', to_field='code2')),
            ],
            options={
                'verbose_name': 'Stripe Country Account',
                'verbose_name_plural': 'Stripe Country Accounts',
            },
        ),
        ]