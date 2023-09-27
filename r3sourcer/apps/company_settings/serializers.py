from django.contrib.auth.models import Group
from django.db.models import Q
from rest_framework import serializers

from r3sourcer.apps.company_settings.models import CompanySettings, MYOBAccount, MYOBSettings, MYOBCompanyFile
from r3sourcer.apps.core.api.fields import ApiBase64ImageField
from r3sourcer.apps.core.models import InvoiceRule, Form, Company
from r3sourcer.apps.hr.models import PayslipRule
from r3sourcer.apps.core.models import User
from r3sourcer.apps.company_settings.models import GlobalPermission


class CompanySettingsSerializer(serializers.ModelSerializer):
    logo = ApiBase64ImageField()
    register_form_id = serializers.SerializerMethodField()
    company_name = serializers.SerializerMethodField()
    country_code = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()

    class Meta:
        model = CompanySettings
        fields = (
            'id', 'logo', 'color_scheme', 'font', 'forwarding_number', 'company', 'billing_email', 'register_form_id',
            'company_name', 'sms_enabled', 'pre_shift_sms_enabled', 'pre_shift_sms_delta', 'invoice_template', 'advance_state_saving',
            'country_code', 'currency'
        )
        read_only_fields = ('company',)

    def get_register_form_id(self, obj):
        form = Form.objects.filter(company=obj.company, is_active=True).first()
        if not form:
            form = Form.objects.filter(company=None, is_active=True).first()

        return form and form.id

    def get_company_name(self, obj):
        if obj.company:
            return obj.company.short_name or obj.company.name

    def get_country_code(self, obj):
        if obj.company:
            hq_addr = obj.company.get_hq_address()
            if not hq_addr:
                return
            return hq_addr.address.country.code2

    def get_currency(self, obj):
        if obj.company:
            hq_addr = obj.company.get_hq_address()
            if not hq_addr:
                return
            return hq_addr.address.country.currency


class PayslipRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayslipRule
        fields = ('id', 'period')


class InvoiceRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceRule
        fields = (
            'id', 'period', 'separation_rule', 'show_candidate_name', 'serial_number', 'starting_number',
            'period_zero_reference'
        )


class MYOBAccountSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField()

    class Meta:
        model = MYOBAccount
        fields = ('id', 'number', 'name', 'type')


class MYOBCompanyFileSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField()

    class Meta:
        model = MYOBCompanyFile
        fields = ('id', 'cf_name')


class MYOBSettingsSerializer(serializers.ModelSerializer):
    invoice_company_file = MYOBCompanyFileSerializer()
    invoice_activity_account = MYOBAccountSerializer()
    timesheet_company_file = MYOBCompanyFileSerializer()

    class Meta:
        model = MYOBSettings
        fields = ('invoice_company_file', 'invoice_activity_account', 'timesheet_company_file',
                  'payroll_accounts_last_refreshed', 'company_files_last_refreshed')

    def update(self, instance, validated_data):
        fields = ('invoice_company_file', 'timesheet_company_file')

        for field in fields:
            if validated_data.get(field, None):
                company_file = MYOBCompanyFile.objects.filter(cf_id=validated_data[field]['id']).first()

                if company_file:
                    setattr(instance, field, company_file)
            validated_data.pop(field)

        if validated_data.get('invoice_activity_account', None):
            myob_account = MYOBAccount.objects.filter(id=validated_data['invoice_activity_account']['id']).first()
            instance.invoice_activity_account = myob_account

        validated_data.pop('invoice_activity_account', None)
        instance.save()
        super(MYOBSettingsSerializer, self).update(instance, validated_data)
        return instance


class GlobalPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalPermission
        fields = ('id', 'name', 'codename')


class GroupSerializer(serializers.ModelSerializer):
    permissions = GlobalPermissionSerializer(source='permissions.all', many=True)

    class Meta:
        model = Group
        fields = ('id', 'name', 'permissions')


class PermissionListSerializer(serializers.Serializer):
    permission_list = serializers.ListField(child=serializers.IntegerField(), min_length=1)

    def validate_permission_list(self, permission_list):
        permission_count = GlobalPermission.objects.filter(id__in=permission_list).count()

        if permission_count != len(permission_list):
            raise serializers.ValidationError("Some permissions dont exist.")

        return permission_list


class CompanyUserSerializer(serializers.ModelSerializer):
    """
    Serializer for rendering list of Users of a given Company in CompanyUserListView
    """
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'name')

    def get_name(self, obj):
        title = ''
        name = '{} {}'.format(obj.contact.first_name, obj.contact.last_name)
        if obj.contact.is_company_contact():
            qry = Q(relationships__company__type=Company.COMPANY_TYPES.master)

            if 'company' in self.context:
                qry = Q(relationships__company=self.context['company'])

            title = obj.contact.company_contact.filter(qry).first().job_title
            name = '{} {}'.format(title, name) if title else name

        return name


class UserGroupSerializer(serializers.ModelSerializer):
    """
    Serializer for rendering list of Groups of a given User in UserGroupListView
    """
    class Meta:
        model = Group
        fields = ('id', 'name')
