from django.urls import path

from .views import AssistantCartView, AssistantConfigView, AssistantConversationView, AssistantMessageView, AssistantOrderPlacedView

urlpatterns = [
    path("assistant/config/", AssistantConfigView.as_view(), name="assistant-config"),
    path("assistant/cart/", AssistantCartView.as_view(), name="assistant-cart"),
    path("assistant/message/", AssistantMessageView.as_view(), name="assistant-message"),
    path(
        "assistant/conversations/<str:conversation_id>/",
        AssistantConversationView.as_view(),
        name="assistant-conversation",
    ),
    path(
        "assistant/conversations/<str:conversation_id>/order-placed/",
        AssistantOrderPlacedView.as_view(),
        name="assistant-order-placed",
    ),
]
