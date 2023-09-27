from rest_framework import serializers

from r3sourcer.apps.billing.models import Subscription, Payment, Discount, SMSBalance, SubscriptionType
from r3sourcer.apps.core.models import Company


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = ('company', 'name', 'subscription_type', 'price', 'worker_count', 'created', 'active', 'id', 'current_period_start',
                  'current_period_end', 'last_time_billed')


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ('type', 'created', 'amount', 'status', 'invoice_url')


class CompanySerializer(serializers.ModelSerializer):
    subscription = serializers.SerializerMethodField()
    sms_balance = serializers.IntegerField(source='sms_balance.balance')

    class Meta:
        model = Company
        fields = ('name', 'short_name', 'subscription', 'sms_balance')

    def get_subscription(self, company):
        subscription = company.subscriptions.filter(active=True).first()
        serializer = SubscriptionSerializer(instance=subscription)
        return serializer.data


class DiscountCompanySerializer(serializers.ModelSerializer):
    id = serializers.CharField()

    class Meta:
        model = Company
        fields = ('id', '__str__')


class DiscountSerializer(serializers.ModelSerializer):
    company = DiscountCompanySerializer()

    class Meta:
        model = Discount
        fields = ('id', 'company', 'payment_type', 'percent_off', 'amount_off', 'active', 'duration', 'duration_in_months')

    def create(self, validated_data):
        company_data = validated_data.pop('company')
        company = Company.objects.get(id=company_data['id'])
        validated_data.update({'company': company})
        return super(DiscountSerializer, self).create(validated_data)


class SmsBalanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SMSBalance
        fields = ('id', 'company',)


class SmsAutoChargeSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)

    class Meta:
        model = SMSBalance
        fields = ('id', 'company', 'company_name', 'balance', 'top_up_amount', 'top_up_limit', 'last_payment', 'segment_cost', 'auto_charge')


class SubscriptionTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionType
        fields = '__all__'
