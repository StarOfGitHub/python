from django.core.exceptions import ObjectDoesNotExist, ValidationError
from rest_framework import serializers

from r3sourcer.apps.core.models import CompanyLanguage, Company, Language
from r3sourcer.apps.core.api.languages.serializers import LanguageSerializer


class CompanyLanguageSerializer(serializers.ModelSerializer):
    language_id = serializers.CharField(write_only=True)
    company_id = serializers.CharField(write_only=True)
    language = LanguageSerializer(read_only=True)
    company = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = CompanyLanguage
        fields = (
            'language_id',
            'company_id',
            'default',
            'language',
            'company',
        )

    @classmethod
    def validate_language_id(cls, value):
        try:
            Language.objects.get(alpha_2=value)
        except ObjectDoesNotExist:
            raise ValidationError('Language with alpha_2 = {} does not exist'.format(value))
        return value

    @classmethod
    def validate_company_id(cls, value):
        try:
            Company.objects.get(pk=value)
        except ObjectDoesNotExist:
            raise ValidationError('Candidate contact with pk = {} does not exist'.format(value))
        return value

    @classmethod
    def get_company(cls, obj):
        return {'id': obj.company_id,
                '__str__': str(obj.company)}
