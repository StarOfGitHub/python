from django.core.exceptions import ObjectDoesNotExist, ValidationError
from rest_framework import serializers

from r3sourcer.apps.core.api.languages.serializers import LanguageSerializer
from r3sourcer.apps.core.models import Language
from r3sourcer.apps.core.models.core import ContactLanguage, Contact


class ContactLanguageSerializer(serializers.ModelSerializer):
    language_id = serializers.CharField(write_only=True)
    contact_id = serializers.CharField(write_only=True)
    language = LanguageSerializer(read_only=True)
    contact = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ContactLanguage
        fields = (
            'language_id',
            'contact_id',
            'default',
            'language',
            'contact',
        )

    @classmethod
    def validate_language_id(cls, value):
        try:
            Language.objects.get(alpha_2=value)
        except ObjectDoesNotExist:
            raise ValidationError('Language with alpha_2 = {} does not exist'.format(value))
        return value

    @classmethod
    def validate_contact_id(cls, value):
        try:
            Contact.objects.get(pk=value)
        except ObjectDoesNotExist:
            raise ValidationError('Contact with pk = {} does not exist'.format(value))
        return value

    @classmethod
    def get_contact(cls, obj):
        return {'id': obj.contact_id,
                '__str__': str(obj.contact)}
