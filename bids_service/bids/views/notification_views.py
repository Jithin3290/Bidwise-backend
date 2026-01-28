"""
Notification testing and management views
"""
import logging
import requests
from datetime import timedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from ..models import Bid
from ..services import notification_client
from ..signals import send_bulk_bid_notifications

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def simple_notification_test(request):
    """Test notification system"""
    try:
        # Send test notification
        test_notification = {
            'recipient_id': str(request.user.user_id),
            'notification_type': 'test',
            'title': 'Test Notification from Bids Service',
            'message': 'This is a test notification to verify the connection',
            'priority': 'normal',
            'data': {
                'test': True,
                'service': 'bids',
                'timestamp': timezone.now().isoformat()
            },
            'action_url': '/dashboard',
            'action_text': 'Go to Dashboard'
        }

        notification_sent = notification_client.send_notification(test_notification)

        return Response({
            'notification_sent': notification_sent,
            'message': 'Test completed successfully' if notification_sent else 'Test failed',
            'notification_service_url': notification_client.base_url
        })

    except Exception as e:
        logger.error(f"Error in notification test: {e}")
        return Response({
            'error': f'Test failed: {str(e)}',
            'success': False
        }, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_bid_reminder_notifications(request):
    """Send reminder notifications for bids expiring soon"""
    try:
        # Get bids expiring in the next 24 hours
        tomorrow = timezone.now() + timedelta(hours=24)
        expiring_bids = Bid.objects.filter(
            status='pending',
            expires_at__lte=tomorrow,
            expires_at__gt=timezone.now()
        )

        results = send_bulk_bid_notifications(
            expiring_bids,
            'bid_deadline_reminder'
        )

        return Response({
            'message': 'Reminder notifications sent',
            'results': results,
            'bids_count': expiring_bids.count()
        })

    except Exception as e:
        logger.error(f"Error sending reminder notifications: {e}")
        return Response(
            {'error': 'Failed to send reminders'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def test_bid_notifications(request):
    """Test all bid notification types"""
    try:
        user_id = str(request.user.user_id)

        # Test different notification types
        notifications = [
            {
                'recipient_id': user_id,
                'notification_type': 'bid_created',
                'title': 'Test: New Bid Received',
                'message': 'This is a test notification for a new bid',
                'priority': 'normal',
                'data': {'test': True, 'type': 'bid_created'},
                'action_url': '/bids/test',
                'action_text': 'View Bid'
            },
            {
                'recipient_id': user_id,
                'notification_type': 'bid_accepted',
                'title': 'Test: Bid Accepted',
                'message': 'This is a test notification for an accepted bid',
                'priority': 'high',
                'data': {'test': True, 'type': 'bid_accepted'},
                'action_url': '/bids/test',
                'action_text': 'View Details'
            },
            {
                'recipient_id': user_id,
                'notification_type': 'bid_viewed',
                'title': 'Test: Bid Viewed',
                'message': 'This is a test notification for a viewed bid',
                'priority': 'low',
                'data': {'test': True, 'type': 'bid_viewed'},
                'action_url': '/bids/test',
                'action_text': 'View Bid'
            }
        ]

        results = {'success': 0, 'failed': 0}

        for notification in notifications:
            if notification_client.send_notification(notification):
                results['success'] += 1
            else:
                results['failed'] += 1

        return Response({
            'message': 'Test notifications sent',
            'results': results,
            'total_sent': len(notifications)
        })

    except Exception as e:
        logger.error(f"Error testing bid notifications: {e}")
        return Response({
            'error': f'Test failed: {str(e)}',
            'success': False
        }, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def debug_notification_detailed(request):
    """Detailed debug of notification service connection"""
    try:
        debug_info = {
            'notification_service_url': notification_client.base_url,
            'service_token_preview': notification_client.service_token[:10] + '...',
            'connection_tests': {}
        }

        # Test 1: Basic health check on notification service
        try:
            health_url = f"{notification_client.base_url}/api/health/"
            health_response = requests.get(health_url, timeout=5)
            debug_info['connection_tests']['health_check'] = {
                'url': health_url,
                'status_code': health_response.status_code,
                'response': health_response.text[:300],
                'success': health_response.status_code == 200
            }
        except Exception as e:
            debug_info['connection_tests']['health_check'] = {
                'url': f"{notification_client.base_url}/api/health/",
                'error': str(e),
                'success': False
            }

        # Test 2: Check if notification types exist
        try:
            types_url = f"{notification_client.base_url}/api/notifications/"
            types_response = requests.get(
                types_url,
                headers=notification_client._get_headers(),
                timeout=5
            )
            debug_info['connection_tests']['notification_types_check'] = {
                'url': types_url,
                'status_code': types_response.status_code,
                'response': types_response.text[:300],
                'success': types_response.status_code in [200, 405]  # 405 = Method not allowed is OK for GET
            }
        except Exception as e:
            debug_info['connection_tests']['notification_types_check'] = {
                'error': str(e),
                'success': False
            }

        # Test 3: Try sending a minimal notification
        try:
            minimal_notification = {
                'recipient_id': str(request.user.user_id),
                'notification_type': 'test',
                'title': 'Debug Test',
                'message': 'Debug test message'
            }

            notif_url = f"{notification_client.base_url}/api/notifications/"
            notif_response = requests.post(
                notif_url,
                json=minimal_notification,
                headers=notification_client._get_headers(),
                timeout=10
            )

            debug_info['connection_tests']['minimal_notification'] = {
                'url': notif_url,
                'payload': minimal_notification,
                'headers': notification_client._get_headers(),
                'status_code': notif_response.status_code,
                'response': notif_response.text[:500],
                'success': notif_response.status_code == 201
            }

        except Exception as e:
            debug_info['connection_tests']['minimal_notification'] = {
                'error': str(e),
                'success': False
            }

        # Test 4: Check if service token is working
        try:
            # Test with wrong token
            wrong_headers = {
                'Authorization': 'Bearer wrong-token',
                'Content-Type': 'application/json'
            }
            wrong_response = requests.post(
                f"{notification_client.base_url}/api/notifications/",
                json=minimal_notification,
                headers=wrong_headers,
                timeout=5
            )
            debug_info['connection_tests']['wrong_token_test'] = {
                'status_code': wrong_response.status_code,
                'response': wrong_response.text[:200],
                'expected': 'Should be 401/403 if token auth is working'
            }
        except Exception as e:
            debug_info['connection_tests']['wrong_token_test'] = {
                'error': str(e)
            }

        return Response(debug_info)

    except Exception as e:
        return Response({
            'error': f'Debug failed: {str(e)}',
            'success': False
        }, status=500)