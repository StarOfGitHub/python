import datetime
import mock
from decimal import Decimal

import stripe
from stripe.error import CardError

from r3sourcer.apps.billing.models import Discount, Subscription, Payment, SubscriptionType
from r3sourcer.apps.billing.tasks import charge_for_extra_workers, charge_for_sms
from r3sourcer.apps.core.tasks import cancel_subscription_access
from r3sourcer.helpers.datetimes import utc_now


class TestSubscription:

    @mock.patch.object(stripe.Subscription, 'retrieve')
    def test_get_stripe_subscription(self, mocked_retrieve, subscription):
        """expect call retrieve to get Stripe subscription"""
        subscription.get_stripe_subscription()
        mocked_retrieve.assert_called_once_with(subscription.subscription_id)

    @mock.patch.object(stripe.Subscription, 'retrieve')
    def test_sync_status_to_incomplete_and_activate(self, mocked_retrieve, canceled_subscription):
        """expect call retrieve to get Stripe subscription and then change status to incomplete and activate"""
        assert canceled_subscription.status == 'canceled'

        stripe_subscription = mock.Mock()
        stripe_subscription.status = 'incomplete'
        mocked_retrieve.return_value = stripe_subscription

        canceled_subscription.sync_status()

        mocked_retrieve.assert_called_once_with(canceled_subscription.subscription_id)
        assert canceled_subscription.status == 'incomplete'
        assert canceled_subscription.active is True

    @mock.patch.object(stripe.Subscription, 'retrieve')
    def test_sync_status_to_active_and_activate(self, mocked_retrieve, canceled_subscription):
        """expect call retrieve to get Stripe subscription and then change status to active and activate"""
        assert canceled_subscription.status == 'canceled'

        stripe_subscription = mock.Mock()
        stripe_subscription.status = 'active'
        mocked_retrieve.return_value = stripe_subscription

        canceled_subscription.sync_status()

        mocked_retrieve.assert_called_once_with(canceled_subscription.subscription_id)
        assert canceled_subscription.status == 'active'
        assert canceled_subscription.active is True

    @mock.patch.object(stripe.Subscription, 'retrieve')
    def test_sync_status_to_trialing_and_activate(self, mocked_retrieve, canceled_subscription):
        """expect call retrieve to get Stripe subscription and then change status to trialing and activate"""
        assert canceled_subscription.status == 'canceled'

        stripe_subscription = mock.Mock()
        stripe_subscription.status = 'trialing'
        mocked_retrieve.return_value = stripe_subscription

        canceled_subscription.sync_status()

        mocked_retrieve.assert_called_once_with(canceled_subscription.subscription_id)
        assert canceled_subscription.status == 'trialing'
        assert canceled_subscription.active is True

    @mock.patch.object(stripe.Subscription, 'retrieve')
    def test_sync_status_to_not_allowed_and_deactivate(self, mocked_retrieve, subscription):
        """expect call retrieve to get Stripe subscription and then change status to past_due and deactivate"""
        assert subscription.status == 'active'
        assert subscription.active is True

        stripe_subscription = mock.Mock()
        stripe_subscription.status = 'past_due'
        mocked_retrieve.return_value = stripe_subscription

        subscription.sync_status()

        mocked_retrieve.assert_called_once_with(subscription.subscription_id)
        assert subscription.status == 'past_due'
        assert subscription.active is False

    @mock.patch.object(stripe.Subscription, 'retrieve')
    def test_sync_status_with_stripe_subscription(self, mocked_retrieve, subscription):
        """expect call retrieve to get Stripe subscription and then change status to canceled and deactivate"""
        assert subscription.status == 'active'
        assert subscription.active is True

        stripe_subscription = mock.Mock()
        stripe_subscription.status = 'canceled'

        subscription.sync_status(stripe_subscription=stripe_subscription)

        mocked_retrieve.assert_not_called()
        assert subscription.status == 'canceled'
        assert subscription.active is False

    def test_update_user_permissions_for_allowed_status(self):
        pass

    def test_update_user_permissions_for_not_allowed_status(self):
        pass

    @mock.patch.object(stripe.Subscription, 'retrieve')
    def test_sync_periods_with_stripe_subscription(self, mocked_retrieve, subscription):
        """expect not to call retrieve and change current_period dates"""
        stripe_subscription = mock.Mock()
        stripe_subscription.current_period_start = 1632375374
        stripe_subscription.current_period_end = 1634967374

        assert subscription.current_period_start is None
        assert subscription.current_period_end is None

        subscription.sync_periods(stripe_subscription)

        mocked_retrieve.assert_not_called()
        assert subscription.current_period_start is not None
        assert subscription.current_period_end is not None

    @mock.patch.object(stripe.Subscription, 'retrieve')
    def test_sync_periods_for_active_subscription(self, mocked_retrieve, subscription):
        """expect call retrieve to get Stripe subscription and then change current_period dates"""
        stripe_subscription = mock.Mock()
        stripe_subscription.current_period_start = 1632375374
        stripe_subscription.current_period_end = 1634967374
        mocked_retrieve.return_value = stripe_subscription

        assert subscription.current_period_start is None
        assert subscription.current_period_end is None

        subscription.sync_periods()

        mocked_retrieve.assert_called_once_with(subscription.subscription_id)
        assert subscription.current_period_start is not None
        assert subscription.current_period_end is not None

    @mock.patch.object(Subscription, 'save')
    @mock.patch.object(stripe.Subscription, 'retrieve')
    def test_sync_periods_for_inactive_subscription(self, mocked_retrieve, mock_save, canceled_subscription):
        """expect to not call retrieve or save"""
        canceled_subscription.sync_periods()

        mocked_retrieve.assert_not_called()
        mock_save.assert_not_called()

    @mock.patch.object(stripe.Subscription, 'retrieve')
    @mock.patch.object(stripe.Subscription, 'modify')
    @mock.patch.object(cancel_subscription_access, 'apply_async')
    def test_deactivate(self, mocked_apply_async, mocked_modify, mocked_retrieve, subscription):
        """expect call retrieve to get Stripe subscription and then modify without cancel_subscription_access"""
        stripe_subscription = mock.Mock()
        mocked_retrieve.return_value = stripe_subscription

        subscription.deactivate()

        mocked_retrieve.assert_called_once_with(subscription.subscription_id)
        stripe_subscription.modify.assert_called_once_with(subscription.subscription_id, cancel_at_period_end=True, prorate=False)
        mocked_apply_async.assert_not_called()

    @mock.patch.object(stripe.Subscription, 'retrieve')
    @mock.patch.object(stripe.Subscription, 'modify')
    @mock.patch.object(cancel_subscription_access, 'apply_async')
    def test_deactivate_with_stripe_subscription(self, mocked_apply_async, mocked_modify, mocked_retrieve, subscription):
        """expect call retrieve to get Stripe subscription and then modify without cancel_subscription_access"""
        stripe_subscription = mock.Mock()
        mocked_retrieve.return_value = stripe_subscription

        subscription.deactivate(stripe_subscription=stripe_subscription)

        mocked_retrieve.assert_not_called()
        stripe_subscription.modify.assert_called_once_with(subscription.subscription_id, cancel_at_period_end=True, prorate=False)
        mocked_apply_async.assert_not_called()

    def test_save_status(self, subscription):
        """change a status of subscription and expect it saves"""
        assert subscription.status == 'active'

        subscription.status = 'canceled'
        subscription.save(update_fields=['status'])

        assert subscription.status == 'canceled'

    @mock.patch.object(stripe.Subscription, 'retrieve')
    @mock.patch.object(stripe.Subscription, 'modify')
    def test_save_another_active_subscription(self, mocked_modify, mocked_retrieve, canceled_subscription, subscription):
        """make a canceled subscription active and expect that 'old' subscription become inactive"""
        assert subscription.status == 'active'
        assert subscription.active is True
        assert canceled_subscription.status == 'canceled'

        stripe_subscription = mock.Mock()
        mocked_retrieve.return_value = stripe_subscription

        canceled_subscription.status = 'active'
        canceled_subscription.active = True
        canceled_subscription.save(update_fields=['status', 'active'])
        mocked_retrieve.assert_called_once()
        stripe_subscription.modify.assert_called_once_with(subscription.subscription_id, cancel_at_period_end=True, prorate=False)

        subscription.refresh_from_db()
        assert subscription.status == 'canceled'
        assert subscription.active is False
        assert canceled_subscription.status == 'active'
        assert canceled_subscription.active is True


