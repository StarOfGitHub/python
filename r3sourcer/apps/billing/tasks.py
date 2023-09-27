from datetime import timedelta

import stripe

from celery import shared_task
from celery.utils.log import get_task_logger

from django.conf import settings
from django.db import transaction
from django.db.models import Count
from stripe.error import InvalidRequestError, StripeError

from r3sourcer.apps.billing.models import (
                            Subscription,
                            Payment,
                            SMSBalance,
                            SubscriptionType,
                            StripeCountryAccount as sca,
    )
from r3sourcer.apps.core.models import Company, VAT
from r3sourcer.apps.core.tasks import cancel_subscription_access
from r3sourcer.apps.email_interface.utils import get_email_service
from r3sourcer.apps.billing import STRIPE_INTERVALS
from r3sourcer.helpers.datetimes import utc_now

logger = get_task_logger(__name__)


@shared_task
def charge_for_extra_workers():
    """
    Checks number of active workers. If that number is bigger that number of workers from client's plan
    then it charges extra fee for every worker and adjust subscription plan to number of active workers.
    """
    today = utc_now().date()
    company_list = Company.objects.filter(type=Company.COMPANY_TYPES.master) \
                                  .filter(subscriptions__active=True) \
                                  .filter(subscriptions__current_period_end=today)

    for company in company_list:
        subscription = company.active_subscription
        paid_workers = subscription.worker_count
        active_workers = company.active_workers(subscription.current_period_start)
        country_code = company.get_country_code()
        stripe.api_key = sca.get_stripe_key(country_code)
        vat_object = VAT.get_vat(country_code).first()
        plan_type = subscription.subscription_type.type

        if active_workers > paid_workers:
            if plan_type == SubscriptionType.SUBSCRIPTION_TYPES.annual:
                extra_worker_fee = settings.ANNUAL_EXTRA_WORKER_FEE
            else:
                extra_worker_fee = settings.MONTHLY_EXTRA_WORKER_FEE

            extra_workers = active_workers - paid_workers
            amount = extra_workers * extra_worker_fee

            for discount in company.get_active_discounts('extra_workers'):
                amount = discount.apply_discount(amount)
            # charge for additional workers
            stripe.InvoiceItem.create(customer=company.stripe_customer,
                                      amount=round((amount * 100) / 1.1),
                                      currency=company.currency,
                                      description='%s extra workers fee' % extra_workers)
            invoice = stripe.Invoice.create(customer=company.stripe_customer,
                                            default_tax_rates=[vat_object.stripe_id],
                                            description='%s extra workers fee' % extra_workers)
            Payment.objects.create(
                company=company,
                type=Payment.PAYMENT_TYPES.extra_workers,
                amount=amount,
                stripe_id=invoice['id'],
                invoice_url=invoice['invoice_pdf'],
                status=invoice['status']
                )
            # adjust the monthly subscription plan to number of active workers
            if plan_type == SubscriptionType.SUBSCRIPTION_TYPES.monthly:
                amount = subscription.get_total_subscription_amount()
                if not subscription.price == amount:
                    plan_name = 'R3sourcer {} plan for {} workers'.format(plan_type, active_workers)
                    plan = stripe.Plan.create(
                        product=settings.STRIPE_PRODUCT_ID,
                        nickname=plan_name,
                        interval=STRIPE_INTERVALS[plan_type],
                        currency=company.currency,
                        amount=round((int(amount) * 100) / 1.1),
                    )
                    subscription_stripe = stripe.Subscription.retrieve(subscription.subscription_id)
                    stripe.Subscription.modify(subscription_stripe.id,
                                               cancel_at_period_end=False,
                                               proration_behavior='none',
                                               items=[{
                                                   'id': subscription_stripe['items']['data'][0].id,
                                                   'plan': plan.id,
                                               }]
                                               )
                    subscription.price = amount
                    subscription.save()


@shared_task
def charge_for_sms(amount, sms_balance_id):
    with transaction.atomic():
        sms_balance = SMSBalance.objects.select_for_update().get(id=sms_balance_id)
        sms_balance.charge_for_sms(amount)


@shared_task
def sync_subscriptions():
    """sync subscriptions statuses and periods"""
    for subscription in Subscription.objects.all():
        try:
            stripe_subscription = subscription.get_stripe_subscription()
            subscription.sync_status(stripe_subscription)
            subscription.sync_periods(stripe_subscription)
            subscription.update_user_permissions(stripe_subscription)
            subscription.save()
        except StripeError as e:
            logger.warning('StripeError during sync_subscriptions: {}'.format(
                e.user_message
            ))

@shared_task
def restrict_access_for_users_without_subscription():
    # for companies without a subscription
    # users should also be restricted by the end of trial
    for company in Company.objects.all().prefetch_related('subscriptions').annotate(count=Count(
            'subscriptions')).filter(count=0):
        this_user = company.get_user()
        now = utc_now()
        if this_user and this_user.trial_period_start and now > this_user.get_end_of_trial_as_date():
            cancel_subscription_access.apply_async([this_user.id])


