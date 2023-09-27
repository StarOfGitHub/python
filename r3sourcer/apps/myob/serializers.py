from rest_framework import serializers

from r3sourcer.apps.myob.models import MYOBCompanyFile, MYOBAuthData


class MYOBCompanyFileSerializer(serializers.ModelSerializer):
    id = serializers.CharField()
    cf_id = serializers.CharField()
    uri = serializers.CharField(source='cf_uri')
    name = serializers.CharField(source='cf_name')

    class Meta:
        model = MYOBCompanyFile
        fields = ('id', 'cf_id', 'uri', 'name', 'authenticated')


class MYOBAuthDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = MYOBAuthData
        fields = ("id", "myob_user_username")
