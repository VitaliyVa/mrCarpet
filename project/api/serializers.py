from rest_framework import serializers

from ..models import ContactRequest, Subscription


class ContactRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactRequest
        fields = [
            "name",
            "email",
            "text",
        ]


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = ["email"]
