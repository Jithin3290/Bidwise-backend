import logging
from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
import jwt
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status, filters
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend

from .signals import send_bulk_bid_notifications, handle_bid_viewed
from .utils  import check_bid_permission,track_bid_view,update_freelancer_profile_cache,get_client_ip
from .models import (
    Bid, BidMilestone, BidAttachment, BidMessage,
    FreelancerBidProfile, JobBidSummary, BidView
)
from .serializers import (
    BidCreateSerializer, BidDetailSerializer, BidListSerializer,
    BidUpdateSerializer, BidStatusUpdateSerializer, BidAttachmentSerializer,
    BidMessageSerializer, JobBidSummarySerializer, BidStatsSerializer,
    FreelancerDashboardSerializer, ClientBidManagementSerializer
)
from .authentication import JWTAuthentication
from .services import UserService, JobService,notification_client
from .filters import BidFilter
from .permissions import IsFreelancer, IsClient, IsBidOwner, IsJobOwner

logger = logging.getLogger(__name__)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


# ============= PUBLIC ENDPOINTS =============



class JobBidsListView(generics.ListAPIView):
    """List all bids for a specific job (public view for job owners)"""

    serializer_class = BidListSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = BidFilter
    ordering_fields = ['created_at', 'amount', 'estimated_delivery', 'views_count']
    ordering = ['-created_at']

    def get_queryset(self):
        job_id = self.kwargs['job_id']

        # Only show non-withdrawn bids
        queryset = Bid.objects.filter(
            job_id=job_id,
            status__in=['pending', 'accepted', 'rejected']
        ).select_related().prefetch_related('milestones', 'attachments')

        return queryset

    def list(self, request, *args, **kwargs):
        job_id = self.kwargs['job_id']

        # Verify job exists
        job_service = JobService()
        job_data = job_service.get_job_details(job_id)
        if not job_data:
            return Response(
                {"error": "Job not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get bids
        queryset = self.filter_queryset(self.get_queryset())

        # Update freelancer profiles for bids
        for bid in queryset:
            profile = FreelancerBidProfile.objects.filter(
                freelancer_id=bid.freelancer_id
            ).first()

            if not profile or not profile.is_cache_valid():
                profile = update_freelancer_profile_cache(bid.freelancer_id)

            bid.freelancer_profile = profile

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class BidDetailView(generics.RetrieveAPIView):
    """Get detailed bid information"""

    serializer_class = BidDetailSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_object(self):
        bid_id = self.kwargs['bid_id']
        bid = get_object_or_404(Bid, id=bid_id)

        # Check permissions
        user_id = self.request.user.user_id

        # Allow access if user is the bid owner or job owner
        job_service = JobService()
        job_data = job_service.get_job_details(bid.job_id)

        if user_id not in [bid.freelancer_id, job_data.get('client_id')]:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You don't have permission to view this bid")

        return bid

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        # Track view if it's the job owner viewing
        job_service = JobService()
        job_data = job_service.get_job_details(instance.job_id)

        if request.user.user_id == job_data.get('client_id'):
            track_bid_view(instance, request)

            # Mark as viewed by client
            if not instance.client_viewed_at:
                instance.client_viewed_at = timezone.now()
                instance.save(update_fields=['client_viewed_at'])

                # Send bid viewed notification
                handle_bid_viewed(instance, request.user.user_id)

        # Update freelancer profile
        profile = FreelancerBidProfile.objects.filter(
            freelancer_id=instance.freelancer_id
        ).first()

        if not profile or not profile.is_cache_valid():
            profile = update_freelancer_profile_cache(instance.freelancer_id)

        instance.freelancer_profile = profile

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

# ============= FREELANCER ENDPOINTS =============

class FreelancerBidsListView(generics.ListAPIView):
    """List freelancer's own bids"""

    serializer_class = BidListSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsFreelancer]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_class = BidFilter
    search_fields = ['proposal']
    ordering_fields = ['created_at', 'amount', 'status', 'estimated_delivery']
    ordering = ['-created_at']

    def get_queryset(self):
        return Bid.objects.filter(
            freelancer_id=self.request.user.user_id
        ).select_related().prefetch_related('milestones', 'attachments')



class CreateBidView(generics.CreateAPIView):
    serializer_class = BidCreateSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        # FIX: Use request.user.user_id instead of request.user.id
        user_id = str(self.request.user.user_id)  # Changed from self.request.user.id
        job_id = serializer.validated_data['job_id']

        logger.info(f"Creating bid for job {job_id} by user {user_id}")

        # Check if user has freelancer account type
        if 'freelancer' not in self.request.user.account_types:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only freelancers can create bids")

        # Check bid permission
        can_bid, error_message = check_bid_permission(self.request, job_id)
        if not can_bid:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(error_message)

        # Simple duplicate check
        existing_bid = Bid.objects.filter(
            job_id=job_id,
            freelancer_id=user_id
        ).first()

        if existing_bid:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("You have already submitted a bid for this job")

        # FIX: Ensure freelancer profile exists
        self._ensure_freelancer_profile_exists(user_id)

        # Save the bid
        bid = serializer.save(freelancer_id=user_id)
        logger.info(f"Bid created successfully: {bid.id}")

        # # Create notification
        # try:
        #     from .tasks import send_bid_notification_task
        #     send_bid_notification_task.delay(str(bid.id))
        # except Exception as e:
        #     logger.error(f"Failed to send bid notification: {e}")
        #
        # return bid

    def _ensure_freelancer_profile_exists(self, user_id):
        """Ensure freelancer profile exists in Users service"""
        try:
            from .services import user_service

            # Check if profile exists - account types already verified via JWT
            user_data = user_service.get_user_profile(user_id)
            if not user_data:
                logger.error(f"User {user_id} not found in Users service")
                from rest_framework.exceptions import ValidationError
                raise ValidationError("User profile not found")

            # Account type verification already done in check_bid_permission via JWT
            # No need to double-check here since JWT is the authoritative source

            logger.info(f"User profile verified for user {user_id}")

        except Exception as e:
            logger.error(f"Error verifying user profile for user {user_id}: {e}")
            raise
class UpdateBidView(generics.UpdateAPIView):
    """Update freelancer's own bid"""

    serializer_class = BidUpdateSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsFreelancer, IsBidOwner]

    def get_queryset(self):
        return Bid.objects.filter(
            freelancer_id=self.request.user.user_id,
            status='pending'
        )

    def perform_update(self, serializer):
        bid = serializer.save()

        try:
            notification_client.send_bid_updated_notification(bid)
        except Exception as e:
            logger.error(f"Failed to send bid update notification: {e}")

