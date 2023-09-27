from django.db import transaction
from rest_framework import serializers

from r3sourcer.apps.core.models import ContactBankAccount, ContactBankAccountField


class ContactBankAccountFieldSerializer(serializers.Serializer):
    def update(self, instance, validated_data):
        raise NotImplementedError

    def create(self, validated_data):
        bank_account_field = ContactBankAccountField(**validated_data)
        bank_account_field.save()
        return bank_account_field

    field_id = serializers.IntegerField()
    value = serializers.CharField()

    class Meta:
        fields = (
            'field_id',
            'value',
        )


class ContactBankAccountSerializer(serializers.Serializer):
    def update(self, instance, validated_data):
        raise NotImplementedError

    def create(self, validated_data):
        with transaction.atomic():
            bank_account = ContactBankAccount(
                contact_id=validated_data['contact_id'],
                layout_id=validated_data['layout_id'],
            )
            bank_account.save()
            for field in validated_data['fields']:
                field_serializer = ContactBankAccountFieldSerializer(field)
                field_serializer.create(dict(bank_account_id=str(bank_account.pk),
                                             **field_serializer.data))
            return bank_account

    id = serializers.CharField(read_only=True)
    contact_id = serializers.CharField()
    layout_id = serializers.IntegerField()
    fields = ContactBankAccountFieldSerializer(many=True)

    class Meta:
        fields = (
            'id',
            'contact_id',
            'layout_id',
            'fields',
        )
