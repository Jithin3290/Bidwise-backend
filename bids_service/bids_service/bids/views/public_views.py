"""
Public bid views - accessible without authentication or with basic permissions
"""
import logging
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status, filters
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from ..models import Bid, FreelancerBidProfile, JobBidSummary
from ..serializers import (
    BidDetailSerializer,
    BidListSerializer,
    JobBidSummarySerializer,
)
from ..authentication import JWTAuthentication
from ..services import JobService
from ..filters import BidFilter
from ..utils import track_bid_view, update_freelancer_profile_cache
from ..signals import handle_bid_viewed
from .utils import StandardResultsSetPagination

logger = logging.getLogger(__name__)


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