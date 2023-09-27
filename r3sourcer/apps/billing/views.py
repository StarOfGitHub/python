import stripe
from itertools import chain

from datetime import datetime

from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _
from rest_framework import status, filters
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView, ListCreateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from stripe.error import InvalidRequestError

from r3sourcer.apps.billing.models import Subscription, Payment, Discount, SMSBalance, SubscriptionType
from r3sourcer.apps.billing.serializers import SubscriptionSerializer, PaymentSerializer, \
    CompanySerializer, DiscountSerializer, SmsBalanceSerializer, SmsAutoChargeSerializer, SubscriptionTypeSerializer
from r3sourcer.apps.billing.tasks import charge_for_sms
from r3sourcer.apps.billing import STRIPE_INTERVALS
from r3sourcer.apps.core.api.serializers import VATSerializer
from r3sourcer.apps.core.models import Company, Contact, VAT
from r3sourcer.apps.company_settings.models import GlobalPermission
from r3sourcer.celeryapp import app
from r3sourcer.apps.billing.models import StripeCountryAccount as sca
from r3sourcer.apps.core.utils.companies import get_site_master_company


class SubscriptionCreateView(APIView):
    def post(self, *args, **kwargs):
        company = get_site_master_company()

        if not company.stripe_customer:
            data = {'error': 'User did not provide payment information.'}
            return Response(status=status.HTTP_400_BAD_REQUEST, data=data)

        company_address = company.get_hq_address()
        if company_address:
            country_code = company_address.address.country.code2
        else:
            country_code = 'EE'

        stripe.api_key = sca.get_stripe_key(country_code)

        vat_qs = VAT.get_vat(country_code)

        vat_object = vat_qs.first()
        plan_type = self.request.data['type']
        sub_type = SubscriptionType.objects.get(type=plan_type)
        worker_count = self.request.data['worker_count']
        plan_name = 'R3sourcer {} plan for {} workers'.format(plan_type, worker_count)
        product = stripe.Product.create(name=plan_name, type='service')
        try:
            plan = stripe.Plan.create(
                product=product.id,
                nickname=plan_name,
                interval=STRIPE_INTERVALS[plan_type],
                currency=company.currency,
                amount=round((int(self.request.data['price']) * 100)),
            )
            subscription = stripe.Subscription.create(
                customer=company.stripe_customer,
                items=[{"plan": plan.id}],
                default_tax_rates=[vat_object.stripe_id],
                cancel_at_period_end=False,
            )
        except InvalidRequestError as e:
            data = {'error': e.user_message}
            return Response(data, status=status.HTTP_400_BAD_REQUEST)
        current_period_start = None
        current_period_end = None

        if isinstance(subscription.current_period_start, int):
            # TODO change it to fromtimestamp if necessary
            current_period_start = datetime.utcfromtimestamp(subscription.current_period_start)
            current_period_end = datetime.utcfromtimestamp(subscription.current_period_end)

        sub = Subscription.objects.create(company=company,
                                          name=plan_name,
                                          subscription_type=sub_type,
                                          worker_count=worker_count,
                                          price=self.request.data.get('price', None),
                                          plan_id=plan.id,
                                          subscription_id=subscription.id,
                                          current_period_start=current_period_start,
                                          current_period_end=current_period_end,
                                          status=subscription.status)
        serializer = SubscriptionSerializer(sub)
        customer = company.stripe_customer
        invoices = stripe.Invoice.list(customer=customer)['data']
        for invoice in invoices:
            if invoice['paid'] is False and invoice['subscription'] is not None and invoice['subscription'] == \
                    subscription.id:
                sub.active = False
                sub.status = Subscription.SUBSCRIPTION_STATUSES.unpaid
                sub.save()

            if not Payment.objects.filter(stripe_id=invoice['id']).exists():
                Payment.objects.create(
                    company=company,
                    type=Payment.PAYMENT_TYPES.subscription,
                    amount=int(self.request.data['price']),
                    stripe_id=invoice['id'],
                    invoice_url=invoice['invoice_pdf'],
                    status=invoice['status']
                )
        # get full access to a site
        user = self.request.user
        # set permissions
        # revoke task with cancel subscription with request.user
        try:
            for task in chain.from_iterable(app.control.inspect().scheduled().values()):
                if str(eval(task['request']['args'])[0]) == str(user.id):
                    app.control.revoke(task['request']['id'], terminate=True, signal='SIGKILL')
        except:
            pass
        permission_list = GlobalPermission.objects.all()
        user.user_permissions.add(*permission_list)
        user.save()
        data = {
            "subscription": serializer.data
        }
        return Response(data, status=status.HTTP_201_CREATED)


