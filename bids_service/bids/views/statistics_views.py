"""
Bid statistics and analytics views
"""
from django.db.models import Avg, Sum
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from ..models import Bid
from ..serializers import BidStatsSerializer
from ..services import JobService


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