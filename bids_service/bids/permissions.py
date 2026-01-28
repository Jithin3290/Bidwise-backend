# bids/permissions.py
from rest_framework.permissions import BasePermission
from .services import JobService


class IsFreelancer(BasePermission):
    """Permission to check if user is a freelancer"""

    message = "Only freelancers can perform this action."

    def has_permission(self, request, view):
        if not request.user or not hasattr(request.user, 'account_types'):
            return False

        return 'freelancer' in request.user.account_types


class IsClient(BasePermission):
    """Permission to check if user is a client"""

    message = "Only clients can perform this action."

    def has_permission(self, request, view):
        if not request.user or not hasattr(request.user, 'account_types'):
            return False

        return 'client' in request.user.account_types


class IsBidOwner(BasePermission):
    """Permission to check if user owns the bid"""

    message = "You can only modify your own bids."

    def has_object_permission(self, request, view, obj):
        if not request.user:
            return False

        return obj.freelancer_id == request.user.user_id


class IsJobOwner(BasePermission):
    """Permission to check if user owns the job"""

    message = "You can only manage bids for your own jobs."

    def has_object_permission(self, request, view, obj):
        if not request.user:
            return False

        # Get job details to verify ownership
        job_service = JobService()
        job_data = job_service.get_job_details(obj.job_id)

        if not job_data:
            return False

        return job_data.get('client_id') == request.user.user_id


class CanViewBid(BasePermission):
    """Permission to check if user can view the bid"""

    message = "You don't have permission to view this bid."

    def has_object_permission(self, request, view, obj):
        if not request.user:
            return False

        # Bid owner can always view
        if obj.freelancer_id == request.user.user_id:
            return True

        # Job owner can view bids for their jobs
        job_service = JobService()
        job_data = job_service.get_job_details(obj.job_id)

        if job_data and job_data.get('client_id') == request.user.user_id:
            return True

        return False


class CanManageBidStatus(BasePermission):
    """Permission to check if user can manage bid status (accept/reject)"""

    message = "Only job owners can manage bid status."

    def has_object_permission(self, request, view, obj):
        if not request.user:
            return False

        # Only job owner can manage bid status
        job_service = JobService()
        job_data = job_service.get_job_details(obj.job_id)

        if not job_data:
            return False

        return job_data.get('client_id') == request.user.user_id