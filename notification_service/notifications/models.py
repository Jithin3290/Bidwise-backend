# notifications/models.py
import uuid
from django.db import models
from django.utils import timezone


class NotificationChannel(models.Model):
    """Define different notification channels"""
    CHANNEL_CHOICES = [
        ('web', 'Web Notification'),
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('push', 'Push Notification'),
    ]

    name = models.CharField(max_length=50, choices=CHANNEL_CHOICES, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.get_name_display()


class NotificationType(models.Model):
    """Define different types of notifications"""
    TYPE_CHOICES = [
        # Bid related
        ('bid_created', 'New Bid Received'),
        ('bid_accepted', 'Bid Accepted'),
        ('bid_rejected', 'Bid Rejected'),
        ('bid_withdrawn', 'Bid Withdrawn'),

        # Job related
        ('job_published', 'Job Published'),
        ('job_updated', 'Job Updated'),
        ('job_expired', 'Job Expired'),
        ('job_completed', 'Job Completed'),

        # Message related
        ('new_message', 'New Message'),
        ('message_reply', 'Message Reply'),

        # System related
        ('account_verified', 'Account Verified'),
        ('profile_updated', 'Profile Updated'),
        ('payment_received', 'Payment Received'),
        ('system_maintenance', 'System Maintenance'),
    ]

    name = models.CharField(max_length=50, choices=TYPE_CHOICES, unique=True)
    title_template = models.CharField(max_length=200)
    message_template = models.TextField()
    default_channels = models.ManyToManyField(NotificationChannel, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.get_name_display()


class UserNotificationPreference(models.Model):
    """User preferences for notification types and channels"""
    user_id = models.CharField(max_length=100)  # From Users Service
    notification_type = models.ForeignKey(NotificationType, on_delete=models.CASCADE)
    channels = models.ManyToManyField(NotificationChannel)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user_id', 'notification_type']

    def __str__(self):
        return f"{self.user_id} - {self.notification_type.name}"


class Notification(models.Model):
    """Individual notification instances"""
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient_id = models.CharField(max_length=100)  # From Users Service
    notification_type = models.ForeignKey(NotificationType, on_delete=models.CASCADE)

    # Content
    title = models.CharField(max_length=200)
    message = models.TextField()
    data = models.JSONField(default=dict, blank=True)  # Additional data for frontend

    # Metadata
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    # Links and actions
    action_url = models.URLField(blank=True, null=True)
    action_text = models.CharField(max_length=50, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient_id', 'status']),
            models.Index(fields=['notification_type', 'created_at']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"Notification {self.id} - {self.title}"

    def mark_as_read(self):
        """Mark notification as read"""
        if self.status != 'read':
            self.status = 'read'
            self.read_at = timezone.now()
            self.save(update_fields=['status', 'read_at'])

    def mark_as_sent(self):
        """Mark notification as sent"""
        self.status = 'sent'
        self.sent_at = timezone.now()
        self.save(update_fields=['status', 'sent_at'])

    def mark_as_delivered(self):
        """Mark notification as delivered"""
        self.status = 'delivered'
        self.delivered_at = timezone.now()
        self.save(update_fields=['status', 'delivered_at'])

    @property
    def is_expired(self):
        """Check if notification has expired"""
        return self.expires_at and timezone.now() > self.expires_at


class NotificationDelivery(models.Model):
    """Track notification delivery across different channels"""
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name='deliveries')
    channel = models.ForeignKey(NotificationChannel, on_delete=models.CASCADE)

    status = models.CharField(max_length=10, choices=Notification.STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)

    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['notification', 'channel']

    def __str__(self):
        return f"{self.notification.title} via {self.channel.name}"


# Messaging System Models
class Conversation(models.Model):
    """Conversation between users"""
    CONVERSATION_TYPES = [
        ('job_inquiry', 'Job Inquiry'),
        ('bid_discussion', 'Bid Discussion'),
        ('project_communication', 'Project Communication'),
        ('support', 'Support'),
        ('general', 'General'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participants = models.JSONField()  # List of user IDs
    conversation_type = models.CharField(max_length=50, choices=CONVERSATION_TYPES, default='general')

    # Related entities
    job_id = models.CharField(max_length=100, blank=True, null=True)
    bid_id = models.CharField(max_length=100, blank=True, null=True)
    project_id = models.CharField(max_length=100, blank=True, null=True)

    # Metadata
    title = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    is_archived = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_message_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['participants']),
            models.Index(fields=['job_id', 'is_active']),
            models.Index(fields=['bid_id', 'is_active']),
            models.Index(fields=['last_message_at']),
        ]

    def __str__(self):
        return f"Conversation {self.id} - {self.title or 'No title'}"

    def get_other_participant(self, current_user_id):
        """Get the other participant in a 2-person conversation"""
        participants = self.participants
        return next((p for p in participants if str(p) != str(current_user_id)), None)


class Message(models.Model):
    """Individual messages in conversations"""
    MESSAGE_TYPES = [
        ('text', 'Text'),
        ('file', 'File'),
        ('image', 'Image'),
        ('system', 'System Message'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender_id = models.CharField(max_length=100)  # From Users Service

    # Content
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES, default='text')
    content = models.TextField()
    file_url = models.URLField(blank=True, null=True)
    file_name = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(null=True, blank=True)

    # Reply functionality
    reply_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)

    # Status tracking
    is_edited = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
            models.Index(fields=['sender_id', 'created_at']),
        ]

    def __str__(self):
        return f"Message {self.id} in {self.conversation.id}"


class MessageReadStatus(models.Model):
    """Track message read status per user"""
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='read_statuses')
    user_id = models.CharField(max_length=100)
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['message', 'user_id']
        indexes = [
            models.Index(fields=['user_id', 'read_at']),
        ]

    def __str__(self):
        return f"Message {self.message.id} read by {self.user_id}"


class ConversationMember(models.Model):
    """Track conversation membership and preferences"""
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='members')
    user_id = models.CharField(max_length=100)

    # Preferences
    is_muted = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)

    # Tracking
    last_read_message = models.ForeignKey(Message, on_delete=models.SET_NULL, null=True, blank=True)
    unread_count = models.PositiveIntegerField(default=0)

    # Timestamps
    joined_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['conversation', 'user_id']
        indexes = [
            models.Index(fields=['user_id', 'is_archived']),
            models.Index(fields=['conversation', 'unread_count']),
        ]

    def __str__(self):
        return f"{self.user_id} in {self.conversation.id}"


# Add to your existing models.py

class AIConversation(models.Model):
    """Track AI-powered conversations"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.CharField(max_length=100)  # From Users Service

    # Metadata
    title = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    # AI Configuration
    model_name = models.CharField(max_length=50, default='gpt-3.5-turbo')
    temperature = models.FloatField(default=0.7)
    max_tokens = models.IntegerField(default=1000)

    # Usage tracking
    total_tokens_used = models.IntegerField(default=0)
    total_messages = models.IntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_message_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-last_message_at']
        indexes = [
            models.Index(fields=['user_id', 'is_active']),
            models.Index(fields=['last_message_at']),
        ]

    def __str__(self):
        return f"AI Conversation {self.id} - {self.user_id}"


class AIMessage(models.Model):
    """Messages in AI conversations"""
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(AIConversation, on_delete=models.CASCADE, related_name='ai_messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()

    # Token tracking
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
        ]

    def __str__(self):
        return f"{self.role} message in {self.conversation.id}"