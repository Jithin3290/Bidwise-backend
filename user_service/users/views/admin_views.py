"""
Admin-only views for user management and statistics
"""
from django.contrib.auth.models import Group
from django.db.models import Count, Q
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from ..models import User
from ..utils.permissions import IsAdminUser
from .utils import StandardResultsSetPagination


class AdminUsersView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        """Admin only - Get all users with pagination and filtering"""
        # Apply filtering
        queryset = User.objects.all().prefetch_related("user_account_types")
        account_type = request.GET.get("account_type")
        if account_type:
            queryset = queryset.filter(user_account_types__account_type=account_type)

        # Apply search
        search = request.GET.get("search")
        if search:
            queryset = queryset.filter(
                Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(username__icontains=search)
            )

        # Pagination
        paginator = StandardResultsSetPagination()
        result_page = paginator.paginate_queryset(queryset, request)

        users_data = []
        for user in result_page:
            users_data.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "full_name": user.full_name,
                    "account_types": list(user.account_types),
                    "groups": list(user.groups.values_list("name", flat=True)),
                    "is_active": user.is_active,
                    "is_verified": user.is_verified,
                    "profile_completion_percentage": user.profile_completion_percentage,
                    "created_at": user.created_at,
                    "last_activity": user.last_activity,
                }
            )

        return paginator.get_paginated_response(users_data)


class AssignUserGroupView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        """Admin can assign users to groups"""
        user_id = request.data.get("user_id")
        group_name = request.data.get("group_name")

        if not user_id or not group_name:
            return Response(
                {"error": "user_id and group_name are required"}, status=400
            )

        try:
            user = User.objects.get(id=user_id)
            group = Group.objects.get(name=group_name)

            # Optionally remove from all groups first
            clear_groups = request.data.get("clear_groups", False)
            if clear_groups:
                user.groups.clear()

            user.groups.add(group)

            return Response(
                {
                    "message": f"User {user.username} assigned to {group_name} group",
                    "user_groups": list(user.groups.values_list("name", flat=True)),
                }
            )
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=400)
        except Group.DoesNotExist:
            return Response({"error": "Group not found"}, status=400)


class ToggleUserStatusView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, user_id):
        """Admin can activate/deactivate users"""
        try:
            user = User.objects.get(id=user_id)
            user.is_active = not user.is_active
            user.save()

            return Response(
                {
                    "message": f"User {user.username} {'activated' if user.is_active else 'deactivated'}",
                    "is_active": user.is_active,
                }
            )
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=400)


class UserStatsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        """Get platform statistics (Admin only)"""
        total_users = User.objects.count()
        total_freelancers = (
            User.objects.filter(user_account_types__account_type="freelancer")
            .distinct()
            .count()
        )
        total_clients = (
            User.objects.filter(user_account_types__account_type="client")
            .distinct()
            .count()
        )
        total_admins = (
            User.objects.filter(user_account_types__account_type="admin")
            .distinct()
            .count()
        )
        verified_users = User.objects.filter(is_verified=True).count()
        premium_users = User.objects.filter(is_premium=True).count()

        # Get users by country (top 10)
        users_by_country = (
            User.objects.values("country")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        )

        return Response(
            {
                "total_users": total_users,
                "total_freelancers": total_freelancers,
                "total_clients": total_clients,
                "total_admins": total_admins,
                "verified_users": verified_users,
                "premium_users": premium_users,
                "verification_rate": (
                    (verified_users / total_users * 100) if total_users > 0 else 0
                ),
                "users_by_country": users_by_country,
            }
        )