class TestSMSBalance:

    def test_substract_sms_cost(self, client, user, company, relationship):
        sms_balance = company.sms_balance
        sms_balance.balance = 100
        sms_balance.save()
        sms_balance.substract_sms_cost(3)

        assert sms_balance.balance == Decimal('99.76')

    def test_send_low_balance_notification(self, client, user, company, relationship, low_balance_limit):
        sms_balance = company.sms_balance
        sms_balance.balance = low_balance_limit.low_balance_limit - 1
        sms_balance.save()

        assert company.sms_balance.low_balance_sent is True

    def test_send_low_balance_notification_twice(self, client, user, company, relationship, low_balance_limit):
        sms_balance = company.sms_balance
        sms_balance.balance = low_balance_limit.low_balance_limit - 1
        sms_balance.save()

        assert company.sms_balance.low_balance_sent is True

        sms_balance.balance = low_balance_limit.low_balance_limit + 10
        sms_balance.save()

        assert company.sms_balance.low_balance_sent is False

    def test_send_ran_out_notification(self, client, user, company, relationship, ran_out_balance_limit):
        sms_balance = company.sms_balance
        sms_balance.balance = ran_out_balance_limit.low_balance_limit - 1
        sms_balance.save()

        assert company.sms_balance.ran_out_balance_sent is True

    def test_send_ran_out_notification_twice(self, client, user, company, relationship, ran_out_balance_limit):
        sms_balance = company.sms_balance
        sms_balance.balance = ran_out_balance_limit.low_balance_limit - 1
        sms_balance.save()

        assert company.sms_balance.ran_out_balance_sent is True

        sms_balance.balance = ran_out_balance_limit.low_balance_limit + 10
        sms_balance.save()

        assert company.sms_balance.ran_out_balance_sent is False

    def test_send_low_balance_general_company(self, client, user, regular_company, relationship,
                                                           low_balance_limit):
        sms_balance = regular_company.sms_balance
        sms_balance.balance = low_balance_limit.low_balance_limit - 1
        sms_balance.save()

        assert regular_company.sms_balance.low_balance_sent is False

    @mock.patch.object(stripe.InvoiceItem, 'create')
    @mock.patch.object(stripe.Invoice, 'create')
    def test_charge_for_sms_without_last_payment_carderror(self, mocked_invoice, mocked_invoice_item, client, user,
                                                           company, company_address, relationship, vat):
        """Topping up balance with 100 and assume balance would be 90 with stripe rate=0.1"""
        sms_balance = company.sms_balance
        stripe_invoice_dict = {
            'id': 'stripe_id',
            'invoice_pdf': 'invoice_pdf',
            'status': 'paid'
        }
        stripe_invoice = mock.MagicMock()
        stripe_invoice.pay = mock.Mock(side_effect=CardError('foo', '', 1))
        # override getitem so we can mock stripe_invoice['id']
        stripe_invoice.__getitem__.side_effect = stripe_invoice_dict.__getitem__
        mocked_invoice.return_value = stripe_invoice

        sms_balance.charge_for_sms(100)

        # mocked_invoice.pay.assert_called_once()
        assert sms_balance.last_payment is not None
        assert sms_balance.balance == 0

    @mock.patch.object(stripe.InvoiceItem, 'create')
    @mock.patch.object(stripe.Invoice, 'create')
    def test_charge_for_sms_without_last_payment_successfully(self, mocked_invoice, mocked_invoice_item, client, user,
                                                           company, company_address, relationship, vat):
        """Topping up balance with 100 and assume balance would be 100"""
        sms_balance = company.sms_balance
        stripe_invoice_dict = {
            'id': 'stripe_id',
            'invoice_pdf': 'invoice_pdf',
            'status': 'paid'
        }
        stripe_invoice = mock.MagicMock()
        # override getitem so we can mock stripe_invoice['id']
        stripe_invoice.__getitem__.side_effect = stripe_invoice_dict.__getitem__
        mocked_invoice.return_value = stripe_invoice

        sms_balance.charge_for_sms(100)

        stripe_invoice.pay.assert_called_once()
        assert sms_balance.last_payment is not None
        assert sms_balance.balance == 100

    @mock.patch.object(stripe.InvoiceItem, 'create')
    @mock.patch.object(stripe.Invoice, 'create')
    def test_charge_for_sms_with_paid_last_payment(self, mocked_invoice, mocked_invoice_item, client, user, company,
                                                   company_address, relationship, vat):
        """Topping up balance with 100 and assume balance would be 100"""
        sms_balance = company.sms_balance
        last_payment = Payment.objects.create(
            company=company,
            amount=100,
            type=Payment.PAYMENT_TYPES.sms,
            status=Payment.PAYMENT_STATUSES.paid,
            stripe_id='stripe_id',
            created=utc_now()-datetime.timedelta(minutes=1)
        )
        sms_balance.last_payment = last_payment
        sms_balance.save()

        stripe_invoice_dict = {
            'id': 'stripe_id',
            'invoice_pdf': 'invoice_pdf',
            'status': 'paid'
        }
        stripe_invoice = mock.MagicMock()
        # override getitem so we can mock stripe_invoice['id']
        stripe_invoice.__getitem__.side_effect = stripe_invoice_dict.__getitem__
        mocked_invoice.return_value = stripe_invoice

        sms_balance.charge_for_sms(100)

        stripe_invoice.pay.assert_called_once()
        assert sms_balance.last_payment.id != last_payment.id
        assert sms_balance.balance == 100

    @mock.patch.object(stripe.InvoiceItem, 'create')
    @mock.patch.object(stripe.Invoice, 'create')
    def test_charge_for_sms_with_not_paid_last_payment(self, mocked_invoice, mocked_invoice_item, client,
                                                       user, company, company_address, relationship, vat):
        """Topping up balance with 100 and assume balance would be 100 without changes in last Payment"""
        sms_balance = company.sms_balance
        last_payment = Payment.objects.create(
            company=company,
            amount=100,
            type=Payment.PAYMENT_TYPES.sms,
            status=Payment.PAYMENT_STATUSES.not_paid,
            stripe_id='stripe_id',
            created=utc_now()-datetime.timedelta(minutes=1)
        )
        sms_balance.last_payment = last_payment
        sms_balance.save()

        stripe_invoice_dict = {
            'id': 'stripe_id',
            'invoice_pdf': 'invoice_pdf',
            'status': 'paid'
        }
        stripe_invoice = mock.MagicMock()
        # override getitem so we can mock stripe_invoice['id']
        stripe_invoice.__getitem__.side_effect = stripe_invoice_dict.__getitem__
        mocked_invoice.return_value = stripe_invoice

        sms_balance.charge_for_sms(100)

        stripe_invoice.pay.assert_called_once()
        assert sms_balance.last_payment.id != last_payment.id
        assert sms_balance.balance == 100


