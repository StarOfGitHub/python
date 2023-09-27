from rest_framework import serializers

from r3sourcer.apps.core.models import Language


class LanguageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Language
        fields = (
            'alpha_2',
            'name',
        )
