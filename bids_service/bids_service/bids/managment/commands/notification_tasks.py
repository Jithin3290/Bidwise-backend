# Create this file: bids/management/commands/notification_tasks.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import logging

from bids.services import enhanced_notification_service
from bids.signals import send_bulk_bid_notifications
from bids.models import Bid

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run notification-related tasks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--task',
            type=str,
            help='Notification task to run',
            choices=['retry_failed', 'send_reminders', 'cleanup', 'all'],
            default='all'
        )

        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run in dry-run mode (don\'t actually send notifications)',
        )

    def handle(self, *args, **options):
        task = options['task']
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(
                self.style.WARNING('Running in DRY-RUN mode - no notifications will be sent')
            )

        if task == 'retry_failed' or task == 'all':
            self.retry_failed_notifications(dry_run)

        if task == 'send_reminders' or task == 'all':
            self.send_reminder_notifications(dry_run)

        if task == 'cleanup' or task == 'all':
            self.cleanup_old_cache_entries(dry_run)

    def retry_failed_notifications(self, dry_run=False):
        """Retry failed notifications"""
        self.stdout.write('Retrying failed notifications...')

        try:
            if not dry_run:
                success_count = enhanced_notification_service.retry_failed_notifications()
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully retried {success_count} notifications')
                )
            else:
                from django.core.cache import cache
                failed_notifications = cache.get('failed_notifications', [])
                self.stdout.write(f'Would retry {len(failed_notifications)} failed notifications')

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error retrying failed notifications: {e}')
            )

    def send_reminder_notifications(self, dry_run=False):
        """Send reminder notifications for expiring bids"""
        self.stdout.write('Sending reminder notifications...')

        try:
            # Get bids expiring in the next 24 hours
            tomorrow = timezone.now() + timedelta(hours=24)
            expiring_bids = Bid.objects.filter(
                status='pending',
                expires_at__lte=tomorrow,
                expires_at__gt=timezone.now()
            )

            self.stdout.write(f'Found {expiring_bids.count()} bids expiring soon')

            if not dry_run and expiring_bids.exists():
                results = send_bulk_bid_notifications(
                    expiring_bids,
                    'bid_deadline_reminder'
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Sent reminders: {results["success"]} success, {results["failed"]} failed'
                    )
                )
            elif dry_run:
                self.stdout.write(f'Would send {expiring_bids.count()} reminder notifications')

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error sending reminder notifications: {e}')
            )

    def cleanup_old_cache_entries(self, dry_run=False):
        """Clean up old cache entries"""
        self.stdout.write('Cleaning up old cache entries...')

        try:
            from django.core.cache import cache

            # Clean up old failed notifications (older than 7 days)
            failed_notifications = cache.get('failed_notifications', [])
            week_ago = timezone.now() - timedelta(days=7)

            old_count = 0
            if failed_notifications:
                cleaned_notifications = []
                for notification in failed_notifications:
                    notification_time = timezone.datetime.fromisoformat(
                        notification['timestamp'].replace('Z', '+00:00')
                    )
                    if notification_time > week_ago:
                        cleaned_notifications.append(notification)
                    else:
                        old_count += 1

                if not dry_run:
                    cache.set('failed_notifications', cleaned_notifications, timeout=86400)

            self.stdout.write(f'Cleaned up {old_count} old failed notification entries')

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error cleaning up cache: {e}')
            )