class TestDiscount:

    def test_apply_discount_percent_off(self, client, user, company):
        discount = Discount.objects.create(
            company=company,
            payment_type='sms',
            percent_off=25,
            duration='once',
        )

        assert discount.apply_discount(1000) == 750

    def test_apply_discount_amount_off(self, client, user, company):
        discount = Discount.objects.create(
            company=company,
            payment_type='sms',
            amount_off=25,
            duration='once',
        )

        assert discount.apply_discount(1000) == 975

    @mock.patch.object(stripe.InvoiceItem, 'create')
    @mock.patch.object(stripe.Invoice, 'create')
    @mock.patch.object(Subscription, 'deactivate')
    def test_apply_discount_sms(self, mocked_subscription, mocked_invoice, mocked_invoice_item, client, user, company,
                                relationship, company_address):
        Discount.objects.create(
            company=company,
            payment_type='sms',
            amount_off=25,
            duration='once',
        )
        stripe_invoice_dict = {
            'id': 'stripe_id',
            'invoice_pdf': 'invoice_pdf',
            'status': 'paid'
        }
        stripe_invoice = mock.MagicMock()
        # override getitem so we can mock stripe_invoice['id']
        stripe_invoice.__getitem__.side_effect = stripe_invoice_dict.__getitem__
        mocked_invoice.return_value = stripe_invoice
        charge_for_sms(100, company.sms_balance.id)

        stripe_invoice.pay.assert_called_once()
        assert Payment.objects.first().amount == 75

    @mock.patch.object(stripe.Subscription, 'modify')
    @mock.patch.object(stripe.Subscription, 'retrieve')
    @mock.patch.object(stripe.Plan, 'create')
    @mock.patch.object(stripe.InvoiceItem, 'create')
    @mock.patch.object(stripe.Invoice, 'create')
    @mock.patch('r3sourcer.apps.core.models.Company.active_workers')
    def test_apply_discount_extra_workers(self, active_workers, mocked_invoice, mocked_invoice_item, mocked_plan_create,
                                          mocked_subscription_retrieve, mocked_subscription_modify, client, user,
                                          company, company_address, vat, subscription_type_monthly):
        Discount.objects.create(
            company=company,
            payment_type='extra_workers',
            amount_off=30,
            duration='once',
        )
        stripe_invoice_dict = {
            'id': 'stripe_id',
            'invoice_pdf': 'invoice_pdf',
            'status': 'paid'
        }
        stripe_invoice = mock.MagicMock()
        # override getitem so we can mock stripe_invoice['id']
        stripe_invoice.__getitem__.side_effect = stripe_invoice_dict.__getitem__
        mocked_invoice.return_value = stripe_invoice
        active_workers.return_value = 110
        company.stripe_customer = 'cus_CnGRCuSr6Fo0Uv'
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

        stripe_plan = mock.Mock()
        stripe_plan.id = 'plan_id'
        mocked_plan_create.return_value = stripe_plan

        some_mock = mock.Mock()
        some_mock.id = 'id'
        stripe_subscription_dict = {
            'items': {
                'data': [some_mock]
            }
        }
        stripe_subscription = mock.MagicMock()
        stripe_subscription.id = 'subscription_id'
        # override getitem so we can mock stripe_invoice['id']
        stripe_subscription.__getitem__.side_effect = stripe_subscription_dict.__getitem__
        mocked_subscription_retrieve.return_value = stripe_subscription

        charge_for_extra_workers()

        mocked_subscription_modify.assert_called_once()
        assert Payment.objects.first().amount == 100

    def test_duration_once(self, client, user, company):
        discount = Discount.objects.create(
            company=company,
            payment_type='sms',
            amount_off=25,
            duration='once',
        )
        discount.apply_discount(1000)

        assert not discount.active
