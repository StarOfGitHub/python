import datetime
import mock

import stripe

from django.utils import timezone
from stripe.error import InvalidRequestError

from r3sourcer.apps.billing.tasks import charge_for_extra_workers, charge_for_sms, fetch_payments, sync_subscriptions
from r3sourcer.apps.billing.models import SMSBalance, Payment, Subscription
from r3sourcer.apps.candidate.models import CandidateContact
from r3sourcer.apps.core.models import User, Company
from r3sourcer.apps.hr.models import JobOffer, TimeSheet


class TestActiveWorkers:
    def test_active_workers_zero(self, client, user, company, relationship):
        assert company.active_workers() == 0

    def test_active_workers(self, client, user, company, relationship, primary_contact, shift):
        user2 = User.objects.create_user(
            email='test2@test.tt', phone_mobile='+12345678902',
            password='test1234'
        )
        contact2 = user2.contact
        cc1 = CandidateContact.objects.create(contact=primary_contact)
        cc2 = CandidateContact.objects.create(contact=contact2)
        job_offer1 = JobOffer.objects.create(
            candidate_contact=cc1,
            shift=shift
        )
        job_offer2 = JobOffer.objects.create(
            candidate_contact=cc2,
            shift=shift
        )
        TimeSheet.objects.create(
            job_offer=job_offer1,
            shift_started_at=timezone.now()
        )
        TimeSheet.objects.create(
            job_offer=job_offer2,
            shift_started_at=timezone.now()
        )
        assert company.active_workers() == 2


class TestChargeForExtraWorkers:
    @mock.patch('r3sourcer.apps.core.models.Company.active_workers')
    def test_no_extra_workers(self, active_workers, client, user, company, relationship, contact,
                              subscription_type_monthly, shift):
        active_workers.return_value = 100
        Subscription.objects.create(
            company=company,
            name='subscription',
            subscription_type=subscription_type_monthly,
            price=500,
            worker_count=100,
        )
        active_workers.return_value = 100
        charge_for_extra_workers()

        assert Payment.objects.count() == 0

    @mock.patch('r3sourcer.apps.core.models.Company.active_workers')
    def test_extra_workers(self, active_workers, client, user, company, relationship,
                           subscription_type_monthly):
        active_workers.return_value = 110
        company.stripe_customer = 'cus_IcPJnMwIAifS1J'
        company.save()
        Subscription.objects.create(
            company=company,
            name='subscription',
            subscription_type=subscription_type_monthly,
            price=500,
            worker_count=100,
            active=True,
            current_period_end=datetime.date.today()
        )
        charge_for_extra_workers()

        assert Payment.objects.count() == 1
        assert Payment.objects.first().amount == 130

    @mock.patch('r3sourcer.apps.core.models.Company.active_workers')
    def test_extra_workers_annual_subscription(self, active_workers, client, user, company,
                                               relationship, subscription_type_annual):
        active_workers.return_value = 110
        company.stripe_customer = 'cus_IcPJnMwIAifS1J'
        company.save()
        Subscription.objects.create(
            company=company,
            name='subscription',
            subscription_type=subscription_type_annual,
            price=500,
            worker_count=100,
            active=True,
            current_period_end=datetime.date.today()
        )
        charge_for_extra_workers()

        assert Payment.objects.count() == 1
        assert Payment.objects.first().amount == 100


class TestChargeForSMS:
    @mock.patch.object(stripe.InvoiceItem, 'create')
    @mock.patch.object(stripe.Invoice, 'create')
    @mock.patch.object(Subscription, 'deactivate')
    def test_charge(self, mocked_invoice, client, user, company, relationship):#, company_address):
        mocked_value = {'id': 'stripe_id'}
        mocked_invoice.return_value = mocked_value
        initial_payment_count = Payment.objects.count()
        charge_for_sms(100, company.sms_balance.id)

        assert initial_payment_count + 1 == Payment.objects.count()


class TestFetchPayments:
    @mock.patch.object(stripe.Invoice, 'retrieve')
    @mock.patch.object(stripe.Invoice, 'list')
    def test_fetch_payments(self, mocked_invoice_retrieve, mocked_invoice_list, client, user, company):
        initial_balance = company.sms_balance.balance
        mocked_invoice_retrieve.return_value = {'data': list()}
        mocked_invoice_list.return_value = {'paid': True}
        payment = Payment.objects.create(
            company=company,
            type=Payment.PAYMENT_TYPES.sms,
            amount=100,
            status=Payment.PAYMENT_STATUSES.not_paid,
            stripe_id='stripeid',
            invoice_url='invoice_url'
        )
        company.stripe_customer = 'stripe_customer'
        company.sms_enabled = False
        company.sms_balance.last_payment = payment
        company.sms_balance.save()
        company.save()
        fetch_payments()

        assert Payment.objects.get(id=payment.id).status == 'paid'
        assert SMSBalance.objects.get(id=company.sms_balance.id).balance == initial_balance + payment.amount
        assert Company.objects.get(id=company.id).sms_enabled

    @mock.patch.object(stripe.Invoice, 'retrieve')
    @mock.patch.object(stripe.Invoice, 'list')
    def test_fetch_removed_payments(self, mocked_invoice_retrieve, mocked_invoice_list, client, user, company):
        mocked_invoice_retrieve.return_value = InvalidRequestError(
            http_status=404,
            code='resource_missing',
            message='error',
            param=()
        )
        mocked_invoice_list.return_value = {'paid': True}
        payment = Payment.objects.create(
            company=company,
            type=Payment.PAYMENT_TYPES.sms,
            amount=100,
            status=Payment.PAYMENT_STATUSES.not_paid,
            stripe_id='stripeid'
        )
        company.stripe_customer = 'stripe_customer'
        company.sms_enabled = False
        company.sms_balance.last_payment = payment
        company.sms_balance.save()
        company.save()
        fetch_payments()

        assert Payment.objects.filter(id=payment.id).count() == 0


class TestSubscriptions:

    def test_sync_subscriptions_active(self, subscription):
        assert subscription.active is True
        sync_subscriptions()
        subscription.refresh_from_db()
        assert subscription.status == "canceled"
        assert subscription.active is False

    def test_sync_subscriptions_canceled(self, canceled_subscription):
        assert canceled_subscription.active is False
        sync_subscriptions()
        canceled_subscription.refresh_from_db()
        assert canceled_subscription.status == "active"
        assert canceled_subscription.active is True
