
import json
import logging
from urllib.parse import parse_qs

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.db import models

from .authentication import JWTAuthentication
from .models import Conversation, ConversationMember, Message

logger = logging.getLogger(__name__)


# notifications/consumers.py
import json
import logging
from urllib.parse import parse_qs

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.db.models import Q
from django.utils import timezone

from .authentication import JWTAuthentication
from .models import Conversation, ConversationMember, Message, MessageReadStatus

logger = logging.getLogger(__name__)


class MessagingConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time messaging"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.user_groups = []

    async def connect(self):
        """Handle WebSocket connection"""
        # Parse token from query string
        query_params = parse_qs(self.scope['query_string'].decode())
        token = query_params.get('token', [None])[0]

        if not token:
            logger.warning("No token provided in WebSocket connection")
            await self.close(code=4001)
            return

        # Authenticate user
        self.user = await self.authenticate_user(token)
        if not self.user:
            logger.warning("Failed to authenticate WebSocket user")
            await self.close(code=4002)
            return

        # Accept connection
        await self.accept()

        # Join user-specific groups (messaging + active conversations)
        await self.join_user_groups()

        # Send connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected to messaging',
            'user_id': self.user.user_id
        }))

        logger.info(f"User {self.user.user_id} connected to messaging WebSocket")

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        # Leave all groups
        for group_name in self.user_groups:
            await self.channel_layer.group_discard(group_name, self.channel_name)

        # Update user's last seen
        if self.user:
            await self.update_user_last_seen()
            logger.info(f"User {self.user.user_id} disconnected from messaging WebSocket")

    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'send_message':
                await self.handle_send_message(data)
            elif message_type == 'join_conversation':
                await self.handle_join_conversation(data)
            elif message_type == 'leave_conversation':
                await self.handle_leave_conversation(data)
            elif message_type == 'mark_read':
                await self.handle_mark_read(data)
            elif message_type == 'typing_start':
                await self.handle_typing(data, True)
            elif message_type == 'typing_stop':
                await self.handle_typing(data, False)
            else:
                await self.send_error('Unknown message type')

        except json.JSONDecodeError:
            await self.send_error('Invalid JSON format')
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await self.send_error('Internal server error')

    # -------------------------
    # Message handlers
    # -------------------------

    async def handle_send_message(self, data):
        conversation_id = data.get('conversation_id')
        content = data.get('content', '').strip()
        reply_to = data.get('reply_to')

        if not conversation_id or not content:
            await self.send_error('Missing required fields')
            return

        # Verify access
        if not await self.verify_conversation_access(conversation_id):
            await self.send_error('Access denied to conversation')
            return

        # Create message
        message = await self.create_message(conversation_id, content, reply_to)
        if message:
            serialized = await self.serialize_message(message)
            await self.channel_layer.group_send(
                f"conversation_{conversation_id}",
                {
                    'type': 'chat_message',
                    'message': serialized
                }
            )

    async def handle_join_conversation(self, data):
        conversation_id = data.get('conversation_id')
        if not conversation_id:
            await self.send_error('Missing conversation_id')
            return

        if not await self.verify_conversation_access(conversation_id):
            await self.send_error('Access denied to conversation')
            return

        group_name = f"conversation_{conversation_id}"
        await self.channel_layer.group_add(group_name, self.channel_name)
        if group_name not in self.user_groups:
            self.user_groups.append(group_name)

        await self.send_success('Joined conversation')

    async def handle_leave_conversation(self, data):
        conversation_id = data.get('conversation_id')
        if not conversation_id:
            await self.send_error('Missing conversation_id')
            return

        group_name = f"conversation_{conversation_id}"
        await self.channel_layer.group_discard(group_name, self.channel_name)
        if group_name in self.user_groups:
            self.user_groups.remove(group_name)

        await self.send_success('Left conversation')

    async def handle_mark_read(self, data):
        conversation_id = data.get('conversation_id')
        if not conversation_id:
            await self.send_error('Missing conversation_id')
            return

        await self.mark_conversation_read(conversation_id)
        await self.channel_layer.group_send(
            f"conversation_{conversation_id}",
            {
                'type': 'messages_read',
                'user_id': self.user.user_id,
                'conversation_id': conversation_id
            }
        )

    async def handle_typing(self, data, is_typing: bool):
        conversation_id = data.get('conversation_id')
        if not conversation_id:
            return
        await self.channel_layer.group_send(
            f"conversation_{conversation_id}",
            {
                'type': 'typing_indicator',
                'user_id': self.user.user_id,
                'conversation_id': conversation_id,
                'is_typing': is_typing
            }
        )

    # -------------------------
    # WebSocket event handlers
    # -------------------------

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({'type': 'message', 'data': event['message']}))

    async def messages_read(self, event):
        if event['user_id'] != self.user.user_id:
            await self.send(text_data=json.dumps({
                'type': 'read_receipt',
                'data': {
                    'user_id': event['user_id'],
                    'conversation_id': event['conversation_id']
                }
            }))

    async def typing_indicator(self, event):
        if event['user_id'] != self.user.user_id:
            await self.send(text_data=json.dumps({
                'type': 'typing',
                'data': {
                    'user_id': event['user_id'],
                    'conversation_id': event['conversation_id'],
                    'is_typing': event['is_typing']
                }
            }))

    # -------------------------
    # Database operations
    # -------------------------

    @database_sync_to_async
    def authenticate_user(self, token):
        try:
            from django.http import HttpRequest
            request = HttpRequest()
            request.META['HTTP_AUTHORIZATION'] = f'Bearer {token}'

            auth = JWTAuthentication()
            user_auth = auth.authenticate(request)
            return user_auth[0] if user_auth else None
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return None

    @database_sync_to_async
    def verify_conversation_access(self, conversation_id):
        try:
            # Use ConversationMember for SQLite compatibility
            conversation = Conversation.objects.filter(
                id=conversation_id,
                members__user_id=str(self.user.user_id),
                is_active=True
            ).first()
            return conversation is not None
        except Exception:
            return False

    @database_sync_to_async
    def create_message(self, conversation_id, content, reply_to=None):
        try:
            conversation = Conversation.objects.get(id=conversation_id)
            reply_message = None
            if reply_to:
                try:
                    reply_message = Message.objects.get(id=reply_to, conversation=conversation)
                except Message.DoesNotExist:
                    pass

            message = Message.objects.create(
                conversation=conversation,
                sender_id=self.user.user_id,
                content=content,
                reply_to=reply_message
            )

            # Mark as read for sender
            MessageReadStatus.objects.create(message=message, user_id=self.user.user_id)

            # Update unread counts for others
            ConversationMember.objects.filter(conversation=conversation).exclude(
                user_id=self.user.user_id
            ).update(unread_count=models.F('unread_count') + 1)

            return message
        except Exception as e:
            logger.error(f"Error creating message: {e}")
            return None

    @database_sync_to_async
    def serialize_message(self, message):
        from .serializers import MessageSerializer
        return MessageSerializer(message).data

    @database_sync_to_async
    def mark_conversation_read(self, conversation_id):
        try:
            conversation = Conversation.objects.get(id=conversation_id)
            unread_messages = Message.objects.filter(
                conversation=conversation,
                is_deleted=False
            ).exclude(
                Q(sender_id=self.user.user_id) |
                Q(read_statuses__user_id=self.user.user_id)
            )

            MessageReadStatus.objects.bulk_create([
                MessageReadStatus(message=msg, user_id=self.user.user_id)
                for msg in unread_messages
            ], ignore_conflicts=True)

            member = ConversationMember.objects.filter(conversation=conversation, user_id=self.user.user_id).first()
            if member:
                member.unread_count = 0
                member.last_seen_at = timezone.now()
                member.save(update_fields=['unread_count', 'last_seen_at'])
        except Exception as e:
            logger.error(f"Error marking conversation as read: {e}")

    @database_sync_to_async
    def update_user_last_seen(self):
        ConversationMember.objects.filter(user_id=self.user.user_id).update(last_seen_at=timezone.now())

    @database_sync_to_async
    def get_user_conversations(self):
        try:
            # Use ConversationMember for SQLite compatibility
            conversations = Conversation.objects.filter(
                members__user_id=str(self.user.user_id),
                is_active=True
            ).values_list('id', flat=True)
            return [str(c) for c in conversations]
        except Exception as e:
            logger.error(f"Error getting user conversations: {e}")
            return []

    async def join_user_groups(self):
        """Join general messaging + active conversations"""
        # General messaging group
        group = f"messaging_{self.user.user_id}"
        await self.channel_layer.group_add(group, self.channel_name)
        self.user_groups.append(group)

        # Active conversations
        active_convs = await self.get_user_conversations()
        for conv_id in active_convs:
            group_name = f"conversation_{conv_id}"
            await self.channel_layer.group_add(group_name, self.channel_name)
            self.user_groups.append(group_name)

    # -------------------------
    # Utilities
    # -------------------------
    async def send_error(self, message):
        await self.send(text_data=json.dumps({'type': 'error', 'message': message}))

    async def send_success(self, message):
        await self.send(text_data=json.dumps({'type': 'success', 'message': message}))


class NotificationConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for notifications"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.notification_group = None

    async def connect(self):
        """Handle WebSocket connection"""
        # Get token from query params
        token = self.scope['query_string'].decode().split('token=')[-1] if 'token=' in self.scope[
            'query_string'].decode() else None

        if not token:
            await self.close(code=4001)
            return

        # Authenticate user
        self.user = await self.authenticate_user(token)
        if not self.user:
            await self.close(code=4002)
            return

        # Accept connection and join notification group
        await self.accept()

        self.notification_group = f"notifications_{self.user.user_id}"
        await self.channel_layer.group_add(
            self.notification_group,
            self.channel_name
        )

        logger.info(f"User {self.user.user_id} connected to notifications WebSocket")

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        if self.notification_group:
            await self.channel_layer.group_discard(
                self.notification_group,
                self.channel_name
            )

        if self.user:
            logger.info(f"User {self.user.user_id} disconnected from notifications WebSocket")

    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'mark_read':
                await self.handle_mark_notification_read(data)
            elif message_type == 'mark_all_read':
                await self.handle_mark_all_notifications_read()
            else:
                await self.send_error('Unknown message type')

        except json.JSONDecodeError:
            await self.send_error('Invalid JSON format')
        except Exception as e:
            logger.error(f"Error handling notification message: {e}")
            await self.send_error('Internal server error')

    async def handle_mark_notification_read(self, data):
        """Handle marking a notification as read"""
        notification_id = data.get('notification_id')

        if not notification_id:
            await self.send_error('Missing notification_id')
            return

        success = await self.mark_notification_read(notification_id)
        if success:
            await self.send_success('Notification marked as read')
        else:
            await self.send_error('Failed to mark notification as read')

    async def handle_mark_all_notifications_read(self):
        """Handle marking all notifications as read"""
        await self.mark_all_notifications_read()
        await self.send_success('All notifications marked as read')

    # WebSocket event handlers
    async def notification_message(self, event):
        """Send notification to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'data': event['notification']
        }))

    # Database operations
    @database_sync_to_async
    def authenticate_user(self, token):
        """Authenticate user with JWT token"""
        try:
            from django.http import HttpRequest
            request = HttpRequest()
            request.META['HTTP_AUTHORIZATION'] = f'Bearer {token}'

            auth = JWTAuthentication()
            user_auth = auth.authenticate(request)

            if user_auth:
                return user_auth[0]
            return None
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return None

    @database_sync_to_async
    def mark_notification_read(self, notification_id):
        """Mark a notification as read"""
        try:
            from .models import Notification
            notification = Notification.objects.get(
                id=notification_id,
                recipient_id=self.user.user_id
            )
            notification.mark_as_read()
            return True
        except Exception as e:
            logger.error(f"Error marking notification as read: {e}")
            return False

    @database_sync_to_async
    def mark_all_notifications_read(self):
        """Mark all notifications as read"""
        try:
            from django.utils import timezone
            from .models import Notification

            Notification.objects.filter(
                recipient_id=self.user.user_id,
                status__in=['pending', 'sent', 'delivered']
            ).update(
                status='read',
                read_at=timezone.now()
            )
            return True
        except Exception as e:
            logger.error(f"Error marking all notifications as read: {e}")
            return False

    # Utility methods
    async def send_error(self, message):
        """Send error message to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message
        }))

    async def send_success(self, message):
        """Send success message to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'success',
            'message': message
        }))

