# bids/services.py
import logging
import time
from datetime import timedelta

import jwt
import requests
from django.conf import settings
from django.core.cache import cache
from typing import Optional, Dict, Any, List

from django.utils import timezone

logger = logging.getLogger(__name__)


class UserService:
    """Service to communicate with Users microservice"""

    def __init__(self):
        self.base_url = getattr(settings, 'USERS_SERVICE_URL', 'http://users_service:8000')
        self.service_token = getattr(settings, 'SERVICE_TOKEN', 'secure-service-token-123')
        self.timeout = 10

    def _get_headers(self):
        return {
            'Authorization': f'Bearer {self.service_token}',
            'Content-Type': 'application/json'
        }

    def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user profile from Users Service"""
        cache_key = f'user_profile_{user_id}'
        cached_data = cache.get(cache_key)

        if cached_data:
            return cached_data

        try:
            url = f"{self.base_url}/api/service/users/{user_id}/profile/"
            response = requests.get(
                url,
                headers=self._get_headers(),
                timeout=self.timeout
            )

            if response.status_code == 200:
                data = response.json()
                cache.set(cache_key, data, 300)  # Cache for 5 minutes
                return data
            else:
                logger.error(f"Failed to fetch user {user_id}: {response.status_code}")
                return None

        except requests.RequestException as e:
            logger.error(f"Error fetching user {user_id}: {e}")
            return None

    def get_users_batch(self, user_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get multiple users in batch"""
        if not user_ids:
            return {}

        users_data = {}
        uncached_ids = []

        # Check cache first
        for user_id in user_ids:
            cache_key = f'user_profile_{user_id}'
            cached_data = cache.get(cache_key)
            if cached_data:
                users_data[str(user_id)] = cached_data
            else:
                uncached_ids.append(user_id)

        # Fetch uncached users
        if uncached_ids:
            try:
                url = f"{self.base_url}/api/service/users/batch/"
                response = requests.post(
                    url,
                    json={'user_ids': uncached_ids},
                    headers=self._get_headers(),
                    timeout=self.timeout
                )

                if response.status_code == 200:
                    fetched_users = response.json().get('users', [])
                    for user in fetched_users:
                        user_id = str(user['id'])
                        users_data[user_id] = user
                        cache.set(f'user_profile_{user_id}', user, 300)
                else:
                    logger.error(f"Batch user fetch failed: {response.status_code}")

            except requests.RequestException as e:
                logger.error(f"Error in batch user fetch: {e}")

        return users_data


