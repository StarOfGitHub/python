import datetime
import logging
from decimal import Decimal
import pytz
import stripe
from django.conf import settings
from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils.formats import date_format
from django.utils.translation import ugettext_lazy as _
from model_utils import Choices
from stripe.error import InvalidRequestError, CardError

from r3sourcer import ref
from r3sourcer.apps.core import tasks
from r3sourcer.apps.core.models import VAT
from r3sourcer.apps.core.models.mixins import CompanyTimeZoneMixin
from r3sourcer.apps.email_interface.models import EmailTemplate, DefaultEmailTemplate
from r3sourcer.helpers.datetimes import utc_now

logger = logging.getLogger(__name__)


class Subscription(CompanyTimeZoneMixin):
    """Subscription class mirrors the Stripe subscription

    Statuses:
    - Subscription is created with status `incomplete`.
    - Subscription status is set to `active` when invoice is paid.
    - Subscriptions that start with a trial don’t require payment and have the `trialing` status.
    For once time invoicing: if no payment is made during 23 hours, the subscription is updated to `incomplete_expired`.
    For automatic invoicing: if automatic payment fails, the subscription is updated to `past_due` and Stripe attempts
    to recover payment based on your retry rules. If payment recovery fails,
    you can set the subscription status to `canceled`, `unpaid`, or you can leave it `active`."""
    ALLOWED_STATUSES = ('active', 'incomplete', 'trialing')
    SUBSCRIPTION_STATUSES = Choices(
        ('active', 'Active'),
        ('past_due', 'Past due'),
        ('canceled', 'Canceled'),
        ('unpaid', 'Unpaid'),
        ('incomplete', 'Incomplete'),
        ('trialing', 'Trialing'),
        ('incomplete_expired', 'Incomplete expired'),
    )
    company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE,
        related_name='subscriptions')
    name = models.CharField(max_length=255)
    subscription_type = models.ForeignKey(
        'billing.SubscriptionType',
        on_delete=models.DO_NOTHING,
        related_name='subscriptions')
    price = models.PositiveIntegerField()
    worker_count = models.PositiveIntegerField()
    created = ref.DTField()
    active = models.BooleanField(default=True)
    status = models.CharField(max_length=255, choices=SUBSCRIPTION_STATUSES)
    current_period_start = ref.DTField(blank=True, null=True)
    current_period_end = ref.DTField(blank=True, null=True)

    # stripe ids
    plan_id = models.CharField(max_length=255)
    subscription_id = models.CharField(max_length=255)

    @property
    def created_tz(self):
        return self.utc2local(self.created)

    @property
    def created_utc(self):
        return self.created

    @property
    def current_period_start_tz(self):
        return self.utc2local(self.current_period_start)

    @property
    def current_period_start_utc(self):
        return self.current_period_start

    @property
    def current_period_end_tz(self):
        return self.utc2local(self.current_period_end)

    @property
    def current_period_end_utc(self):
        return self.current_period_end

    @property
    def current_period_end_plus_two_week(self):
        return self.current_period_end + datetime.timedelta(days=14)

    def __str__(self):
        return "{} with {} workers. Status: {}".format(self.company.name, self.worker_count, self.status)

    def get_total_subscription_amount(self):
        active_workers = self.company.active_workers(self.current_period_start)
        if self.subscription_type.type == self.subscription_type.SUBSCRIPTION_TYPES.monthly:
            total_amount = self.subscription_type.start_range_price_monthly
        else:
            total_amount = self.subscription_type.start_range_price_annual
        start_workers = settings.SUBSCRIPTION_START_WORKERS
        if active_workers > start_workers:
            total_amount += (active_workers - start_workers) * self.subscription_type.step_change_val
        if self.subscription_type.type == self.subscription_type.SUBSCRIPTION_TYPES.annual:
            if self.subscription_type.percentage_discount:
                total_amount = (total_amount * 12) - (
                        total_amount * 12 / 100 * self.subscription_type.percentage_discount)
            else:
                total_amount = total_amount * 12 * settings.SUBSCRIPTION_DEFAULT_DISCOUNT
        if self.subscription_type.type == self.subscription_type.SUBSCRIPTION_TYPES.monthly:
            if self.subscription_type.percentage_discount:
                total_amount = total_amount - (total_amount / 100 * self.subscription_type.percentage_discount)
            else:
                total_amount = total_amount
        return total_amount

    def get_stripe_subscription(self):
        stripe.api_key = StripeCountryAccount.get_stripe_key_on_company(self.company)
        subscription = stripe.Subscription.retrieve(self.subscription_id)
        return subscription

    def sync_status(self, stripe_subscription=None):
        logger.warning('Synchronization statuses for subscription {}'.format(self.subscription_id))
        if not stripe_subscription:
            stripe.api_key = StripeCountryAccount.get_stripe_key_on_company(self.company)
            stripe_subscription = stripe.Subscription.retrieve(self.subscription_id)

        self.status = stripe_subscription.status
        if stripe_subscription.status not in self.ALLOWED_STATUSES:
            self.active = False
        else:
            self.active = True
        self.save(update_fields=['status', 'active'])

    def update_user_permissions(self, stripe_subscription=None):
        this_user = self.company.get_user()
        if this_user.trial_period_start:
            end_of_trial = this_user.get_end_of_trial_as_date()
            if self.status not in self.ALLOWED_STATUSES and self.now_utc > end_of_trial:
                logger.warning('Call deactivate subscription {} from update_user_permissions based on trial'.format(self.subscription_id))
                self.deactivate(user_id=(str(this_user.id)), stripe_subscription=stripe_subscription)
        # elif self.status in allowed_statuses:
        #     self.activate(user_id=(str(this_user.id)))

        # waiting for 14 days to pay then cancel subscription
        if self.current_period_end_plus_two_week.replace(tzinfo=pytz.UTC) < self.now_utc:
            logger.warning('Call deactivate subscription {} from update_user_permissions'.format(self.subscription_id))
            self.deactivate(user_id=(str(this_user.id) if this_user else None), stripe_subscription=stripe_subscription)

    def sync_periods(self, stripe_subscription=None):
        if self.active:
            logger.warning('Synchronization periods for subscription {}'.format(self.subscription_id))
            if not stripe_subscription:
                stripe.api_key = StripeCountryAccount.get_stripe_key_on_company(self.company)
                stripe_subscription = stripe.Subscription.retrieve(self.subscription_id)

            self.current_period_start = datetime.datetime.utcfromtimestamp(stripe_subscription.current_period_start)
            self.current_period_end = datetime.datetime.utcfromtimestamp(stripe_subscription.current_period_end)
            self.save(update_fields=['current_period_start', 'current_period_end'])

    def deactivate(self, user_id=None, stripe_subscription=None):
        logger.warning('Deactivating subscription {}'.format(self.subscription_id))
        if not stripe_subscription:
            stripe.api_key = StripeCountryAccount.get_stripe_key_on_company(self.company)
            stripe_subscription = stripe.Subscription.retrieve(self.subscription_id)
        try:
            stripe_subscription.modify(self.subscription_id, cancel_at_period_end=True, proration_behavior=None)
            logger.warning('Successfully deactivate subscription {}'.format(self.subscription_id))
        except InvalidRequestError as e:
            logger.warning('Cannot deactivate subscription {}. It is missed, probably cancelled: {}'.format(self.subscription_id, e))
        if user_id:
            tasks.cancel_subscription_access.apply_async([user_id])

    @staticmethod
    def activate(user_id=None):
        if user_id:
            tasks.give_subscription_access.apply_async([user_id])

    @property
    def last_time_billed(self):
        last_payment = self.company.payment_set.order_by('-created').first()

        if last_payment:
            return last_payment.created

    @property
    def sms_balance(self):
        return self.company.sms_balance.balance

    def save(self, *args, **kwargs):
        if not self.created:
            self.created = self.now_utc
        super().save(*args, **kwargs)

        if self.active:
            subscriptions = Subscription.objects.filter(
                company=self.company,
                active=True,
            ).exclude(id=self.id)

            for subscription in subscriptions:
                subscription.deactivate()
                subscription.status = Subscription.SUBSCRIPTION_STATUSES.canceled
                subscription.active = False
                subscription.save(update_fields=['status', 'active'])

    @classmethod
    def use_logger(cls):
        return True


