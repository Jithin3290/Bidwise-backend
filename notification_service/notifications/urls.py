# notifications/urls.py - Updated for CBVs
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    # Notification views
    CreateNotificationView, UserNotificationsView, MarkNotificationReadView,
    MarkAllNotificationsReadView, NotificationStatsView,

    # Messaging views
    ConversationListView, ConversationCreateView, ConversationDetailView,
    ConversationMessagesView, SendMessageView, ConversationStatsView,
    MarkConversationReadView,

    # New messaging views
    StartConversationView, ConversationParticipantsView, UpdateConversationView,
    DeleteMessageView, EditMessageView, SearchMessagesView,

    # Utility views
    HealthCheckView, AIChatView, AIConversationListView, AIConversationDetailView, AIConversationDeleteView,
    AIConversationStatsView
)

# Create router for ViewSets
router = DefaultRouter()

urlpatterns = [
    # Include router URLs
    path('', include(router.urls)),

    # Health check
    path('health/', HealthCheckView.as_view(), name='health_check'),

    # Notification endpoints
    path('notifications/create/', CreateNotificationView.as_view(), name='create_notification'),
    path('notifications/<uuid:notification_id>/delete/', CreateNotificationView.as_view(), name='delete_notification'),
    path('notifications/', UserNotificationsView.as_view(), name='user_notifications'),
    path('notifications/<uuid:notification_id>/read/', MarkNotificationReadView.as_view(), name='mark_notification_read'),
    path('notifications/read-all/', MarkAllNotificationsReadView.as_view(), name='mark_all_notifications_read'),
    path('notifications/stats/', NotificationStatsView.as_view(), name='notification_stats'),

    # Conversations under notifications
    path('notifications/conversations/', ConversationListView.as_view(), name='conversation_list'),
    path('notifications/conversations/create/', ConversationCreateView.as_view(), name='conversation_create'),
    path('notifications/conversations/start/', StartConversationView.as_view(), name='start_conversation'),
    path('notifications/conversations/<uuid:pk>/', ConversationDetailView.as_view(), name='conversation_detail'),
    path('notifications/conversations/<uuid:conversation_id>/messages/', ConversationMessagesView.as_view(),
         name='conversation_messages'),
    path('notifications/conversations/<uuid:conversation_id>/send/', SendMessageView.as_view(), name='send_message'),
    path('notifications/conversations/<uuid:conversation_id>/read/', MarkConversationReadView.as_view(),
         name='mark_conversation_read'),
    path('notifications/conversations/<uuid:conversation_id>/participants/', ConversationParticipantsView.as_view(),
         name='conversation_participants'),
    path('notifications/conversations/<uuid:conversation_id>/update/', UpdateConversationView.as_view(), name='update_conversation'),
    path('notifications/conversations/stats/', ConversationStatsView.as_view(), name='conversation_stats'),

    # Message management
    path('messages/<uuid:message_id>/edit/', EditMessageView.as_view(), name='edit_message'),
    path('messages/<uuid:message_id>/delete/', DeleteMessageView.as_view(), name='delete_message'),
    path('messages/search/', SearchMessagesView.as_view(), name='search_messages'),





    path('ai/chat/', AIChatView.as_view(), name='ai_chat'),
    path('ai/conversations/', AIConversationListView.as_view(), name='ai_conversation_list'),
    path('ai/conversations/<uuid:pk>/', AIConversationDetailView.as_view(), name='ai_conversation_detail'),
    path('ai/conversations/<uuid:conversation_id>/delete/', AIConversationDeleteView.as_view(), name='ai_conversation_delete'),
    path('ai/conversations/stats/', AIConversationStatsView.as_view(), name='ai_conversation_stats'),

]
