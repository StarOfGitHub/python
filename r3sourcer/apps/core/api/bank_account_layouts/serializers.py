from rest_framework import serializers


class BankAccountFieldLanguage(serializers.Serializer):

    def update(self, instance, validated_data):
        raise NotImplementedError

    def create(self, validated_data):
        raise NotImplementedError

    name = serializers.CharField()
    default = serializers.BooleanField()
    language_id = serializers.CharField()

    class Meta:
        fields = (
            'name',
            'language_id',
            'default',
        )


class BankAccountLayoutFieldSerializer(serializers.Serializer):
    def update(self, instance, validated_data):
        raise NotImplementedError

    def create(self, validated_data):
        raise NotImplementedError

    id = serializers.IntegerField(source='field.id')
    name = serializers.CharField(source='field.name')
    description = serializers.CharField(source='field.description')
    order = serializers.IntegerField(default=0)
    languages = BankAccountFieldLanguage(many=True, source='field.languages')

    class Meta:
        fields = (
            'id',
            'name',
            'description',
            'languages',
            'order',
        )


class BankAccountLayoutSerializer(serializers.Serializer):
    def update(self, instance, validated_data):
        raise NotImplementedError

    def create(self, validated_data):
        raise NotImplementedError

    id = serializers.IntegerField()
    name = serializers.CharField()
    slug = serializers.CharField()
    description = serializers.CharField()
    fields = BankAccountLayoutFieldSerializer(many=True)

    class Meta:
        fields = (
            'id',
            'name',
            'slug',
            'description',
            'fields',
        )
