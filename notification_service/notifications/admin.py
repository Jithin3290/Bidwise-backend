from django.contrib import admin
from .models import (
    NotificationChannel, NotificationType, UserNotificationPreference,
    Notification, NotificationDelivery, Conversation, Message,
    ConversationMember, MessageReadStatus
)

@admin.register(NotificationChannel)
class NotificationChannelAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name']

@admin.register(NotificationType)
class NotificationTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'title_template', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'title_template']
    filter_horizontal = ['default_channels']

@admin.register(UserNotificationPreference)
class UserNotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ['user_id', 'notification_type', 'is_enabled']
    list_filter = ['notification_type', 'is_enabled']
    search_fields = ['user_id']
    filter_horizontal = ['channels']

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['title', 'recipient_id', 'notification_type', 'priority', 'status', 'created_at']
    list_filter = ['notification_type', 'priority', 'status', 'created_at']
    search_fields = ['title', 'recipient_id', 'message']
    readonly_fields = ['created_at', 'sent_at', 'delivered_at', 'read_at']

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'conversation_type', 'title', 'is_active', 'created_at']
    list_filter = ['conversation_type', 'is_active', 'created_at']
    search_fields = ['title', 'job_id', 'bid_id']

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'conversation', 'sender_id', 'message_type', 'created_at']
    list_filter = ['message_type', 'is_edited', 'is_deleted', 'created_at']
    search_fields = ['sender_id', 'content']
    readonly_fields = ['created_at', 'updated_at']