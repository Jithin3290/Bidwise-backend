
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import Message, Conversation, ConversationMember
from .services import MessagingService
import logging

logger = logging.getLogger(__name__)


@shared_task
def cleanup_old_messages():
    """Clean up old deleted messages"""
    try:
        # Delete messages that have been marked as deleted for more than 30 days
        cutoff_date = timezone.now() - timedelta(days=30)

        old_messages = Message.objects.filter(
            is_deleted=True,
            updated_at__lt=cutoff_date
        )

        count = old_messages.count()
        old_messages.delete()

        logger.info(f"Cleaned up {count} old deleted messages")
        return f"Cleaned up {count} messages"

    except Exception as e:
        logger.error(f"Error cleaning up old messages: {e}")
        raise


@shared_task
def update_user_status(user_id, status):
    """Update user online/offline status"""
    try:
        messaging_service = MessagingService()
        messaging_service.notify_user_status_change(user_id, status)

        logger.info(f"Updated user {user_id} status to {status}")

    except Exception as e:
        logger.error(f"Error updating user status: {e}")
        raise


@shared_task
def send_offline_message_notifications():
    """Send notifications for messages to offline users"""
    try:
        from .models import Notification, NotificationType

        # Get users with unread messages who haven't been online recently
        cutoff_time = timezone.now() - timedelta(minutes=15)

        offline_members = ConversationMember.objects.filter(
            unread_count__gt=0,
            last_seen_at__lt=cutoff_time
        ).select_related('conversation')

        notification_type = NotificationType.objects.get(name='new_message')

        for member in offline_members:
            # Check if notification already exists
            existing = Notification.objects.filter(
                recipient_id=member.user_id,
                notification_type=notification_type,
                data__conversation_id=str(member.conversation.id),
                status__in=['pending', 'sent', 'delivered']
            ).exists()

            if not existing:
                Notification.objects.create(
                    recipient_id=member.user_id,
                    notification_type=notification_type,
                    title=f'You have {member.unread_count} unread message(s)',
                    message=f'New messages in "{member.conversation.title}"',
                    data={
                        'conversation_id': str(member.conversation.id),
                        'unread_count': member.unread_count
                    },
                    action_url=f'/messages/{member.conversation.id}',
                    action_text='View Messages',
                    priority='normal'
                )

        logger.info(f"Sent offline notifications to {offline_members.count()} users")

    except Exception as e:
        logger.error(f"Error sending offline notifications: {e}")
        raise