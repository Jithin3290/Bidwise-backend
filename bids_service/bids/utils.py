from decimal import Decimal

from django.conf import settings
from django.db.models import F
from django.utils import timezone
from rest_framework import serializers

from .models import BidView, Bid, FreelancerBidProfile
import logging

from .services import UserService, JobService

logger = logging.getLogger(__name__)


# ============= UTILITY FUNCTIONS =============

def get_client_ip(request):
    """Get client IP address"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def track_bid_view(bid, request):
    """Track bid view for analytics"""
    try:
        viewer_id = getattr(request.user, 'user_id', None)
        ip_address = get_client_ip(request)

        # Only track if it's a different user viewing
        if viewer_id != bid.freelancer_id:
            BidView.objects.create(
                bid=bid,
                viewer_id=viewer_id,
                ip_address=ip_address,
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )

            # Update view count
            Bid.objects.filter(id=bid.id).update(views_count=F('views_count') + 1)

    except Exception as e:
        logger.error(f"Error tracking bid view: {e}")


def update_freelancer_profile_cache(freelancer_id):
    """Update cached freelancer profile data"""
    try:
        user_service = UserService()
        job_service = JobService()

        # Get user data from Users Service
        user_data = user_service.get_user_profile(freelancer_id)
        if not user_data:
            return None

        # Calculate bid statistics
        bids = Bid.objects.filter(freelancer_id=freelancer_id)
        total_bids = bids.count()
        accepted_bids = bids.filter(status='accepted').count()

        # Update or create profile
        profile, created = FreelancerBidProfile.objects.get_or_create(
            freelancer_id=freelancer_id,
            defaults={
                'cache_expires_at': timezone.now() + timezone.timedelta(hours=6)
            }
        )

        # Update profile data
        profile.username = user_data.get('username', '')
        profile.first_name = user_data.get('first_name', '')
        profile.last_name = user_data.get('last_name', '')
        profile.profile_picture_url = user_data.get('profile_picture', '')
        profile.location = user_data.get('location', '')
        profile.title = user_data.get('title', '')
        profile.bio = user_data.get('bio', '')
        profile.skills = user_data.get('skills', [])
        profile.hourly_rate = user_data.get('hourly_rate')
        profile.is_verified = user_data.get('is_verified', False)
        profile.is_premium = user_data.get('is_premium', False)

        # Update statistics
        profile.total_bids = total_bids
        profile.accepted_bids = accepted_bids
        if total_bids > 0:
            profile.acceptance_rate = (accepted_bids / total_bids) * 100

        profile.cache_expires_at = timezone.now() + timezone.timedelta(hours=6)
        profile.save()

        return profile

    except Exception as e:
        logger.error(f"Error updating freelancer profile cache: {e}")
        return None


def check_bid_permission(request, job_id):
    """Check if user can bid on this job"""
    logger.info(f"=== CHECKING BID PERMISSION ===")
    logger.info(f"Job ID: {job_id}")
    logger.info(f"User ID: {getattr(request.user, 'user_id', 'NOT SET')}")

    try:
        from .services import JobService

        job_service = JobService()

        # First test the service connection
        connection_test = job_service.test_connection()
        logger.info(f"Job service connection test: {connection_test}")

        job_data = job_service.get_job_details(job_id)
        logger.info(f"Job data retrieved: {job_data is not None}")

        if not job_data:
            logger.error(f"Job {job_id} not found in job service")

            # Additional debugging: try to list available jobs
            try:
                import requests
                list_url = f"{job_service.base_url}/api/jobs/"
                response = requests.get(list_url, timeout=10)
                if response.status_code == 200:
                    jobs = response.json().get('results', [])
                    available_ids = [job.get('id') for job in jobs[:5]]
                    logger.info(f"Available job IDs (first 5): {available_ids}")
                else:
                    logger.error(f"Failed to list jobs: {response.status_code}")
            except Exception as e:
                logger.error(f"Error listing jobs: {e}")

            return False, f"Job {job_id} not found"

        # Log job details
        logger.info(f"Job found - Title: {job_data.get('title', 'N/A')}")
        logger.info(f"Job status: {job_data.get('status', 'N/A')}")
        logger.info(f"Job client_info: {job_data.get('client_info', {})}")

        # Check job status
        status = job_data.get('status')
        if status != 'published':
            return False, f"Job is not available for bidding (status: {status})"

        # Get client ID from client_info object
        client_info = job_data.get('client_info', {})
        client_id = client_info.get('id')

        if not client_id:
            logger.error(f"Job client information not found for job {job_id}")
            logger.error(f"Full job data: {job_data}")
            return False, f"Job client information not found"

        logger.info(f"Job validation: status={status}, client_id={client_id}")

        # Use user_id from JWT authentication
        user_id = str(request.user.user_id)
        logger.info(f"Requesting user ID: {user_id}")

        # Check if user is the job owner
        if user_id == str(client_id):
            return False, "Cannot bid on your own job"

        # Check for existing bid
        from .models import Bid
        existing_bid = Bid.objects.filter(
            job_id=job_id,
            freelancer_id=user_id
        ).first()

        if existing_bid:
            return False, f"You have already submitted a bid for this job"

        # Get account types from JWT token
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        account_types = []

        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            try:
                import jwt
                from django.conf import settings
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
                account_types = payload.get('account_types', [])
                logger.info(f"User account types: {account_types}")
            except jwt.InvalidTokenError as e:
                logger.error(f"Invalid JWT token: {e}")
                pass

        if 'freelancer' not in account_types:
            return False, f"Only freelancers can submit bids. Your account types: {account_types}"

        logger.info(f"Bid permission granted for user {user_id} on job {job_id}")
        return True, None

    except Exception as e:
        logger.error(f"Error checking bid permission: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False, f"Error validating bid permission: {str(e)}"


def validate_positive(value, field_name="Value"):
    if value is None or Decimal(str(value)) <= 0:
        raise serializers.ValidationError(f"{field_name} must be greater than 0")
    return value

def validate_proposal_length(value):
    min_length = getattr(settings, 'MIN_PROPOSAL_LENGTH', 50)
    max_length = getattr(settings, 'MAX_PROPOSAL_LENGTH', 5000)
    value = value.strip()
    if len(value) < min_length:
        raise serializers.ValidationError(f"Proposal must be at least {min_length} characters long")
    if len(value) > max_length:
        raise serializers.ValidationError(f"Proposal cannot exceed {max_length} characters")
    return value
