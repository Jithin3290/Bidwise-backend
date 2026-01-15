"""
User profile management views
"""
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny

from ..models import User, UserPortfolio
from ..serializers import (
    UserProfileSerializer,
    UserUpdateSerializer,
    UserPortfolioSerializer,
)
from ..tasks import (
    update_profile_completion_task,
    sync_user_data_with_jobs_service,
)


class CurrentUserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get current user's complete profile"""
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data)


class UpdateUserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request):
        """Update current user's profile"""
        serializer = UserUpdateSerializer(
            request.user, data=request.data, partial=False
        )
        if serializer.is_valid():
            user = serializer.save()

            # Trigger async profile completion update
            update_profile_completion_task.delay(user.id)

            # Sync data with other services
            sync_user_data_with_jobs_service.delay(user.id)

            profile_serializer = UserProfileSerializer(user)
            return Response(profile_serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request):
        """Partially update current user's profile"""
        serializer = UserUpdateSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            user = serializer.save()

            # Trigger async tasks
            update_profile_completion_task.delay(user.id)
            sync_user_data_with_jobs_service.delay(user.id)

            profile_serializer = UserProfileSerializer(user)
            return Response(profile_serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserProfileView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, user_id):
        """Get public profile of any user"""
        try:
            user = User.objects.get(id=user_id, is_active=True)
            serializer = UserProfileSerializer(user)

            # Remove sensitive data for public view
            data = serializer.data
            sensitive_fields = [
                "email",
                "phone_number",
                "security_profile",
                "preferences",
            ]
            for field in sensitive_fields:
                data.pop(field, None)

            return Response(data)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)


class UpdateProfileCompletionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Manually trigger profile completion calculation"""
        user = request.user
        percentage = user.calculate_profile_completion()
        user.save()

        return Response(
            {
                "message": "Profile completion updated",
                "profile_completion_percentage": percentage,
            }
        )


class UserPublicPortfolioView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, user_id):
        """Get user's public portfolio items"""
        try:
            user = User.objects.get(id=user_id, is_active=True)
            if not user.is_freelancer:
                return Response({"error": "User is not a freelancer"}, status=400)

            freelancer_profile = getattr(user, "freelancer_profile", None)
            if not freelancer_profile:
                return Response({"error": "Freelancer profile not found"}, status=404)

            portfolio_items = UserPortfolio.objects.filter(
                freelancer_profile=freelancer_profile
            )
            serializer = UserPortfolioSerializer(portfolio_items, many=True)

            professional_profile = getattr(user, "professional_profile", None)

            return Response(
                {
                    "user": {
                        "id": user.id,
                        "username": user.username,
                        "full_name": user.full_name,
                        "title": (
                            professional_profile.title if professional_profile else ""
                        ),
                        "profile_picture": (
                            user.profile_picture.url if user.profile_picture else None
                        ),
                        "bio": user.bio,
                        "skills": freelancer_profile.skills,
                        "average_rating": freelancer_profile.average_rating,
                        "total_reviews": freelancer_profile.total_reviews,
                    },
                    "portfolio": serializer.data,
                }
            )
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)