@shared_task()
def fetch_payments():
    """creates invoices for not payed payments and downloads invoices from stripe for payed"""
    companies = Company.objects.all()

    for company in companies:
        stripe.api_key = sca.get_stripe_key_on_company(company)
        if not company.stripe_customer:
            continue

        customer = company.stripe_customer
        try:
            invoices = stripe.Invoice.list(customer=customer)['data']
        except:
            continue
        # check all customer invoices
        for invoice in invoices:
            # if subscription invoice is unpaid mark active subscription as inactive -- this is done in sync_subscription
            # if invoice['paid'] is False and invoice['subscription'] is not None:
            #     try:
            #         subscription = Subscription.objects.get(subscription_id=invoice['subscription'], active=True)
            #         stripe_subscription = subscription.get_stripe_subscription()
            #         subscription.status = stripe_subscription.status
            #         subscription.active = False
            #         subscription.save()
            #         logger.warning('Mark subscription {} as inactive from fetch_payments'.format(
            #             subscription.subscription_id
            #         ))
            #     except Subscription.DoesNotExist:
            #         pass

            # if payment is not created yet then create it for not-void invoices
            # void means this invoice was a mistake or cancelled.
            if invoice['status'] != 'void' and not Payment.objects.filter(stripe_id=invoice['id']).exists():
                payment_type = Payment.PAYMENT_TYPES.candidate
                if invoice['subscription'] is not None:
                    payment_type = Payment.PAYMENT_TYPES.subscription
                elif 'sms' in invoice['description']:
                    payment_type = Payment.PAYMENT_TYPES.sms
                elif 'extra workers' in invoice['description']:
                    payment_type = Payment.PAYMENT_TYPES.extra_workers
                logger.warning('Create payment with invoice {} from fetch_payments'.format(
                    invoice['id']
                ))
                Payment.objects.create(
                    company=company,
                    type=payment_type,
                    amount=invoice['total'] / 100,
                    stripe_id=invoice['id'],
                    invoice_url=invoice['invoice_pdf']
                )

        payments = Payment.objects.filter(invoice_url__isnull=True, company=company)
        for payment in payments:
            try:
                invoice = stripe.Invoice.retrieve(payment.stripe_id)
            except InvalidRequestError as ex:
                if ex.http_status == 404 and ex.code == 'resource_missing':
                    logger.warning('Delete payment with invoice {} from fetch_payments'.format(
                        payment.stripe_id
                    ))
                    payment.delete()
                    continue

            if invoice['invoice_pdf']:
                logger.warning('Set invoice_pdf with invoice {} from fetch_payments'.format(
                    payment.stripe_id
                ))
                payment.invoice_url = invoice['invoice_pdf']
                payment.save()

        not_paid_payments = Payment.objects.filter(status=Payment.PAYMENT_STATUSES.not_paid, company=company)
        for payment in not_paid_payments:
            try:
                invoice = stripe.Invoice.retrieve(payment.stripe_id)
            except InvalidRequestError as ex:
                if ex.http_status == 404 and ex.code == 'resource_missing':
                    logger.warning('Delete payment with invoice {} from fetch_payments'.format(
                        payment.stripe_id
                    ))
                    payment.delete()
                    continue

            if invoice['paid'] == True:
                logger.warning('Mark payment with invoice {} as paid from fetch_payments'.format(
                    payment.stripe_id
                ))
                payment.status = Payment.PAYMENT_STATUSES.paid
                payment.save()

                if 'sms' in invoice['description']:
                    sms_balance = SMSBalance.objects.filter(last_payment=payment).first()
                    if sms_balance:
                        logger.warning('Add sms balance from payment with invoice {} from fetch_payments'.format(
                            payment.stripe_id
                        ))
                        sms_balance.balance += payment.amount
                        sms_balance.save()

            if invoice['status'] == 'void':
                logger.warning('Delete payment with invoice {} because it\'s void from fetch_payments'.format(
                    payment.stripe_id
                ))
                payment.delete()


@shared_task
def send_sms_payment_reminder():
    balance_objects = SMSBalance.objects.filter(company__type='master',
                                                last_payment__status='not_paid')
    one_day_objects = balance_objects.filter(last_payment__created__gte=utc_now() - timedelta(days=1))
    two_days_objects = balance_objects.filter(last_payment__created__gte=utc_now() - timedelta(days=2)) \
                                      .filter(last_payment__created__lt=utc_now() - timedelta(days=1))
    email_interface = get_email_service()

    for sms_balance in one_day_objects:
        email_interface.send_tpl(sms_balance.company.primary_contact.contact,
                                 sms_balance.company,
                                 tpl_name='sms-payment-reminder-24')

    for sms_balance in two_days_objects:
        email_interface.send_tpl(sms_balance.company.primary_contact.contact,
                                 sms_balance.company,
                                 tpl_name='sms-payment-reminder-48')


@shared_task
def charge_for_new_amount():
    """"adjusts stripe plan to actual worker count"""
    company_list = Company.objects.filter(type=Company.COMPANY_TYPES.master) \
                                  .filter(subscriptions__active=True)

    for company in company_list:
        country_code = company.get_country_code()
        stripe.api_key = sca.get_stripe_key(country_code)
        subscription = company.active_subscription
        amount = subscription.get_total_subscription_amount()
        if not subscription.price == amount:
            plan_type = subscription.subscription_type.type
            plan_name = 'R3sourcer {} plan for {} workers'.format(plan_type,
                                                                  subscription.worker_count)
            plan = stripe.Plan.create(
                product=settings.STRIPE_PRODUCT_ID,
                nickname=plan_name,
                interval=STRIPE_INTERVALS[plan_type],
                currency=company.currency,
                amount=round((int(amount) * 100) / 1.1),
                )
            subscription_stripe = stripe.Subscription.retrieve(subscription.subscription_id)
            stripe.Subscription.modify(subscription_stripe.id,
                                       cancel_at_period_end=False,
                                       proration_behavior='none',
                                       items=[{
                                           'id': subscription_stripe['items']['data'][0].id,
                                           'plan': plan.id,
                                           }]
                                       )
            subscription.price = amount
            subscription.save()
        else:
            pass
