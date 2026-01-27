"""
Freelancer-specific bid views
"""
import logging
import jwt
from django.conf import settings
from rest_framework import generics, status, filters
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from ..models import Bid
from ..serializers import (
    BidCreateSerializer,
    BidListSerializer,
    BidUpdateSerializer,
)
from ..authentication import JWTAuthentication
from ..services import notification_client, user_service
from ..filters import BidFilter
from ..permissions import IsFreelancer, IsBidOwner
from ..utils import check_bid_permission
from .utils import StandardResultsSetPagination

logger = logging.getLogger(__name__)


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

    def _ensure_freelancer_profile_exists(self, user_id):
        """Ensure freelancer profile exists in Users service"""
        try:
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