class SubscriptionListView(ListAPIView):
    def get(self, *args, **kwargs):
        company = get_site_master_company()
        subscriptions = Subscription.objects.filter(company=company).order_by('-created')
        serializer = SubscriptionSerializer(subscriptions, many=True)
        data = {
            "subscriptions": serializer.data
        }
        return Response(data)


class StripeCustomerView(APIView):
    def post(self, *args, **kwargs):
        company = get_site_master_company()
        description = '{}'.format(company.name)
        email = ''
        address = None
        country_code = 'EE'
        hq_addr = company.get_hq_address()
        if hq_addr:
            country_code = company.get_hq_address().address.country.code2
            address = hq_addr.address.get_address_for_stripe(company.name)
        stripe.api_key = sca.get_stripe_key(country_code)
        if company.billing_email:
            email = company.billing_email
        elif company.primary_contact:
            email = company.primary_contact.contact.email

        customer = stripe.Customer.create(
            description=description,
            source=self.request.data.get('source'),
            email=email,
            address=address,
            name=company.name or str(company.primary_contact),
        )
        company.stripe_customer = customer.id
        company.card_number = self.request.data.get('last4')
        company.save()
        return Response(status=status.HTTP_201_CREATED)

    def put(self, *args, **kwargs):
        company = get_site_master_company()
        country_code = 'EE'
        if not company.stripe_customer:
            raise ValidationError({"error": _("Company has no stripe account")})
        if company.get_hq_address():
            country_code = company.get_hq_address().address.country.code2
        stripe.api_key = sca.get_stripe_key(country_code)
        stripe.Customer.modify(
            company.stripe_customer,
            source=self.request.data.get('source'),
        )
        company.card_number = self.request.data.get('last4')
        company.save()
        return Response(status=status.HTTP_200_OK)

    def delete(self, *args, **kwargs):
        company = get_site_master_company()
        company.stripe_customer = None
        company.card_number = None
        company.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SubscriptionStatusView(APIView):
    def get(self, *args, **kwargs):
        status = 'not_created'
        company = get_site_master_company()
        subscription = company.subscriptions.filter(active=True).first()

        if subscription:
            status = subscription.status

        data = {
            'status': status
        }
        return Response(data)


class PaymentListView(ListAPIView):
    serializer_class = PaymentSerializer
    filter_backends = (filters.OrderingFilter,)
    ordering_fields = ['created', 'type', 'amount', 'status', 'invoice_url']

    def get_queryset(self):
        company = get_site_master_company()
        return Payment.objects.filter(company=company).order_by('-created')


class CheckPaymentInformationView(APIView):
    def get(self, *args, **kwargs):
        company = get_site_master_company()
        return Response({
            "payment_information_submited": bool(company.stripe_customer),
            "card_number_last4": company.card_number if bool(company.stripe_customer) else None,
        })


class SubscriptionCancelView(APIView):
    def get(self, *args, **kwargs):
        company = get_site_master_company()
        subscription = Subscription.objects.get(company=company, active=True)
        subscription.deactivate()
        subscription.active = False
        subscription.status = 'canceled'
        subscription.save()
        return Response()


