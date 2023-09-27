from django.contrib import admin

from . import models


class SMSBalanceAdmin(admin.ModelAdmin):
    list_display = ('company', 'balance',)
    search_fields = ('company__name',)
    readonly_fields = ('actual_segment_cost',)
    fields = ('company', 'balance', 'top_up_amount', 'top_up_limit', 'last_payment', 'cost_of_segment',
              'auto_charge', 'actual_segment_cost',)

    def actual_segment_cost(self, obj):
        return obj.segment_cost


class TSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'active', 'subscription_id', 'current_period_start', 'current_period_end')
    list_filter = ('company',)
    readonly_fields = ('last_time_billed', 'sms_balance', 'current_period_start',
                       'current_period_end', 'worker_count', 'price', 'subscription_type',
                       'created')


class SubscriptionTypeAdmin(admin.ModelAdmin):

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.type == models.SubscriptionType.SUBSCRIPTION_TYPES.annual:
            return self.readonly_fields + ('start_range_price_monthly',)
        else:
            return self.readonly_fields + ('start_range_price_annual',)


class PaymentAdmin(admin.ModelAdmin):
    list_display = ('company', 'type', 'created')
    search_fields = ('company__name',)


class SMSBalanceLimitsAdmin(admin.ModelAdmin):
    list_display = ('name', 'low_balance_limit', 'email_template')

admin.site.register(models.SMSBalance, SMSBalanceAdmin)
admin.site.register(models.Subscription, TSubscriptionAdmin)
admin.site.register(models.SubscriptionType, SubscriptionTypeAdmin)
admin.site.register(models.Payment, PaymentAdmin)
admin.site.register(models.Discount)
admin.site.register(models.StripeCountryAccount)
admin.site.register(models.SMSBalanceLimits, SMSBalanceLimitsAdmin)