class SMSBalance(models.Model):
    company = models.OneToOneField(
        'core.Company',
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name='sms_balance')
    balance = models.DecimalField(default=0, max_digits=8, decimal_places=2)
    top_up_amount = models.IntegerField(default=100)
    top_up_limit = models.IntegerField(default=10)
    last_payment = models.ForeignKey('Payment', blank=True, null=True, on_delete=models.SET_NULL)
    cost_of_segment = models.DecimalField(default=0, max_digits=8, decimal_places=2)
    auto_charge = models.BooleanField(default=False, verbose_name=_('Auto Charge'))
    low_balance_sent = models.BooleanField(default=False)
    ran_out_balance_sent = models.BooleanField(default=False)

    @property
    def segment_cost(self):
        return self.cost_of_segment or settings.COST_OF_SMS_SEGMENT

    def substract_sms_cost(self, number_of_segments):
        amount = Decimal(number_of_segments) * self.segment_cost
        self.balance = self.balance - Decimal(amount)
        self.save()

    def charge_for_sms(self, amount):
        country_code = self.company.get_hq_address().address.country.code2
        stripe_secret_key = StripeCountryAccount.get_stripe_key(country_code)
        stripe.api_key = stripe_secret_key
        # try to create and pay invoice if it's the first payment
        # or if payment was more than a 3 minutes ago to exclude duplicates
        if self.last_payment is None or self.last_payment.created_utc + datetime.timedelta(minutes=3) < utc_now():
            vat_object = VAT.get_vat(country_code).first()
            tax_percent = vat_object.stripe_rate

            for discount in self.company.get_active_discounts('sms'):
                amount = discount.apply_discount(amount)

            tax_value = tax_percent / 100 + 1
            stripe.InvoiceItem.create(customer=self.company.stripe_customer,
                                      amount=round(int(amount * 100 / tax_value)),
                                      currency=self.company.currency,
                                      description='Topping up sms balance')
            logger.info('InvoiceItem Topping up sms balance created for {} to {}'.format(
                round(int(amount * 100 / tax_value)),
                self.company.id
            ))
            invoice = stripe.Invoice.create(customer=self.company.stripe_customer,
                                            default_tax_rates=[vat_object.stripe_id],
                                            description='Topping up sms balance',
                                            pending_invoice_items_behavior='include'
                                            )
            logger.info('Invoice Topping up sms balance created to {}'.format(self.company.id))
            payment = Payment.objects.create(
                company=self.company,
                type=Payment.PAYMENT_TYPES.sms,
                amount=amount,
                stripe_id=invoice['id'],
                invoice_url=invoice['invoice_pdf'],
                status=invoice['status']
            )
            # pay an invoice after creation of corresponding Payment
            try:
                invoice.pay()
            except CardError as ex:
                # mark as unpaid if error
                payment.status = Payment.PAYMENT_STATUSES.not_paid
                payment.save()
                logger.warning('Invoice Topping up sms balance was not successful for {}'.format(self.company.id))
            else:
                # increase balance if payment is successful
                self.balance += Decimal(payment.amount)
                payment.status = Payment.PAYMENT_STATUSES.paid
                payment.save()
                logger.info('Invoice Topping up sms balance was successful for {}'.format(self.company.id))
            finally:
                # in any case save the last payment to sms_balance
                self.last_payment = payment
                self.save()
                logger.info('Topping up sms balance for {} finished'.format(self.company.id))


    def save(self, *args, **kwargs):
        from r3sourcer.apps.billing.tasks import charge_for_sms

        if self.balance <= self.top_up_limit and self.auto_charge is True:
            charge_for_sms.delay(self.top_up_amount, self.id)

        if self.company.is_master:
            low_limit = SMSBalanceLimits.objects.filter(name="Low").first()
            if low_limit:
                if Decimal(self.balance) < low_limit.low_balance_limit and self.low_balance_sent is False:
                    tasks.send_sms_balance_is_low_email.delay(self.company.id, template=low_limit.email_template.slug)
                    self.low_balance_sent = True

                if Decimal(self.balance) > low_limit.low_balance_limit and self.low_balance_sent is True:
                    self.low_balance_sent = False

            ran_out_limit = SMSBalanceLimits.objects.filter(name="Ran out").first()
            if ran_out_limit:
                if Decimal(self.balance) < ran_out_limit.low_balance_limit and self.ran_out_balance_sent is False:
                    tasks.send_sms_balance_ran_out_email.delay(self.company.id,
                                                               template=ran_out_limit.email_template.slug)
                    self.ran_out_balance_sent = True

                if Decimal(self.balance) > ran_out_limit.low_balance_limit and self.ran_out_balance_sent is True:
                    self.ran_out_balance_sent = False

        if Decimal(self.balance) - self.segment_cost < 0:
            self.company.sms_enabled = False
            self.company.save()

        if not self.company.sms_enabled and Decimal(self.balance) - self.segment_cost > 0:
            self.company.sms_enabled = True
            self.company.save()

        super().save(*args, **kwargs)

    @classmethod
    def use_logger(cls):
        return True