class JobService:
    """Service to communicate with Jobs microservice"""

    def __init__(self):
        self.base_url = getattr(settings, 'JOBS_SERVICE_URL', 'http://127.0.0.1:8001')
        self.service_token = getattr(settings, 'SERVICE_TOKEN', 'secure-service-token-123')
        self.timeout = 10

    def _get_headers(self):
        return {
            'Authorization': f'Bearer {self.service_token}',
            'Content-Type': 'application/json'
        }

    def get_job_details(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job details from Jobs Service"""
        cache_key = f'job_details_{job_id}'
        cached_data = cache.get(cache_key)

        if cached_data:
            return cached_data

        try:
            url = f"{self.base_url}/api/jobs/{job_id}/"
            response = requests.get(
                url,
                # headers=self._get_headers(),
                timeout=self.timeout
            )

            if response.status_code == 200:
                data = response.json()
                cache.set(cache_key, data, 600)  # Cache for 10 minutes
                return data
            else:
                logger.error(f"Failed to fetch job {job_id}: {response.status_code}")
                return None

        except requests.RequestException as e:
            logger.error(f"Error fetching job {job_id}: {e}")
            return None

    def get_client_jobs(self, client_id: str) -> List[Dict[str, Any]]:
        """Get all jobs for a client"""
        try:
            # Use the public jobs list endpoint with client filter
            url = f"{self.base_url}/api/jobs/"
            params = {
                'client': client_id,  # Filter by client ID
                'ordering': '-created_at'  # Latest jobs first
            }
            logger.info(client_id,"from service")
            # Remove authentication since jobs service allows public access to job listings
            response = requests.get(
                url,
                params=params,
                timeout=self.timeout
            )

            if response.status_code == 200:
                jobs_data = response.json()
                return jobs_data.get('results', [])
            else:
                logger.error(f"Failed to fetch client jobs: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return []

        except requests.RequestException as e:
            logger.error(f"Error fetching client jobs: {e}")
            return []

    def update_job_applications_count(self, job_id: str, count: int):
        """Update job's applications count"""
        try:
            url = f"{self.base_url}/api/jobs/service/update-stats/"
            response = requests.patch(
                url,
                json={
                    'job_id': job_id,
                    'applications_count': count
                },
                # headers=self._get_headers(),
                timeout=self.timeout
            )

            if response.status_code != 200:
                logger.error(f"Failed to update job stats: {response.status_code}")

        except requests.RequestException as e:
            logger.error(f"Error updating job stats: {e}")

    def test_connection(self):
        # simple ping to jobs service
        response = requests.get(f"{self.base_url}/health/")
        return response.status_code == 200

import logging
import requests
import jwt
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from typing import Dict, Any

logger = logging.getLogger(__name__)


class NotificationServiceClient:
    """Client for communicating with the notification service"""

    def __init__(self):
        self.base_url = getattr(settings, 'NOTIFICATION_SERVICE_URL', 'http://localhost:8003')
        self.service_token = getattr(settings, 'SERVICE_TOKEN', 'secure-service-token-123')
        self.timeout = 10
        self.max_retries = 3

    def _get_service_jwt_token(self):
        """Generate JWT token for service-to-service communication"""
        payload = {
            'service': 'bids_service',
            'service_type': 'microservice',
            'iat': int(timezone.now().timestamp()),
            'exp': int((timezone.now() + timedelta(hours=24)).timestamp()),
            'sub': 'service_communication'
        }
        secret_key = getattr(settings, 'SECRET_KEY')
        token = jwt.encode(payload, secret_key, algorithm='HS256')
        return token

    def _get_headers(self):
        return {
            "Host": "localhost",
            "Authorization": f"Bearer secure-service-token-123",
            "Content-Type": "application/json"
        }

    def send_notification(self, notification_data: Dict[str, Any]) -> bool:
        """Send notification to notification service"""
        try:
            url = f"{self.base_url}/api/notifications/create/"
            logger.info(f"Sending notification: {notification_data['title']} -> {notification_data['recipient_id']}")
            logger.info(f"URL: {url}")
            logger.info(f"Headers: {self._get_headers()}")
            logger.info(f"Payload: {notification_data}")

            response = requests.post(
                url,
                json=notification_data,
                headers=self._get_headers(),
                timeout=self.timeout
            )

            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Response content: {response.text}")

            if response.status_code == 201:
                logger.info(f"✓ Notification sent successfully")
                return True
            else:
                logger.error(f"✗ Failed to send notification: {response.status_code} - {response.text}")
                return False

        except requests.RequestException as e:
            logger.error(f"✗ Request error: {e}")
            return False

    def send_bid_created_notification(self, bid) -> bool:
        """Send notification when a new bid is created"""
        try:
            from .services import JobService  # Import here to avoid circular imports
            job_service = JobService()
            job_data = job_service.get_job_details(bid.job_id)

            if not job_data:
                logger.error(f"Job {bid.job_id} not found for bid notification")
                return False

            client_id = job_data.get('client_info', {}).get('id')
            if not client_id:
                logger.error(f"Client ID not found in job {bid.job_id}")
                return False

            notification_data = {
                'recipient_id': str(client_id),
                'notification_type': 'bid_created',
                'title': 'New Bid Received',
                'message': f'You received a new bid on your job "{job_data.get("title", "")}"',
                'priority': 'normal',
                'data': {
                    'bid_id': str(bid.id),
                    'job_id': bid.job_id,
                    'job_title': job_data.get('title', ''),
                    'freelancer_id': bid.freelancer_id,
                    'bid_amount': str(bid.amount) if bid.amount else None,
                    'bid_type': bid.bid_type,
                    'estimated_delivery': bid.estimated_delivery,
                    'service': 'bids'
                },
                'action_text': 'View Bid'
            }

            return self.send_notification(notification_data)

        except Exception as e:
            logger.error(f"Error creating bid notification: {e}")
            return False

    def send_bid_status_notification(self, bid) -> bool:
        """Send notification when bid status changes"""
        try:
            if bid.status not in ['accepted', 'rejected']:
                return True

            from .services import JobService
            job_service = JobService()
            job_data = job_service.get_job_details(bid.job_id)
            job_title = job_data.get('title', '') if job_data else ''

            status_messages = {
                'accepted': f'Congratulations! Your bid on "{job_title}" has been accepted.',
                'rejected': f'Your bid on "{job_title}" was not selected this time.'
            }

            status_titles = {
                'accepted': 'Bid Accepted',
                'rejected': 'Bid Not Selected'
            }

            notification_data = {
                'recipient_id': bid.freelancer_id,
                'notification_type': f'bid_{bid.status}',
                'title': status_titles.get(bid.status, f'Bid {bid.status.title()}'),
                'message': status_messages.get(bid.status, f'Your bid status has been updated to {bid.status}'),
                'priority': 'high' if bid.status == 'accepted' else 'normal',
                'data': {
                    'bid_id': str(bid.id),
                    'job_id': bid.job_id,
                    'job_title': job_title,
                    'status': bid.status,
                    'client_feedback': getattr(bid, 'client_feedback', '') or '',
                    'service': 'bids'
                },
                'action_text': 'View Details'
            }

            return self.send_notification(notification_data)

        except Exception as e:
            logger.error(f"Error creating bid status notification: {e}")
            return False

    def send_bid_viewed_notification(self, bid) -> bool:
        """Send notification when client views bid"""
        try:
            notification_data = {
                'recipient_id': bid.freelancer_id,
                'notification_type': 'bid_viewed',
                'title': 'Bid Viewed',
                'message': 'A client has viewed your bid',
                'priority': 'low',
                'data': {
                    'bid_id': str(bid.id),
                    'job_id': bid.job_id,
                    'viewed_at': timezone.now().isoformat(),
                    'service': 'bids'
                },
                'action_text': 'View Bid'
            }

            return self.send_notification(notification_data)

        except Exception as e:
            logger.error(f"Error creating bid viewed notification: {e}")
            return False

    def send_bid_withdrawn_notification(self, bid) -> bool:
        """Notify client when freelancer withdraws bid"""
        try:
            job_service = JobService()
            job_data = job_service.get_job_details(bid.job_id)

            notification_data = {
                'recipient_id': str(job_data.get('client_info', {}).get('id')),
                'notification_type': 'bid_withdrawn',
                'title': 'Bid Withdrawn',
                'message': f'A freelancer withdrew their bid on "{job_data.get("title", "")}"',
                'priority': 'low',
                'data': {
                    'bid_id': str(bid.id),
                    'job_id': bid.job_id,
                    'job_title': job_data.get('title', ''),
                    'service': 'bids'
                },
                'action_text': 'View Job'
            }

            return self.send_notification(notification_data)
        except Exception as e:
            logger.error(f"Error sending withdrawal notification: {e}")
            return False

    def send_bid_updated_notification(self, bid) -> bool:
        """Notify client when freelancer updates bid"""
        try:
            job_service = JobService()
            job_data = job_service.get_job_details(bid.job_id)

            notification_data = {
                'recipient_id': str(job_data.get('client_info', {}).get('id')),
                'notification_type': 'bid_updated',
                'title': 'Bid Updated',
                'message': f'A freelancer updated their bid on "{job_data.get("title", "")}"',
                'priority': 'low',
                'data': {
                    'bid_id': str(bid.id),
                    'job_id': bid.job_id,
                    'service': 'bids'
                },
                'action_text': 'Review Changes'
            }

            return self.send_notification(notification_data)
        except Exception as e:
            logger.error(f"Error sending update notification: {e}")
            return False

    def send_payment_success_notification(self, payment, bid):
        """Send payment success notification to freelancer"""
        try:
            # Notification to freelancer
            freelancer_notification = {
                'recipient_id': payment.freelancer_id,
                'notification_type': 'payment_received',
                'title': 'Payment Received!',
                'message': f'You have received a payment of {payment.amount} {payment.currency} for your bid.',
                'priority': 'high',
                'data': {
                    'payment_id': str(payment.id),
                    'bid_id': str(bid.id),
                    'amount': str(payment.amount),
                    'currency': payment.currency,
                    'receipt_number': payment.receipt_number
                },
                'action_url': f'/bids/{bid.id}',
                'action_text': 'View Details'
            }

            # Notification to client
            client_notification = {
                'recipient_id': payment.client_id,
                'notification_type': 'payment_completed',
                'title': 'Payment Successful',
                'message': f'Your payment of {payment.amount} {payment.currency} has been completed successfully.',
                'priority': 'normal',
                'data': {
                    'payment_id': str(payment.id),
                    'bid_id': str(bid.id),
                    'amount': str(payment.amount),
                    'currency': payment.currency,
                    'receipt_number': payment.receipt_number
                },
                'action_url': f'/bids/{bid.id}',
                'action_text': 'View Receipt'
            }

            self.send_notification(freelancer_notification)
            self.send_notification(client_notification)

            logger.info(f"Payment success notifications sent for payment {payment.id}")
            return True

        except Exception as e:
            logger.error(f"Failed to send payment success notification: {e}")
            return False


# Initialize a global notification client
notification_client = NotificationServiceClient()

# Use this as your main notification service
user_service= UserService()
job_service = JobService()
# Update your signals to use this client
# In your bids/signals.py, replace enhanced_notification_service with notification_client


import razorpay
import hmac
import hashlib
import logging
from django.conf import settings
from decimal import Decimal

logger = logging.getLogger(__name__)


class RazorpayPaymentService:
    """Service for handling Razorpay payments"""

    def __init__(self):
        self.client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )
        self.client.set_app_details({
            "title": "FreelanceHub",
            "version": "1.0.0"
        })

    def create_order(self, amount, currency='INR', receipt=None, notes=None):
        """
        Create a Razorpay order

        Args:
            amount: Amount in smallest currency unit (paise for INR)
            currency: Currency code (default: INR)
            receipt: Receipt number for reference
            notes: Additional notes (dict)

        Returns:
            dict: Razorpay order details
        """
        try:
            # Convert amount to paise (smallest unit)
            amount_paise = int(Decimal(str(amount)) * 100)

            order_data = {
                'amount': amount_paise,
                'currency': currency,
                'receipt': receipt or f'receipt_{timezone.now().timestamp()}',
                'notes': notes or {}
            }

            order = self.client.order.create(data=order_data)
            logger.info(f"Razorpay order created: {order['id']}")

            return {
                'success': True,
                'order_id': order['id'],
                'amount': order['amount'],
                'currency': order['currency'],
                'status': order['status'],
                'receipt': order.get('receipt'),
                'created_at': order.get('created_at')
            }

        except Exception as e:
            logger.error(f"Error creating Razorpay order: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def verify_payment_signature(self, razorpay_order_id, razorpay_payment_id, razorpay_signature):
        """
        Verify Razorpay payment signature

        Args:
            razorpay_order_id: Order ID from Razorpay
            razorpay_payment_id: Payment ID from Razorpay
            razorpay_signature: Signature from Razorpay

        Returns:
            bool: True if signature is valid
        """
        try:
            # Generate signature
            message = f"{razorpay_order_id}|{razorpay_payment_id}"
            generated_signature = hmac.new(
                settings.RAZORPAY_KEY_SECRET.encode(),
                message.encode(),
                hashlib.sha256
            ).hexdigest()

            is_valid = hmac.compare_digest(generated_signature, razorpay_signature)

            if is_valid:
                logger.info(f"Payment signature verified for payment: {razorpay_payment_id}")
            else:
                logger.warning(f"Invalid payment signature for payment: {razorpay_payment_id}")

            return is_valid

        except Exception as e:
            logger.error(f"Error verifying payment signature: {str(e)}")
            return False

    def get_payment_details(self, payment_id):
        """
        Get payment details from Razorpay

        Args:
            payment_id: Razorpay payment ID

        Returns:
            dict: Payment details
        """
        try:
            payment = self.client.payment.fetch(payment_id)
            return {
                'success': True,
                'payment': payment
            }
        except Exception as e:
            logger.error(f"Error fetching payment details: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def capture_payment(self, payment_id, amount):
        """
        Capture a payment

        Args:
            payment_id: Razorpay payment ID
            amount: Amount to capture in smallest currency unit

        Returns:
            dict: Capture result
        """
        try:
            amount_paise = int(Decimal(str(amount)) * 100)
            payment = self.client.payment.capture(payment_id, amount_paise)

            logger.info(f"Payment captured: {payment_id}")
            return {
                'success': True,
                'payment': payment
            }
        except Exception as e:
            logger.error(f"Error capturing payment: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def refund_payment(self, payment_id, amount=None):
        """
        Refund a payment

        Args:
            payment_id: Razorpay payment ID
            amount: Amount to refund (None for full refund)

        Returns:
            dict: Refund result
        """
        try:
            refund_data = {}
            if amount:
                refund_data['amount'] = int(Decimal(str(amount)) * 100)

            refund = self.client.payment.refund(payment_id, refund_data)

            logger.info(f"Payment refunded: {payment_id}")
            return {
                'success': True,
                'refund': refund
            }
        except Exception as e:
            logger.error(f"Error refunding payment: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }