from rest_framework.generics import CreateAPIView

from .serializers import ContactRequestSerializer, SubscriptionSerializer
from ..models import ContactRequest, Subscription


class ContactRequestCreateView(CreateAPIView):
    queryset = ContactRequest.objects.all()
    serializer_class = ContactRequestSerializer


class SubscriptionCreateView(CreateAPIView):
    queryset = Subscription.objects.all()
    serializer_class = SubscriptionSerializer