class WithdrawBidView(generics.UpdateAPIView):
    """Withdraw a bid"""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsFreelancer, IsBidOwner]

    def get_queryset(self):
        return Bid.objects.filter(
            freelancer_id=self.request.user.user_id,
            status='pending'
        )

    def patch(self, request, *args, **kwargs):
        bid = self.get_object()

        try:
            bid.withdraw()
            notification_client.send_bid_withdrawn_notification(bid)
            return Response(
                {"message": "Bid withdrawn successfully"},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )



class FreelancerDashboardView(APIView):
    """Get freelancer dashboard data"""
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # Get user ID from standard Django user
        freelancer_id = str(request.user.id)

        # Extract account types from JWT token
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        account_types = []

        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            try:
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
                account_types = payload.get('account_types', [])
            except jwt.InvalidTokenError:
                pass

        if 'freelancer' not in account_types:
            return Response(
                {"error": "Only freelancers can access this endpoint"},
                status=status.HTTP_403_FORBIDDEN
            )

        # Rest of your dashboard logic...
        return Response({
            'user_id': freelancer_id,
            'account_types': account_types,
            'message': 'Dashboard working!'
        })
class ClientBidManagementView(generics.ListAPIView):
    """Client bid management dashboard"""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsClient]

    def get(self, request, *args, **kwargs):
        client_id = request.user.user_id

        # Get client's jobs
        job_service = JobService()
        client_jobs = job_service.get_client_jobs(client_id)
        logger.info("ldskflsf",client_id)
        logger.info("ldskflsf",client_jobs)
        dashboard_data = []

        for job in client_jobs:
            job_id = job['id']

            # Get bid summary
            summary, created = JobBidSummary.objects.get_or_create(job_id=job_id)
            if created or not summary.last_updated or \
                    (timezone.now() - summary.last_updated).seconds > 3600:  # 1 hour
                summary.refresh_summary()

            # Get new bids (last 24 hours)
            yesterday = timezone.now() - timezone.timedelta(days=1)
            new_bids_count = Bid.objects.filter(
                job_id=job_id,
                created_at__gte=yesterday
            ).count()

            # Get top bids
            top_bids = Bid.objects.filter(
                job_id=job_id,
                status='pending'
            ).order_by('amount')[:5]

            # Update freelancer profiles for top bids
            for bid in top_bids:
                profile = FreelancerBidProfile.objects.filter(
                    freelancer_id=bid.freelancer_id
                ).first()
                if not profile or not profile.is_cache_valid():
                    profile = update_freelancer_profile_cache(bid.freelancer_id)
                bid.freelancer_profile = profile

            # Calculate quality score (simplified)
            quality_score = min(10.0, (summary.total_bids / 5) * 2)  # Basic scoring

            job_data = {
                'job_id': job_id,
                'job_title': job.get('title', ''),
                'total_bids': summary.total_bids,
                'new_bids': new_bids_count,
                'quality_score': quality_score,
                'average_bid': summary.average_bid or 0,
                'top_bids': top_bids
            }

            dashboard_data.append(job_data)

        serializer = ClientBidManagementSerializer(dashboard_data, many=True)
        return Response(serializer.data)


