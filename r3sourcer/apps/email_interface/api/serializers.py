from rest_framework import serializers

from r3sourcer.apps.core.api.fields import ApiBaseRelatedField
from r3sourcer.apps.core.api.languages.serializers import LanguageSerializer
from r3sourcer.apps.core.api.serializers import ApiBaseModelSerializer
from r3sourcer.apps.core.models import Language, Contact, Company
from r3sourcer.apps.email_interface.models import EmailTemplate, EmailMessage


class EmailMessageSerializer(ApiBaseModelSerializer):

    method_fields = ('bodies',)

    class Meta:
        model = EmailMessage
        fields = '__all__'

    def get_bodies(self, obj):
        return [{'content': x.content} for x in obj.bodies.all()]


class EmailTemplateSerializer(serializers.ModelSerializer):
    language = LanguageSerializer(read_only=True)
    language_id = serializers.PrimaryKeyRelatedField(write_only=True, queryset=Language.objects.all())

    class Meta:
        model = EmailTemplate
        fields = (
            'id',
            'updated_at',
            'created_at',
            'name',
            'slug',
            'message_text_template',
            'message_html_template',
            'reply_timeout',
            'delivery_timeout',
            'type',
            'language_id',
            'company_id',
            'language',
        )

    def create(self, validated_data):
        language = validated_data.pop('language_id')
        template = EmailTemplate.objects.create(**validated_data, language=language)
        return template

    def update(self, instance, validated_data):
        instance.name = validated_data['name']
        instance.message_text_template = validated_data['message_text_template']
        instance.message_html_template = validated_data['message_html_template']
        instance.reply_timeout = validated_data['reply_timeout']
        instance.delivery_timeout = validated_data['delivery_timeout']
        instance.language = validated_data['language_id']
        instance.save()
        return instance
