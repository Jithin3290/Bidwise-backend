# notifications/signals.py - Enhanced with caching
import json
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Notification, Message, Conversation, ConversationMember
from .services import NotificationService, MessagingService, UserService, CacheManager
import logging

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()


@receiver(post_save, sender=Notification)
def notification_created(sender, instance, created, **kwargs):
    """Send real-time notification when a new notification is created"""
    if created and channel_layer:
        try:
            # Send to user's notification group
            notification_data = {
                'id': str(instance.id),
                'title': instance.title,
                'message': instance.message,
                'type': instance.notification_type.name,
                'priority': instance.priority,
                'status': instance.status,
                'data': instance.data,
                'action_url': instance.action_url,
                'action_text': instance.action_text,
                'created_at': instance.created_at.isoformat(),
            }

            async_to_sync(channel_layer.group_send)(
                f"notifications_{instance.recipient_id}",
                {
                    'type': 'notification_message',
                    'notification': notification_data
                }
            )

            # Invalidate user notification caches
            patterns = [
                f"user_{instance.recipient_id}_notifications_*",
                f"user_{instance.recipient_id}_notification_stats*"
            ]
            for pattern in patterns:
                CacheManager.invalidate_pattern(pattern)

            logger.info(f"Real-time notification sent to user {instance.recipient_id}")

        except Exception as e:
            logger.error(f"Error sending real-time notification: {e}")


@receiver(post_save, sender=Message)
def message_created(sender, instance, created, **kwargs):
    """Send real-time message when a new message is created"""
    if created:
        try:
            # Update conversation timestamp
            from django.utils import timezone
            from django.db.models import F

            instance.conversation.last_message_at = instance.created_at
            instance.conversation.save(update_fields=['last_message_at'])

            # Update unread counts for other participants
            ConversationMember.objects.filter(
                conversation=instance.conversation
            ).exclude(user_id=instance.sender_id).update(
                unread_count=F('unread_count') + 1
            )

            # Send real-time message
            if channel_layer:
                message_data = {
                    'id': str(instance.id),
                    'conversation_id': str(instance.conversation.id),
                    'sender_id': instance.sender_id,
                    'content': instance.content,
                    'message_type': instance.message_type,
                    'reply_to': str(instance.reply_to.id) if instance.reply_to else None,
                    'created_at': instance.created_at.isoformat(),
                    'is_edited': instance.is_edited,
                }

                async_to_sync(channel_layer.group_send)(
                    f"conversation_{instance.conversation.id}",
                    {
                        'type': 'chat_message',
                        'message': message_data
                    }
                )

                # Also send to individual messaging groups for offline users
                for participant_id in instance.conversation.participants:
                    if str(participant_id) != str(instance.sender_id):
                        async_to_sync(channel_layer.group_send)(
                            f"messaging_{participant_id}",
                            {
                                'type': 'chat_message',
                                'message': message_data
                            }
                        )

            # Invalidate relevant caches
            conversation_id = str(instance.conversation.id)

            # Invalidate conversation caches
            conversation_patterns = [
                f"conversation_{conversation_id}_*",
                f"*_conversation_{conversation_id}_*"
            ]
            for pattern in conversation_patterns:
                CacheManager.invalidate_pattern(pattern)

            # Invalidate participant caches
            for participant_id in instance.conversation.participants:
                user_patterns = [
                    f"user_{participant_id}_conversations_*",
                    f"user_{participant_id}_conversation_stats*",
                    f"message_search_{participant_id}_*"
                ]
                for pattern in user_patterns:
                    CacheManager.invalidate_pattern(pattern)

            # Create notification for offline users
            create_message_notification(instance)

            logger.info(f"Message {instance.id} processed successfully")

        except Exception as e:
            logger.error(f"Error processing message {instance.id}: {e}")


@receiver(post_delete, sender=Message)
def message_deleted(sender, instance, **kwargs):
    """Handle message deletion - invalidate caches"""
    try:
        # Invalidate message-specific cache
        cache.delete(f"message_{instance.id}_data")

        # Invalidate conversation caches
        conversation_id = str(instance.conversation.id)
        conversation_patterns = [
            f"conversation_{conversation_id}_*",
            f"*_conversation_{conversation_id}_*"
        ]
        for pattern in conversation_patterns:
            CacheManager.invalidate_pattern(pattern)

        # Invalidate search caches for all participants
        for participant_id in instance.conversation.participants:
            search_pattern = f"message_search_{participant_id}_*"
            CacheManager.invalidate_pattern(search_pattern)

        logger.info(f"Cache invalidated for deleted message {instance.id}")

    except Exception as e:
        logger.error(f"Error handling message deletion cache: {e}")


@receiver(post_save, sender=Conversation)
def conversation_updated(sender, instance, created, **kwargs):
    """Handle conversation updates - invalidate caches"""
    try:
        conversation_id = str(instance.id)

        # Invalidate conversation caches
        conversation_patterns = [
            f"conversation_{conversation_id}_*",
            f"*_conversation_{conversation_id}_*"
        ]
        for pattern in conversation_patterns:
            CacheManager.invalidate_pattern(pattern)

        # Invalidate participant caches
        for participant_id in instance.participants:
            user_patterns = [
                f"user_{participant_id}_conversations_*",
                f"user_{participant_id}_conversation_stats*"
            ]
            for pattern in user_patterns:
                CacheManager.invalidate_pattern(pattern)

        if created:
            logger.info(f"Cache setup for new conversation {conversation_id}")
        else:
            logger.info(f"Cache invalidated for updated conversation {conversation_id}")

    except Exception as e:
        logger.error(f"Error handling conversation cache update: {e}")


def create_message_notification(message):
    """Create notification for new message"""
    try:
        from .models import NotificationType

        conversation = message.conversation
        other_participants = [
            p for p in conversation.participants
            if str(p) != str(message.sender_id)
        ]

        # Get notification type (with caching)
        notif_type_cache_key = "notification_type_new_message"
        notification_type = cache.get(notif_type_cache_key)
        if not notification_type:
            notification_type = NotificationType.objects.get(name='new_message')
            cache.set(notif_type_cache_key, notification_type, timeout=3600)

        # Get sender info (cached in UserService)
        user_service = UserService()
        sender_info = user_service.get_user_profile(message.sender_id)
        sender_name = sender_info.get('username', 'Someone') if sender_info else 'Someone'

        # Create notification for each participant
        for participant_id in other_participants:
            Notification.objects.create(
                recipient_id=str(participant_id),
                notification_type=notification_type,
                title='New Message',
                message=f'{sender_name}: {message.content[:100]}{"..." if len(message.content) > 100 else ""}',
                data={
                    'conversation_id': str(conversation.id),
                    'message_id': str(message.id),
                    'sender_id': str(message.sender_id),
                    'sender_name': sender_name,
                    'conversation_title': conversation.title or 'Direct Message'
                },
                action_url=f'/messages/{conversation.id}',
                action_text='View Message',
                priority='normal'
            )

    except Exception as e:
        logger.error(f"Error creating message notification: {e}")
