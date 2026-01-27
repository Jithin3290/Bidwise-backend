"""
Client-specific bid management views
"""
import logging
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from ..models import Bid, FreelancerBidProfile, JobBidSummary
from ..serializers import (
    BidStatusUpdateSerializer,
    ClientBidManagementSerializer,
)
from ..authentication import JWTAuthentication
from ..services import JobService, notification_client
from ..permissions import IsClient
from ..utils import update_freelancer_profile_cache

logger = logging.getLogger(__name__)


class ClientBidManagementView(generics.ListAPIView):
    """Client bid management dashboard"""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsClient]

    def get(self, request, *args, **kwargs):
        client_id = request.user.user_id

        # Get client's jobs
        job_service = JobService()
        client_jobs = job_service.get_client_jobs(client_id)
        logger.info("Client ID: %s", client_id)
        logger.info("Client Jobs: %s", client_jobs)

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