from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import timedelta
import logging
import requests

User = get_user_model()
logger = logging.getLogger(__name__)



@shared_task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 60})
def send_welcome_email_task(self, user_id):
    """Send welcome email to new users"""
    try:
        user = User.objects.get(id=user_id)

        subject = "Welcome to Our Platform!"
        message = f"""
Hi {user.full_name or user.username},

Welcome to our platform! We're excited to have you join our community.

Here are some next steps to get you started:
1. Complete your profile
2. Verify your email address
3. Explore available opportunities

If you have any questions, feel free to contact our support team.

Best regards,
BidWise Team
        """

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )

        return f"Welcome email sent to {user.email}"

    except User.DoesNotExist:
        logger.error(f"User with ID {user_id} not found")
        return f"User with ID {user_id} not found"
    except Exception as e:
        logger.error(f"Failed to send welcome email to user {user_id}: {str(e)}")
        raise self.retry(exc=e)


@shared_task
def send_password_reset_email_task(user_id, reset_link):
    """Send password reset email"""
    try:
        user = User.objects.get(id=user_id)

        subject = "Password Reset Request"
        message = f"""
Hi {user.full_name or user.username},

You requested a password reset. Click the link below to reset your password:

{reset_link}

This link will expire in 1 hour.

If you didn't request this reset, please ignore this email.

Best regards,
BidWise
        """

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )

        return f"Password reset email sent to {user.email}"

    except Exception as e:
        logger.error(f"Failed to send password reset email: {str(e)}")
        return f"Error: {str(e)}"


# Profile Processing Tasks
@shared_task
def process_profile_picture_task(user_id, image_url):
    """Process and save profile picture from URL"""
    try:
        from .views import save_profile_picture_from_url
        user = User.objects.get(id=user_id)
        save_profile_picture_from_url(user, image_url)
        return f"Profile picture processed for user {user.email}"
    except Exception as e:
        logger.error(f"Failed to process profile picture for user {user_id}: {str(e)}")
        return f"Error: {str(e)}"


@shared_task
def update_profile_completion_task(user_id):
    """Update user profile completion percentage"""
    try:
        user = User.objects.get(id=user_id)
        percentage = user.calculate_profile_completion()
        user.save(update_fields=['profile_completion_percentage'])
        return f"Profile completion updated to {percentage}% for user {user.email}"
    except Exception as e:
        logger.error(f"Failed to update profile completion for user {user_id}: {str(e)}")
        return f"Error: {str(e)}"


# Notification Tasks
@shared_task
def send_notification_email_task(user_id, subject, message):
    """Send general notification email to user"""
    try:
        user = User.objects.get(id=user_id)

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )

        return f"Notification email sent to {user.email}"

    except Exception as e:
        logger.error(f"Failed to send notification email: {str(e)}")
        return f"Error: {str(e)}"


# Cleanup Tasks
@shared_task
def cleanup_expired_verification_tokens():
    """Clean up expired email verification tokens"""
    try:
        from .models import UserSecurity

        cutoff_time = timezone.now()
        expired_tokens = UserSecurity.objects.filter(
            email_verification_expires__lt=cutoff_time
        ).exclude(email_verification_token='')

        count = expired_tokens.count()
        expired_tokens.update(
            email_verification_token='',
            email_verification_expires=None
        )

        return f"Cleaned up {count} expired verification tokens"

    except Exception as e:
        logger.error(f"Failed to cleanup expired tokens: {str(e)}")
        return f"Error: {str(e)}"


@shared_task
def cleanup_locked_accounts():
    """Unlock accounts that have passed the lock duration"""
    try:
        from .models import UserSecurity

        now = timezone.now()
        locked_accounts = UserSecurity.objects.filter(
            account_locked_until__lt=now
        ).exclude(account_locked_until__isnull=True)

        count = locked_accounts.count()
        locked_accounts.update(
            account_locked_until=None,
            login_attempts=0
        )

        return f"Unlocked {count} accounts"

    except Exception as e:
        logger.error(f"Failed to cleanup locked accounts: {str(e)}")
        return f"Error: {str(e)}"


# Analytics and Reporting Tasks
@shared_task
def generate_user_activity_report():
    """Generate daily user activity report"""
    try:
        yesterday = timezone.now() - timedelta(days=1)

        # Get user statistics
        total_users = User.objects.count()
        new_users = User.objects.filter(created_at__date=yesterday.date()).count()
        verified_users = User.objects.filter(is_verified=True).count()
        active_users = User.objects.filter(last_activity__date=yesterday.date()).count()

        # Create report
        report = f"""
Daily User Activity Report - {yesterday.strftime('%Y-%m-%d')}

Total Users: {total_users}
New Users: {new_users}
Verified Users: {verified_users}
Active Users: {active_users}
Verification Rate: {(verified_users / total_users * 100):.1f}%
        """

        # You can send this to admins or save to database
        logger.info(report)
        return f"User activity report generated for {yesterday.date()}"

    except Exception as e:
        logger.error(f"Failed to generate user activity report: {str(e)}")
        return f"Error: {str(e)}"


