from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers

from r3sourcer.apps.core.api.serializers import ApiBaseModelSerializer, ApiContactImageFieldsMixin
from r3sourcer.apps.core.models import Contact
from r3sourcer.apps.core.utils.utils import is_valid_email, is_valid_phone_number
from r3sourcer.apps.core.utils.companies import get_site_master_company

from .. import models


class LoginSerializer(serializers.Serializer):

    username = serializers.CharField(
        max_length=255,
        required=True,
        label=_('Phone or E-mail address')
    )
    password = serializers.CharField(
        max_length=128,
        required=False,
        allow_blank=True,
        allow_null=True,
        label=_('Password (optional)')
    )
    remember_me = serializers.BooleanField(
        required=False,
        default=False,
        label=_('Remember me')
    )
    country_code = serializers.CharField(label=_('Country code'),
                                         required=False)

    class Meta:
        model = models.TokenLogin
        fields = ('username', 'password', 'remember_me')

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        username = representation['username']
        country_code = representation.get('country_code')
        mobile_phone_username = is_valid_phone_number(username, country_code)
        if mobile_phone_username:
            if not username.startswith('+'):
                username = '+{}'.format(username)
            representation['username'] = username
        return representation

    def validate(self, data):
        username = data['username']

        email_username = is_valid_email(username)
        mobile_phone_username = is_valid_phone_number(username, data.get('country_code'))
        if email_username is False and mobile_phone_username is False:
            raise serializers.ValidationError(
                _(
                    "Please enter a correct email or mobile phone number and password. "
                    "Note that both fields may be case-sensitive."
                ),
                code='invalid_login',
            )

        return data


class TokenLoginSerializer(ApiBaseModelSerializer):
    class Meta:
        model = models.TokenLogin
        fields = ('contact', 'redirect_to', 'role')


class ContactLoginSerializer(ApiContactImageFieldsMixin, ApiBaseModelSerializer):
    name = serializers.SerializerMethodField()
    contact_type = serializers.CharField(source='get_role', read_only=True)
    contact_id = serializers.UUIDField(source='get_role_id', read_only=True)

    image_fields = ('picture', )
    method_fields = ('company', 'company_id', 'candidate_contact', 'default_language')

    class Meta:
        model = Contact
        fields = ('id', 'name', 'contact_type', 'contact_id', 'picture', 'email')

    def get_name(self, obj):
        return str(obj)

    def get_company(self, obj):
        return obj.get_closest_company().name

    def get_company_id(self, obj):
        return str(obj.get_closest_company().id)

    def get_candidate_contact(self, obj):
        if obj.is_candidate_contact():
            candidate = obj.candidate_contacts.filter(candidate_rels__master_company=get_site_master_company()).first()
            if candidate:
                return str(candidate.pk)

    def get_default_language(self, obj):
        language = obj.languages.filter(default=True).first()
        if language:
            return language.language.alpha_2
        else:
            return None


class TokenPayloadSerializer(ApiContactImageFieldsMixin, ApiBaseModelSerializer):
    name = serializers.SerializerMethodField()
    contact_type = serializers.CharField(source='get_role', read_only=True)
    contact_id = serializers.UUIDField(source='get_role_id', read_only=True)

    method_fields = ('company', 'company_id', 'candidate_contact')

    class Meta:
        model = Contact
        fields = ('id', 'name', 'contact_type', 'contact_id', 'email')

    def get_name(self, obj):
        return str(obj)

    def get_company(self, obj):
        return obj.get_closest_company().name

    def get_company_id(self, obj):
        return str(obj.get_closest_company().id)

    def get_candidate_contact(self, obj):
        if obj.is_candidate_contact():
            candidate = obj.candidate_contacts.filter(candidate_rels__master_company=get_site_master_company()).first()
            if candidate:
                return str(candidate.pk)
        return None
