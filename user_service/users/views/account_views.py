"""
Account type management views
"""
from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from ..models import UserAccountType, FreelancerProfile, ClientProfile, AdminProfile
from ..serializers import AccountTypeManagementSerializer
from .utils import assign_user_to_group


class ManageAccountTypeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Add or remove account types for user"""
        serializer = AccountTypeManagementSerializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid():
            user = request.user
            account_type = serializer.validated_data["account_type"]
            action = serializer.validated_data["action"]

            if action == "add":
                # Create account type
                UserAccountType.objects.create(
                    user=user,
                    account_type=account_type,
                    is_primary=len(user.account_types) == 0,
                )

                # Create corresponding profile
                if account_type == "freelancer":
                    FreelancerProfile.objects.get_or_create(user=user)
                elif account_type == "client":
                    ClientProfile.objects.get_or_create(user=user)
                elif account_type == "admin":
                    AdminProfile.objects.get_or_create(user=user)

                # Assign to group
                group_name = account_type.capitalize()
                assign_user_to_group(user, group_name)

                message = f"Added {account_type} account type"

            elif action == "remove":
                # Remove account type
                UserAccountType.objects.filter(
                    user=user, account_type=account_type
                ).delete()

                # Remove corresponding profile
                if account_type == "freelancer" and hasattr(user, "freelancer_profile"):
                    user.freelancer_profile.delete()
                elif account_type == "client" and hasattr(user, "client_profile"):
                    user.client_profile.delete()
                elif account_type == "admin" and hasattr(user, "admin_profile"):
                    user.admin_profile.delete()

                # Remove from group
                try:
                    group = Group.objects.get(name=account_type.capitalize())
                    user.groups.remove(group)
                except Group.DoesNotExist:
                    pass

                message = f"Removed {account_type} account type"

            user.calculate_profile_completion()
            user.save()

            return Response(
                {"message": message, "account_types": list(user.account_types)}
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)