class Payment(CompanyTimeZoneMixin):
    PAYMENT_TYPES = Choices(
        ('sms', 'SMS'),
        ('extra_workers', 'Extra Workers'),
        ('subscription', 'Subscription'),
        ('candidate', 'Candidate Profile'),
    )
    PAYMENT_STATUSES = Choices(
        ('paid', 'Paid'),
        ('not_paid', 'Not paid')
    )
    company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE)
    type = models.CharField(max_length=255, choices=PAYMENT_TYPES)
    created = ref.DTField()
    amount = models.DecimalField(default=0, max_digits=8, decimal_places=2)
    status = models.CharField(max_length=255, choices=PAYMENT_STATUSES, default=PAYMENT_STATUSES.not_paid)
    stripe_id = models.CharField(max_length=255)
    invoice_url = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return '{} Payment at {}'.format(self.company, date_format(self.created, settings.DATETIME_MYOB_FORMAT))

    @property
    def created_tz(self):
        return self.utc2local(self.created)

    @property
    def created_utc(self):
        return self.created

    def save(self, *args, **kwargs):
        if not self.created:
            self.created = self.now_utc
        super().save(*args, **kwargs)

    @classmethod
    def use_logger(cls):
        return True


class Discount(CompanyTimeZoneMixin):
    DURATIONS = Choices(
        ('forever', 'Forever'),
        ('once', 'Once'),
        ('repeating', 'Repeating')
    )
    PAYMENT_TYPES = Choices(
        ('sms', 'SMS'),
        ('extra_workers', 'Extra Workers'),
        ('subscription', 'Subscription')
    )
    company = models.ForeignKey(
        'core.Company',
        related_name='discounts',
        on_delete=models.CASCADE
    )
    payment_type = models.CharField(max_length=255, choices=PAYMENT_TYPES, blank=True, null=True)
    percent_off = models.IntegerField(blank=True, null=True)
    amount_off = models.IntegerField(blank=True, null=True)
    active = models.BooleanField(default=True)
    duration = models.CharField(max_length=255, choices=DURATIONS)
    duration_in_months = models.IntegerField(blank=True, null=True)
    created = ref.DTField()

    @property
    def created_tz(self):
        return self.utc2local(self.created)

    @property
    def created_utc(self):
        return self.created

    def apply_discount(self, original_amount):
        if self.percent_off:
            discounted_value = original_amount * (1.0 - (float(self.percent_off) / 100))
        else:
            discounted_value = original_amount - self.amount_off

        if self.duration == self.DURATIONS.once:
            self.active = False
            self.save()

        if self.duration == self.DURATIONS.repeating and self.duration_in_months:
            duration_in_days = 30 * self.duration_in_months

            if self.created + datetime.timedelta(days=duration_in_days) < utc_now():
                self.active = False
                self.save()

        return discounted_value

    def save(self, *args, **kwargs):
        if not self.created:
            self.created = self.now_utc

        if not self.id and self.payment_type == 'subscription':
            subscription = Subscription.objects.get(company=self.company, active=True)

            coupon_data = {
                'duration': self.duration,
            }

            if self.percent_off:
                coupon_data.update({
                    'percent_off': self.percent_off,
                })
            else:
                coupon_data.update({
                    'amount_off': self.amount_off,
                    'currency': self.company.currency
                })

            if self.duration_in_months:
                coupon_data.update({
                    'duration_in_months': self.duration_in_months
                })
            StripeCountryAccount.get_stripe_key_on_company(self.company)
            coupon = stripe.Coupon.create(**coupon_data)
            subscription = stripe.Subscription.retrieve(subscription.subscription_id)
            subscription.coupon = coupon.id
            subscription.save()
        super().save(*args, **kwargs)


