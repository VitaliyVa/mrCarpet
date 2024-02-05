from rest_framework.generics import CreateAPIView

from .serializers import ContactRequestSerializer
from ..models import ContactRequest


class ContactRequestCreateView(CreateAPIView):
    queryset = ContactRequest.objects.all()
    serializer_class = ContactRequestSerializer
