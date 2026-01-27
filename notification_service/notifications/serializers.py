# notifications/serializers.py
from rest_framework import serializers
from .models import (
    Notification, NotificationType, NotificationChannel,
    UserNotificationPreference, Conversation, Message,
    ConversationMember, MessageReadStatus
)


class NotificationTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationType
        fields = ['id', 'name', 'title_template', 'message_template', 'is_active']


class NotificationChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationChannel
        fields = ['id', 'name', 'is_active']


class UserNotificationPreferenceSerializer(serializers.ModelSerializer):
    notification_type = NotificationTypeSerializer(read_only=True)
    channels = NotificationChannelSerializer(many=True, read_only=True)

    class Meta:
        model = UserNotificationPreference
        fields = ['id', 'notification_type', 'channels', 'is_enabled']


class NotificationSerializer(serializers.ModelSerializer):
    notification_type_name = serializers.CharField(source='notification_type.name', read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id', 'recipient_id', 'notification_type_name', 'title', 'message',
            'data', 'priority', 'status', 'action_url', 'action_text',
            'created_at', 'sent_at', 'delivered_at', 'read_at', 'expires_at'
        ]
        read_only_fields = ['id', 'created_at', 'sent_at', 'delivered_at']


class NotificationCreateSerializer(serializers.Serializer):
    recipient_id = serializers.CharField(max_length=100)
    notification_type = serializers.CharField(max_length=50)
    title = serializers.CharField(max_length=200)
    message = serializers.CharField()
    data = serializers.JSONField(default=dict, required=False)
    priority = serializers.ChoiceField(
        choices=['low', 'normal', 'high', 'urgent'],
        default='normal'
    )
    action_url = serializers.URLField(required=False, allow_blank=True)
    action_text = serializers.CharField(max_length=50, required=False, allow_blank=True)
    expires_at = serializers.DateTimeField(required=False)


class MessageSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)  # convert UUID to string
    conversation = serializers.CharField(source='conversation.id', read_only=True)  # also as string

    sender_info = serializers.SerializerMethodField()
    reply_to_message = serializers.SerializerMethodField()
    read_by = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'conversation', 'sender_id', 'sender_info', 'content',
            'message_type', 'file_url', 'file_name', 'file_size',
            'reply_to', 'reply_to_message', 'is_edited', 'is_deleted',
            'created_at', 'updated_at', 'read_by'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'sender_info', 'read_by']


    def get_sender_info(self, obj):
        """Get sender information from users service"""
        # This would normally call the users service
        # For now, return basic info
        return {
            'id': obj.sender_id,
            'username': f'User {obj.sender_id}',
            'profile_picture': None
        }

    def get_reply_to_message(self, obj):
        """Get the message this is replying to"""
        if obj.reply_to:
            return {
                'id': str(obj.reply_to.id),
                'content': obj.reply_to.content[:100] + '...' if len(
                    obj.reply_to.content) > 100 else obj.reply_to.content,
                'sender_id': obj.reply_to.sender_id
            }
        return None

    def get_read_by(self, obj):
        read_statuses = obj.read_statuses.all()
        return [
            {
                'user_id': status.user_id,
                'read_at': status.read_at.isoformat() if status.read_at else None
            }
            for status in read_statuses
        ]


class ConversationSerializer(serializers.ModelSerializer):
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    other_participant = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            'id', 'participants', 'conversation_type', 'job_id', 'bid_id',
            'project_id', 'title', 'is_active', 'created_at', 'updated_at',
            'last_message_at', 'last_message', 'unread_count', 'other_participant'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'last_message_at']

    def get_last_message(self, obj):
        """Get the last message in conversation"""
        last_message = obj.messages.filter(is_deleted=False).last()
        if last_message:
            return {
                'id': str(last_message.id),
                'content': last_message.content,
                'sender_id': last_message.sender_id,
                'created_at': last_message.created_at,
                'message_type': last_message.message_type
            }
        return None

    def get_unread_count(self, obj):
        """Get unread count for current user"""
        request = self.context.get('request')
        if request and hasattr(request, 'user') and hasattr(request.user, 'user_id'):
            user_id = str(request.user.user_id)
            member = obj.members.filter(user_id=user_id).first()
            return member.unread_count if member else 0
        return 0

    def get_other_participant(self, obj):
        """Get other participant info for 2-person conversations"""
        request = self.context.get('request')
        if request and hasattr(request, 'user') and hasattr(request.user, 'user_id'):
            current_user_id = str(request.user.user_id)
            other_participant_id = obj.get_other_participant(current_user_id)
            if other_participant_id:
                # This would normally call the users service
                return {
                    'id': other_participant_id,
                    'username': f'User {other_participant_id}',
                    'profile_picture': None
                }
        return None


class ConversationCreateSerializer(serializers.ModelSerializer):
    participants = serializers.ListField(
        child=serializers.CharField(),
        min_length=2,
        max_length=10
    )

    class Meta:
        model = Conversation
        fields = [
            'participants', 'conversation_type', 'job_id', 'bid_id',
            'project_id', 'title'
        ]

    def validate_participants(self, value):
        """Validate participants list"""
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Duplicate participants not allowed")
        return value


class MessageCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ['content', 'message_type', 'file_url', 'file_name', 'file_size', 'reply_to']

    def validate_content(self, value):
        """Validate message content"""
        if not value.strip():
            raise serializers.ValidationError("Message content cannot be empty")
        if len(value) > 5000:
            raise serializers.ValidationError("Message too long (max 5000 characters)")
        return value.strip()


# Add to your existing serializers.py

from .models import AIConversation, AIMessage


class AIMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIMessage
        fields = [
            'id', 'role', 'content', 'prompt_tokens',
            'completion_tokens', 'total_tokens', 'created_at'
        ]


class AIConversationSerializer(serializers.ModelSerializer):
    ai_messages = AIMessageSerializer(many=True, read_only=True)
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = AIConversation
        fields = [
            'id', 'user_id', 'title', 'is_active', 'model_name',
            'temperature', 'max_tokens', 'total_tokens_used',
            'total_messages', 'created_at', 'updated_at',
            'last_message_at', 'ai_messages', 'message_count'
        ]

    def get_message_count(self, obj):
        return obj.ai_messages.count()


class AIChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=5000)
    conversation_id = serializers.UUIDField(required=False, allow_null=True)
    system_prompt = serializers.CharField(required=False, allow_null=True, max_length=2000)


class AIConversationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIConversation
        fields = ['title', 'model_name', 'temperature', 'max_tokens']