class SubscriptionType(models.Model):
    SUBSCRIPTION_TYPES = Choices(
        ('annual', 'Annual'),
        ('monthly', 'Monthly')
    )
    type = models.CharField(max_length=255, choices=SUBSCRIPTION_TYPES)
    employess_total_num = models.PositiveIntegerField(blank=True, null=True)
    max_employess_num = models.PositiveIntegerField(blank=True, null=True)
    start_range = models.PositiveIntegerField(blank=True, null=True)
    start_range_price_monthly = models.PositiveIntegerField(blank=True, null=True)
    start_range_price_annual = models.PositiveIntegerField(blank=True, null=True)
    step_change_val = models.PositiveIntegerField(blank=True, null=True)
    heading = models.CharField(max_length=255, blank=True, null=True)
    amount = models.PositiveIntegerField(blank=True, null=True)
    amount_tag_line = models.CharField(max_length=255, blank=True, null=True)
    amount_annual = models.CharField(max_length=255, blank=True, null=True)
    table_text = models.CharField(max_length=255, blank=True, null=True)
    discount_comment = models.CharField(max_length=255, blank=True, null=True)
    percentage_discount = models.PositiveIntegerField(blank=True, null=True)
    amount_comment = models.CharField(max_length=255, blank=True, null=True)
    heading_tag_line = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.type

    def save(self, *args, **kwargs):
        from r3sourcer.apps.billing.tasks import charge_for_new_amount
        charge_for_new_amount.delay()
        super().save(*args, **kwargs)