@shared_task
def send_verification_reminder_emails():
    """Send reminder emails to unverified users"""
    try:
        # Find users who registered more than 3 days ago but haven't verified
        cutoff_date = timezone.now() - timedelta(days=3)
        unverified_users = User.objects.filter(
            is_verified=False,
            created_at__lt=cutoff_date,
            is_active=True
        )

        count = 0
        for user in unverified_users:
            subject = "Please verify your email address"
            message = f"""
Hi {user.full_name or user.username},

We noticed you haven't verified your email address yet. 

To complete your registration and access all features, please verify your email address by requesting a new verification code.

Best regards,
Your App Team
            """

            send_notification_email_task.delay(user.id, subject, message)
            count += 1

        return f"Sent verification reminders to {count} users"

    except Exception as e:
        logger.error(f"Failed to send verification reminders: {str(e)}")
        return f"Error: {str(e)}"


@shared_task
def bulk_update_profile_completions():
    """Update profile completion for all users (maintenance task)"""
    try:
        users = User.objects.all()
        count = 0

        for user in users:
            old_percentage = user.profile_completion_percentage
            new_percentage = user.calculate_profile_completion()

            if old_percentage != new_percentage:
                user.save(update_fields=['profile_completion_percentage'])
                count += 1

        return f"Updated profile completion for {count} users"

    except Exception as e:
        logger.error(f"Failed to bulk update profile completions: {str(e)}")
        return f"Error: {str(e)}"


@shared_task
def sync_user_data_with_jobs_service(user_id):
    """Sync user profile changes with jobs service"""
    try:
        user = User.objects.get(id=user_id)

        # Prepare user data for sync
        user_data = {
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'profile_picture': user.profile_picture.url if user.profile_picture else None,
            'is_verified': user.is_verified,
            'last_activity': user.last_activity.isoformat() if user.last_activity else None,
        }

        # Make API call to jobs service to update cached user data
        jobs_service_url = getattr(settings, 'JOBS_SERVICE_URL', 'http://jobs_service:8000')
        service_token = getattr(settings, 'SERVICE_TOKEN', 'secure-service-token-123')

        response = requests.post(
            f"{jobs_service_url}/api/internal/sync-user-data/",
            json=user_data,
            headers={
                'Authorization': f'Bearer {service_token}',
                'Content-Type': 'application/json'
            },
            timeout=10
        )

        if response.status_code == 200:
            return f"User data synced successfully for {user.email}"
        else:
            logger.warning(f"Failed to sync user data: {response.status_code}")
            return f"Sync failed with status {response.status_code}"

    except Exception as e:
        logger.error(f"Failed to sync user data: {str(e)}")
        return f"Error: {str(e)}"


# users/tasks.py

from celery import shared_task
import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def trigger_freelancer_indexing(self, user_id, action="index"):
    """
    Async task to trigger AI service indexing.
    Safely disabled if AI service is not configured.
    """
    ai_service_url = getattr(settings, "AI_SCORING_SERVICE_URL", None)

    if not ai_service_url:
        logger.info(
            "AI_SCORING_SERVICE_URL not configured. "
            "Skipping freelancer indexing for user %s.",
            user_id,
        )
        return {
            "status": "skipped",
            "reason": "AI service not configured",
            "user_id": user_id,
        }

    try:
        if action == "index":
            url = f"{ai_service_url}/api/scoring/index-freelancer/"
        elif action == "delete":
            url = f"{ai_service_url}/api/scoring/delete-freelancer/"
        else:
            raise ValueError(f"Invalid action: {action}")

        response = requests.post(
            url,
            json={"user_id": user_id},
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {getattr(settings, 'SERVICE_TOKEN', '')}",
            },
            timeout=10,
        )

        if response.status_code == 200:
            logger.info("AI indexing successful for user %s", user_id)
            return {"status": "success", "user_id": user_id}

        logger.warning(
            "AI indexing failed for user %s. Status=%s Body=%s",
            user_id,
            response.status_code,
            response.text,
        )
        return {
            "status": "failed",
            "user_id": user_id,
            "http_status": response.status_code,
        }

    except Exception as exc:
        logger.exception("Unexpected error in AI indexing task for user %s", user_id)
        return {
            "status": "error",
            "user_id": user_id,
            "error": str(exc),
        }
