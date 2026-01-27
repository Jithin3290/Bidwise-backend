# bids/signals.py - Updated to use NotificationServiceClient

import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Bid
from .services import notification_client  # Use the simple HTTP client

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Bid)
def handle_bid_created(sender, instance, created, **kwargs):
    """Handle bid creation notification"""
    if not created:
        return

    try:
        # Send bid created notification via HTTP to notification service
        success = notification_client.send_bid_created_notification(instance)

        if success:
            logger.info(f"Bid created notification sent for bid {instance.id}")
        else:
            logger.error(f"Failed to send bid created notification for bid {instance.id}")

    except Exception as e:
        logger.error(f"Error in bid created signal: {e}")


@receiver(pre_save, sender=Bid)
def handle_bid_status_change(sender, instance, **kwargs):
    """Handle bid status change notifications"""
    if not instance.pk:
        return

    try:
        # Get the old instance to compare status
        old_instance = Bid.objects.get(pk=instance.pk)

        # Check if status actually changed
        if old_instance.status == instance.status:
            return

        # Only send notifications for certain status changes
        if instance.status in ['accepted', 'rejected']:
            # Add timestamps for status changes
            if instance.status == 'accepted' and not instance.accepted_at:
                instance.accepted_at = timezone.now()
            elif instance.status == 'rejected' and not instance.rejected_at:
                instance.rejected_at = timezone.now()

            # Flag that status changed for post_save signal
            instance._status_changed = True
            instance._old_status = old_instance.status

    except Bid.DoesNotExist:
        # This is a new bid, handled by post_save
        pass
    except Exception as e:
        logger.error(f"Error in bid status change signal: {e}")


@receiver(post_save, sender=Bid)
def handle_bid_status_notification(sender, instance, created, **kwargs):
    """Send notification after bid status change is saved"""
    if created:
        return

    try:
        # Check if status was changed
        if hasattr(instance, '_status_changed') and instance._status_changed:
            success = notification_client.send_bid_status_notification(instance)

            if success:
                logger.info(f"Bid status notification sent for bid {instance.id} - status: {instance.status}")
            else:
                logger.error(f"Failed to send bid status notification for bid {instance.id}")

            # Clean up the temporary flag
            if hasattr(instance, '_status_changed'):
                delattr(instance, '_status_changed')
            if hasattr(instance, '_old_status'):
                delattr(instance, '_old_status')

    except Exception as e:
        logger.error(f"Error in bid status notification signal: {e}")


def handle_bid_viewed(bid, viewer_user_id):
    """Handle bid viewed notification (call this from your view)"""
    try:
        # Only notify if the viewer is the client (job owner)
        from .services import job_service
        job_data = job_service.get_job_details(bid.job_id)

        if job_data and str(job_data.get('client_info', {}).get('id')) == str(viewer_user_id):
            # Only send notification if this is the first view
            if not bid.client_viewed_at:
                success = notification_client.send_bid_viewed_notification(bid)

                if success:
                    logger.info(f"Bid viewed notification sent for bid {bid.id}")
                else:
                    logger.error(f"Failed to send bid viewed notification for bid {bid.id}")

    except Exception as e:
        logger.error(f"Error in bid viewed notification: {e}")


def send_bulk_bid_notifications(bids, notification_type, **extra_data):
    """Send bulk notifications for multiple bids"""
    try:
        success_count = 0
        failed_count = 0

        for bid in bids:
            if notification_type == 'bid_deadline_reminder':
                notification_data = {
                    'recipient_id': bid.freelancer_id,
                    'notification_type': 'bid_deadline_reminder',
                    'title': 'Bid Deadline Reminder',
                    'message': f'Your bid expires in 24 hours',
                    'priority': 'normal',
                    'data': {
                        'bid_id': str(bid.id),
                        'job_id': bid.job_id,
                        'expires_at': bid.expires_at.isoformat() if bid.expires_at else None,
                        'service': 'bids'
                    },
                    'action_text': 'View Bid'
                }

                if notification_client.send_notification(notification_data):
                    success_count += 1
                else:
                    failed_count += 1

        results = {'success': success_count, 'failed': failed_count}
        logger.info(f"Bulk bid notifications sent: {results}")
        return results

    except Exception as e:
        logger.error(f"Error sending bulk bid notifications: {e}")
        return {'success': 0, 'failed': len(bids)}