class StripeCountryAccount(models.Model):
    country = models.ForeignKey(
        'core.Country',
        to_field='code2',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    stripe_public_key = models.CharField(max_length=255, blank=True, null=True)
    stripe_secret_key = models.CharField(max_length=255, blank=True, null=True)
    stripe_product_id = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        verbose_name = _("Stripe Country Account")
        verbose_name_plural = _("Stripe Country Accounts")

    def __str__(self):
        return self.country.name

    @classmethod
    def get_stripe_key(cls, country_code2='EE'):
        """
        return: settings api key for Stripe Country Account
        default: EE for Estonia Stripe Account
        """
        if settings.DEBUG:
            return settings.STRIPE_SECRET_API_KEY
        stripe_accounts = cls.objects.filter(country=country_code2)
        if not stripe_accounts and country_code2 == 'EE':
            raise Exception("Not Even Estonia account found. Configure stripe accounts!")
        stripe_account = stripe_accounts.first() or cls.objects.filter(country='EE').first()
        api_key = stripe_account.stripe_secret_key
        return api_key

    @classmethod
    def get_stripe_key_on_company(cls, company):
        country_code = company.get_country_code()
        api_key = cls.get_stripe_key(country_code)
        return api_key

    @classmethod
    def get_stripe_pub(cls, country_code2='EE'):
        if settings.DEBUG:
            return settings.STRIPE_PUBLIC_API_KEY
        stripe_accounts = cls.objects.filter(country=country_code2)
        if not stripe_accounts and country_code2 == 'EE':
            raise Exception("Not Even Estonia account found. Configure stripe accounts!")
        stripe_account = stripe_accounts.first() or cls.objects.filter(country='EE').first()
        api_key = stripe_account.stripe_public_key
        return api_key


class SMSBalanceLimits(models.Model):
    name = models.CharField(max_length=255, unique=True)
    low_balance_limit = models.PositiveIntegerField(default=20)
    email_template = models.ForeignKey(
        DefaultEmailTemplate,
        on_delete=models.CASCADE,
    )