class CompanyListView(ListAPIView):
    queryset = Company.objects.filter(subscriptions__isnull=False)
    serializer_class = CompanySerializer


class DiscountView(ListCreateAPIView):
    queryset = Discount.objects.all()
    serializer_class = DiscountSerializer


class DisableSMSCompanyView(APIView):
    def get(self, *args, **kwargs):
        company = Company.objects.get(id=kwargs['id'])
        company.sms_enabled = False
        company.save()
        return Response()


class DisableSMSContactView(APIView):
    def get(self, *args, **kwargs):
        contact = Contact.objects.get(id=kwargs['id'])
        contact.sms_enabled = False
        contact.save()
        return Response()


class TwilioFundCreateView(APIView):
    def post(self, *args, **kwargs):
        company = get_site_master_company()

        if not company.stripe_customer:
            data = {'error': 'User didnt provide payment information.'}
            return Response(status=status.HTTP_400_BAD_REQUEST, data=data)

        amount = self.request.data.get('amount')

        sms_balance, created = SMSBalance.objects.get_or_create(company=company)
        charge_for_sms.delay(amount, sms_balance.id)

        serializer = SmsBalanceSerializer(sms_balance)

        data = {
            "sms_balance": serializer.data
        }
        return Response(data, status=status.HTTP_201_CREATED)


class TwilioAutoChargeView(APIView):
    def get(self, *args, **kwargs):
        company = get_site_master_company()
        try:
            sms_balance = SMSBalance.objects.get(company=company)
        except SMSBalance.DoesNotExist:
            return Response(status=status.HTTP_200_OK)

        serializer = SmsAutoChargeSerializer(sms_balance)
        data = {
            "sms_balance": serializer.data
            }
        return Response(data, status=status.HTTP_200_OK)

    def post(self, *args, **kwargs):
        company = get_site_master_company()

        if not company.stripe_customer:
            data = {'error': 'User didnt provide payment information.'}
            return Response(status=status.HTTP_400_BAD_REQUEST, data=data)

        sms_balance = SMSBalance.objects.get(company=company)

        if 'top_up_amount' not in self.request.data or 'top_up_limit' not in self.request.data:
            data = {'error': 'Must provide top_up_amount and top_up_limit'}
            return Response(status=status.HTTP_400_BAD_REQUEST, data=data)
        sms_balance.top_up_amount = self.request.data.get('top_up_amount')
        sms_balance.top_up_limit = self.request.data.get('top_up_limit')
        sms_balance.auto_charge = self.request.data.get('auto_charge', False)
        sms_balance.save()

        serializer = SmsAutoChargeSerializer(sms_balance)

        data = {
            "sms_balance": serializer.data
            }
        return Response(data, status=status.HTTP_201_CREATED)


class SubscriptionTypeView(APIView):
    def get(self, *args, **kwargs):
        company = get_site_master_company()
        company_address = company.get_hq_address()
        if not company_address:
            company_address = company.company_addresses.first()
        if not company_address:
            raise NotFound(detail='Company address not found')

        country_code = company_address.address.country.code2 or 'EE'
        vats = VAT.get_vat(country_code)
        vat_serializer = VATSerializer(vats, many=True)
        subscription_types = SubscriptionType.objects.all()
        serializer = SubscriptionTypeSerializer(subscription_types, many=True)
        data = {
            "subscription_types": serializer.data,
            "vats": vat_serializer.data,
            }
        return Response(data, status=status.HTTP_200_OK)


class StripeCountryAccountView(APIView):
    def get(self, *args, **kwargs):
        company = get_site_master_company()
        hq_addr = company.get_hq_address()
        country_code = 'EE'
        if hq_addr:
            country_code = hq_addr.address.country.code2
        public_key = sca.get_stripe_pub(country_code)
        data = {
            "public_key": public_key
            }
        return Response(data, status=status.HTTP_200_OK)
