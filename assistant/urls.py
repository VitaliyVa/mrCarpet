from django.urls import path

from .views import AssistantConversationView, AssistantMessageView, AssistantOrderPlacedView

urlpatterns = [
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
