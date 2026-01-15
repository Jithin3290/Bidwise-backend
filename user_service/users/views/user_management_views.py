"""
User listing, search, and profile detail management views
"""
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics, viewsets, serializers
from rest_framework.permissions import IsAuthenticated

from ..models import (
    User,
    UserEducation,
    UserExperience,
    UserCertification,
    UserPortfolio,
    UserSocialLink,
    FreelancerProfile,
)
from ..serializers import (
    UserListSerializer,
    UserEducationSerializer,
    UserExperienceSerializer,
    UserCertificationSerializer,
    UserPortfolioSerializer,
    UserSocialLinkSerializer,
)
from .utils import StandardResultsSetPagination


class UserListView(generics.ListAPIView):
    """List and search users with filtering"""

    serializer_class = UserListSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    search_fields = ["first_name", "last_name", "professional_profile__title", "bio"]
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = (
            User.objects.filter(is_active=True)
            .select_related("professional_profile", "freelancer_profile")
            .prefetch_related("user_account_types")
        )

        # Filter by account type
        account_type = self.request.query_params.get("account_type")
        if account_type:
            queryset = queryset.filter(user_account_types__account_type=account_type)

        # Filter by country
        country = self.request.query_params.get("country")
        if country:
            queryset = queryset.filter(country=country)

        # Filter by freelancer-specific fields
        if account_type == "freelancer":
            # Filter by skills
            skills = self.request.query_params.get("skills")
            if skills:
                skill_list = [skill.strip() for skill in skills.split(",")]
                queryset = queryset.filter(
                    freelancer_profile__skills__overlap=skill_list
                )

            # Filter by hourly rate range
            min_rate = self.request.query_params.get("min_rate")
            max_rate = self.request.query_params.get("max_rate")
            if min_rate:
                queryset = queryset.filter(
                    freelancer_profile__hourly_rate__gte=min_rate
                )
            if max_rate:
                queryset = queryset.filter(
                    freelancer_profile__hourly_rate__lte=max_rate
                )

            # Filter by minimum rating
            min_rating = self.request.query_params.get("min_rating")
            if min_rating:
                queryset = queryset.filter(
                    freelancer_profile__average_rating__gte=min_rating
                )

            # Filter by availability status
            availability_status = self.request.query_params.get("availability_status")
            if availability_status:
                queryset = queryset.filter(
                    freelancer_profile__availability_status=availability_status
                )

            # Filter by experience level
            experience_level = self.request.query_params.get("experience_level")
            if experience_level:
                queryset = queryset.filter(
                    freelancer_profile__experience_level=experience_level
                )

        return queryset.distinct()


class UserEducationViewSet(viewsets.ModelViewSet):
    serializer_class = UserEducationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if not self.request.user.is_freelancer:
            return UserEducation.objects.none()

        freelancer_profile = getattr(self.request.user, "freelancer_profile", None)
        if not freelancer_profile:
            return UserEducation.objects.none()

        return UserEducation.objects.filter(freelancer_profile=freelancer_profile)

    def perform_create(self, serializer):
        if not self.request.user.is_freelancer:
            raise serializers.ValidationError("Only freelancers can add education")

        freelancer_profile = getattr(self.request.user, "freelancer_profile", None)
        if not freelancer_profile:
            FreelancerProfile.objects.create(user=self.request.user)
            freelancer_profile = self.request.user.freelancer_profile

        serializer.save(freelancer_profile=freelancer_profile)


class UserExperienceViewSet(viewsets.ModelViewSet):
    serializer_class = UserExperienceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if not self.request.user.is_freelancer:
            return UserExperience.objects.none()

        freelancer_profile = getattr(self.request.user, "freelancer_profile", None)
        if not freelancer_profile:
            return UserExperience.objects.none()

        return UserExperience.objects.filter(freelancer_profile=freelancer_profile)

    def perform_create(self, serializer):
        if not self.request.user.is_freelancer:
            raise serializers.ValidationError("Only freelancers can add experience")

        freelancer_profile = getattr(self.request.user, "freelancer_profile", None)
        if not freelancer_profile:
            FreelancerProfile.objects.create(user=self.request.user)
            freelancer_profile = self.request.user.freelancer_profile

        # If this is marked as current, unmark other current jobs
        if serializer.validated_data.get("is_current"):
            UserExperience.objects.filter(
                freelancer_profile=freelancer_profile, is_current=True
            ).update(is_current=False)
        serializer.save(freelancer_profile=freelancer_profile)

    def perform_update(self, serializer):
        freelancer_profile = getattr(self.request.user, "freelancer_profile", None)
        # If this is marked as current, unmark other current jobs
        if serializer.validated_data.get("is_current"):
            UserExperience.objects.filter(
                freelancer_profile=freelancer_profile, is_current=True
            ).exclude(id=self.get_object().id).update(is_current=False)
        serializer.save()


class UserCertificationViewSet(viewsets.ModelViewSet):
    serializer_class = UserCertificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if not self.request.user.is_freelancer:
            return UserCertification.objects.none()

        freelancer_profile = getattr(self.request.user, "freelancer_profile", None)
        if not freelancer_profile:
            return UserCertification.objects.none()

        return UserCertification.objects.filter(freelancer_profile=freelancer_profile)

    def perform_create(self, serializer):
        if not self.request.user.is_freelancer:
            raise serializers.ValidationError("Only freelancers can add certifications")

        freelancer_profile = getattr(self.request.user, "freelancer_profile", None)
        if not freelancer_profile:
            FreelancerProfile.objects.create(user=self.request.user)
            freelancer_profile = self.request.user.freelancer_profile

        serializer.save(freelancer_profile=freelancer_profile)


class UserPortfolioViewSet(viewsets.ModelViewSet):
    serializer_class = UserPortfolioSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if not self.request.user.is_freelancer:
            return UserPortfolio.objects.none()

        freelancer_profile = getattr(self.request.user, "freelancer_profile", None)
        if not freelancer_profile:
            return UserPortfolio.objects.none()

        return UserPortfolio.objects.filter(freelancer_profile=freelancer_profile)

    def perform_create(self, serializer):
        if not self.request.user.is_freelancer:
            raise serializers.ValidationError(
                "Only freelancers can add portfolio items"
            )

        freelancer_profile = getattr(self.request.user, "freelancer_profile", None)
        if not freelancer_profile:
            FreelancerProfile.objects.create(user=self.request.user)
            freelancer_profile = self.request.user.freelancer_profile

        serializer.save(freelancer_profile=freelancer_profile)


class UserSocialLinkViewSet(viewsets.ModelViewSet):
    serializer_class = UserSocialLinkSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserSocialLink.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)