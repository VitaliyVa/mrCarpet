from rest_framework import serializers

from ukr_poshta.models import UkrOffice, City


class UkrOfficeSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = UkrOffice
        fields = "__all__"

    def get_full_name(self, obj):
        return f"{obj.post_office} {obj.street}"


class CitySerializer(serializers.ModelSerializer):
    offices = UkrOfficeSerializer(source="related_city", many=True, read_only=True)

    class Meta:
        model = City
        fields = "__all__"