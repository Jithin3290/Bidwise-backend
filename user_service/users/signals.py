# users/signals.py (Celery version)

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import FreelancerProfile, UserProfessionalProfile, User, UserAccountType
from .tasks import trigger_freelancer_indexing
import logging
from django.conf import settings
import requests
logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def auto_add_admin_account_type_for_superuser(sender, instance, created, **kwargs):
    """Automatically add 'admin' account type when a superuser is created or updated"""
    if instance.is_superuser:
        # Check if admin account type already exists
        admin_exists = UserAccountType.objects.filter(
            user=instance, 
            account_type='admin'
        ).exists()
        
        if not admin_exists:
            UserAccountType.objects.create(
                user=instance,
                account_type='admin',
                is_primary=True
            )
            logger.info(f"Auto-added 'admin' account type for superuser: {instance.email}")


def trigger_ai_indexing(user_id):
    """Direct HTTP call to AI service"""
    logger.info(f" Starting AI indexing for user {user_id}")

    try:
        url = f"{settings.AI_SCORING_SERVICE_URL}/api/scoring/index-freelancer/"
        logger.info(f"  Calling: {url}")

        response = requests.post(
            url,
            json={'user_id': user_id},
            headers={'Content-Type': 'application/json'},
            timeout=30
        )

        logger.info(f"Response status: {response.status_code}")
        logger.info(f" Response body: {response.text}")

        if response.status_code == 200:
            logger.info(f"✓ AI indexing successful for user {user_id}")
        else:
            logger.error(f"✗ AI indexing failed: {response.text}")

    except Exception as e:
        logger.error(f" Error calling AI service: {e}")
        import traceback
        traceback.print_exc()


@receiver(post_save, sender=FreelancerProfile)
def index_freelancer_on_profile_save(sender, instance, **kwargs):
    logger.info(f" Signal fired for user {instance.user_id}")
    trigger_ai_indexing(instance.user_id)

@receiver(post_save, sender=UserProfessionalProfile)
def reindex_on_professional_profile_update(sender, instance, created, **kwargs):
    """Re-index on professional profile update"""
    try:
        if hasattr(instance.user, 'freelancer_profile'):
            transaction.on_commit(
                lambda: trigger_freelancer_indexing.delay(instance.user_id, action='index')
            )
    except Exception as e:
        logger.error(f"Error queuing professional profile indexing: {e}")