class UpdateBidStatusView(generics.UpdateAPIView):
    """Update bid status (accept/reject)"""

    serializer_class = BidStatusUpdateSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsClient]

    def get_object(self):
        bid_id = self.kwargs['bid_id']
        bid = get_object_or_404(Bid, id=bid_id, status='pending')

        # Verify user owns the job
        job_service = JobService()
        job_data = job_service.get_job_details(bid.job_id)
        # logger.info(job_data)
        if not job_data or job_data.get('client_info', {}).get('id') != self.request.user.user_id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You don't have permission to manage this bid")

        return bid

    def perform_update(self, serializer):
        bid = serializer.save()

        # If bid is accepted, reject all other pending bids for the same job
        if bid.status == 'accepted':
            Bid.objects.filter(
                job_id=bid.job_id,
                status='pending'
            ).exclude(id=bid.id).update(
                status='rejected',
                rejected_at=timezone.now(),
                client_feedback='Another bid was selected for this project'
            )

        # Update job bid summary
        summary, created = JobBidSummary.objects.get_or_create(job_id=bid.job_id)
        summary.refresh_summary()

        # Send notifications
        try:
            notification_service = notification_client()
            notification_service.send_bid_status_notification(bid)
        except Exception as e:
            logger.error(f"Error sending bid status notification: {e}")


# ============= BID ATTACHMENTS =============

class BidAttachmentView(APIView):
    """Upload and delete bid attachments"""
    permission_classes = [IsAuthenticated]

    def post(self, request, bid_id, *args, **kwargs):
        """Upload attachment to a bid"""
        # Validate Bid ownership
        bid = get_object_or_404(Bid, id=bid_id, freelancer_id=request.user.user_id)

        if bid.status != 'pending':
            return Response(
                {"error": "Can only add attachments to pending bids"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if 'file' not in request.FILES:
            return Response(
                {"error": "No file provided"},
                status=status.HTTP_400_BAD_REQUEST
            )

        file = request.FILES['file']
        description = request.data.get('description', '')
        file_type = request.data.get('file_type', 'document')

        # File size validation (10MB limit)
        if file.size > 10 * 1024 * 1024:
            return Response(
                {"error": "File size exceeds 10MB limit"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            attachment = BidAttachment.objects.create(
                bid=bid,
                file=file,
                filename=file.name,
                file_type=file_type,
                file_size=file.size,
                description=description
            )
            serializer = BidAttachmentSerializer(attachment, context={'request': request})
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error creating bid attachment: {e}")
            return Response(
                {"error": "Failed to upload attachment"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def delete(self, request, bid_id, attachment_id=None, *args, **kwargs):
        """Delete a bid attachment"""
        # Validate Bid and Attachment
        bid = get_object_or_404(Bid, id=bid_id, freelancer_id=request.user.user_id)
        attachment = get_object_or_404(BidAttachment, id=attachment_id, bid=bid)

        if bid.status != 'pending':
            return Response(
                {"error": "Can only delete attachments from pending bids"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Delete file from storage then DB
        if attachment.file:
            attachment.file.delete()
        attachment.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)
# ============= STATISTICS AND ANALYTICS =============


class JobBidSummaryView(APIView):
    """Get bid summary for a job"""
    permission_classes = [AllowAny]

    def get(self, request, job_id):
        job_service = JobService()
        job_data = job_service.get_job_details(job_id)
        if not job_data:
            return Response(
                {"error": "Job not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        summary, created = JobBidSummary.objects.get_or_create(job_id=job_id)
        if created or (timezone.now() - summary.last_updated).seconds > 3600:
            summary.refresh_summary()

        serializer = JobBidSummarySerializer(summary)
        return Response(serializer.data)

from django.db.models import Avg, Sum

class BidStatisticsView(APIView):
    """Get bid statistics for authenticated user"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_id = request.user.user_id
        user_type = getattr(request.user, 'user_type', None)

        if user_type == 'freelancer' or 'freelancer' in getattr(request.user, 'account_types', []):
            # Freelancer statistics
            bids = Bid.objects.filter(freelancer_id=user_id)

            total_bids = bids.count()
            pending_bids = bids.filter(status='pending').count()
            accepted_bids = bids.filter(status='accepted').count()
            rejected_bids = bids.filter(status='rejected').count()
            withdrawn_bids = bids.filter(status='withdrawn').count()

            acceptance_rate = (accepted_bids / total_bids * 100) if total_bids > 0 else 0
            average_bid_amount = bids.aggregate(avg=Avg('amount'))['avg'] or 0
            total_potential_earnings = bids.filter(
                status__in=['pending', 'accepted']
            ).aggregate(total=Sum('amount'))['total'] or 0

            # Recent activity
            recent_bids = bids.order_by('-created_at')[:5]
            recent_activity = [
                {
                    'bid_id': str(bid.id),
                    'job_id': bid.job_id,
                    'amount': bid.amount,
                    'status': bid.status,
                    'created_at': bid.created_at,
                }
                for bid in recent_bids
            ]

            stats = {
                'total_bids': total_bids,
                'pending_bids': pending_bids,
                'accepted_bids': accepted_bids,
                'rejected_bids': rejected_bids,
                'withdrawn_bids': withdrawn_bids,
                'acceptance_rate': round(acceptance_rate, 2),
                'average_bid_amount': average_bid_amount,
                'total_potential_earnings': total_potential_earnings,
                'recent_activity': recent_activity,
            }

        else:
            # Client statistics
            job_service = JobService()
            client_jobs = job_service.get_client_jobs(user_id)
            job_ids = [job['id'] for job in client_jobs]

            bids = Bid.objects.filter(job_id__in=job_ids)

            total_bids = bids.count()
            pending_bids = bids.filter(status='pending').count()
            accepted_bids = bids.filter(status='accepted').count()
            rejected_bids = bids.filter(status='rejected').count()

            stats = {
                'total_bids_received': total_bids,
                'pending_bids': pending_bids,
                'accepted_bids': accepted_bids,
                'rejected_bids': rejected_bids,
                'average_bids_per_job': total_bids / len(job_ids) if job_ids else 0,
                'recent_activity': [],
            }

        serializer = BidStatsSerializer(stats)
        return Response(serializer.data)

class HealthCheckView(APIView):
    """Health check endpoint"""
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            'status': 'healthy',
            'service': 'bids-service',
            'timestamp': timezone.now(),
            'version': '1.0.0',
        })


from .services import notification_client


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
        from datetime import timedelta

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
        import requests
        from .services import notification_client

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