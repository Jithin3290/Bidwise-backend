# users/serializers.py
from django.contrib.auth import authenticate
from rest_framework import serializers

from .models import (AdminProfile, ClientProfile, FreelancerProfile, User,
                     UserAccountType, UserCertification, UserEducation,
                     UserExperience, UserPortfolio, UserPreferences,
                     UserProfessionalProfile, UserSecurity, UserSocialLink)


class UserProfessionalProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfessionalProfile
        fields = [
            "title",
            "company_name",
            "website",
            "linkedin_url",
            "github_url",
            "portfolio_url",
            "languages_spoken",
        ]


class UserSecuritySerializer(serializers.ModelSerializer):
    last_login_ip = serializers.CharField(max_length=45, required=False, allow_blank=True, allow_null=True)
    class Meta:
        model = UserSecurity
        fields = ["mfa_enabled", "last_login_ip"]
        read_only_fields = ["last_login_ip"]


class UserPreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreferences
        fields = ["notification_preferences", "privacy_settings"]


class UserAccountTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAccountType
        fields = ["account_type", "is_primary", "is_active"]
        read_only_fields = ["created_at"]


class FreelancerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = FreelancerProfile
        fields = [
            "skills",
            "experience_level",
            "years_of_experience",
            "hourly_rate",
            "currency",
            "availability_status",
            "availability_hours_per_week",
            "average_rating",
            "total_reviews",
            "total_projects_completed",
        ]
        read_only_fields = [
            "average_rating",
            "total_reviews",
            "total_projects_completed",
        ]


class ClientProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientProfile
        fields = ["company_size", "industry", "total_projects_posted", "total_spent"]
        read_only_fields = ["total_projects_posted", "total_spent"]


class AdminProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminProfile
        fields = ["permissions", "department", "admin_level"]


class UserEducationSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserEducation
        fields = "__all__"
        read_only_fields = ["freelancer_profile", "created_at"]


class UserExperienceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserExperience
        fields = "__all__"
        read_only_fields = ["freelancer_profile", "created_at"]


class UserCertificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserCertification
        fields = "__all__"
        read_only_fields = ["freelancer_profile", "created_at"]


class UserPortfolioSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPortfolio
        fields = "__all__"
        read_only_fields = ["freelancer_profile", "created_at"]


class UserSocialLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSocialLink
        fields = "__all__"
        read_only_fields = ["user", "created_at"]


class UserProfileSerializer(serializers.ModelSerializer):
    """Comprehensive user profile serializer"""

    profile_picture = serializers.ImageField(use_url=True)
    full_name = serializers.ReadOnlyField()

    # Related profiles
    professional_profile = UserProfessionalProfileSerializer(read_only=True)
    security_profile = UserSecuritySerializer(read_only=True)
    preferences = UserPreferencesSerializer(read_only=True)
    user_account_types = UserAccountTypeSerializer(many=True, read_only=True)
    freelancer_profile = FreelancerProfileSerializer(read_only=True)
    client_profile = ClientProfileSerializer(read_only=True)
    admin_profile = AdminProfileSerializer(read_only=True)

    # Related data for freelancers
    education = serializers.SerializerMethodField()
    experience = serializers.SerializerMethodField()
    certifications = serializers.SerializerMethodField()
    portfolio = serializers.SerializerMethodField()
    social_links = UserSocialLinkSerializer(many=True, read_only=True)

    # Computed fields
    account_types = serializers.ReadOnlyField()
    is_freelancer = serializers.ReadOnlyField()
    is_client = serializers.ReadOnlyField()
    is_admin = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone_number",
            "profile_picture",
            "bio",
            "country",
            "city",
            "timezone",
            "is_verified",
            "phone_verified",
            "identity_verified",
            "profile_completion_percentage",
            "last_activity",
            "is_featured",
            "is_premium",
            "premium_expires",
            "created_at",
            "updated_at",
            "professional_profile",
            "security_profile",
            "preferences",
            "user_account_types",
            "freelancer_profile",
            "client_profile",
            "admin_profile",
            "education",
            "experience",
            "certifications",
            "portfolio",
            "social_links",
            "account_types",
            "is_freelancer",
            "is_client",
            "is_admin",
        ]
        read_only_fields = [
            "id",
            "profile_completion_percentage",
            "last_activity",
            "created_at",
            "updated_at",
            "account_types",
            "is_freelancer",
            "is_client",
            "is_admin",
        ]

    def get_education(self, obj):
        if hasattr(obj, "freelancer_profile") and obj.freelancer_profile:
            return UserEducationSerializer(
                obj.freelancer_profile.education.all(), many=True
            ).data
        return []

    def get_experience(self, obj):
        if hasattr(obj, "freelancer_profile") and obj.freelancer_profile:
            return UserExperienceSerializer(
                obj.freelancer_profile.experience.all(), many=True
            ).data
        return []

    def get_certifications(self, obj):
        if hasattr(obj, "freelancer_profile") and obj.freelancer_profile:
            return UserCertificationSerializer(
                obj.freelancer_profile.certifications.all(), many=True
            ).data
        return []

    def get_portfolio(self, obj):
        if hasattr(obj, "freelancer_profile") and obj.freelancer_profile:
            return UserPortfolioSerializer(
                obj.freelancer_profile.portfolio.all(), many=True
            ).data
        return []

    def validate_phone_number(self, value):
        if (
            value
            and not value.replace("+", "").replace("-", "").replace(" ", "").isdigit()
        ):
            raise serializers.ValidationError("Invalid phone number format")
        return value

    def update(self, instance, validated_data):
        # Update the instance
        instance = super().update(instance, validated_data)
        # Recalculate profile completion
        instance.calculate_profile_completion()
        instance.save()
        return instance


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    account_types = serializers.ListField(
        child=serializers.ChoiceField(choices=["client", "freelancer"]),
        write_only=True,
        required=True,
    )

    class Meta:
        model = User
        fields = ["email", "password", "account_types"]

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("User with this email already exists")
        return value

    def validate_account_types(self, value):
        if not value:
            raise serializers.ValidationError("At least one account type is required")
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Duplicate account types are not allowed")
        return value

    def create(self, validated_data):
        account_types = validated_data.pop("account_types")
        password = validated_data.pop("password")

        # Create user with only email + password
        user = User.objects.create_user(
            email=validated_data["email"],
            username=validated_data["email"].split("@")[0],  # optional: auto-username from email
            password=password,
        )

        # Assign account types
        for i, account_type in enumerate(account_types):
            UserAccountType.objects.create(
                user=user, account_type=account_type, is_primary=(i == 0)
            )

            if account_type == "freelancer":
                FreelancerProfile.objects.create(user=user)
            elif account_type == "client":
                ClientProfile.objects.create(user=user)

        # Create related profiles
        UserProfessionalProfile.objects.create(user=user)
        UserSecurity.objects.create(user=user)
        UserPreferences.objects.create(user=user)

        return user


class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get("email")
        password = data.get("password")

        if email and password:
            try:
                user = User.objects.get(email=email)

                # Check if account is locked
                if not user.can_login():
                    if user.is_account_locked:
                        raise serializers.ValidationError(
                            "Account is temporarily locked due to too many failed login attempts"
                        )
                    elif not user.is_active:
                        raise serializers.ValidationError("Account is disabled")

                # Authenticate user
                user = authenticate(
                    request=self.context.get("request"),
                    username=email,
                    password=password,
                )

                if user:
                    # Reset failed login attempts on successful login
                    user.reset_login_attempts()
                    data["user"] = user
                else:
                    # Increment failed login attempts
                    user_obj = User.objects.get(email=email)
                    user_obj.increment_login_attempts()
                    raise serializers.ValidationError("Invalid credentials")

            except User.DoesNotExist:
                raise serializers.ValidationError("Invalid credentials")
        else:
            raise serializers.ValidationError("Email and password are required")

        return data


class UserUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user profile and related profiles"""

    professional_profile = UserProfessionalProfileSerializer(required=False)
    preferences = UserPreferencesSerializer(required=False)
    freelancer_profile = FreelancerProfileSerializer(required=False)
    client_profile = ClientProfileSerializer(required=False)

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "phone_number",
            "profile_picture",
            "bio",
            "country",
            "city",
            "timezone",
            "professional_profile",
            "preferences",
            "freelancer_profile",
            "client_profile",
        ]
        extra_kwargs = {
            "profile_picture": {"required": False, "allow_null": True},
        }

    def validate_freelancer_profile(self, value):
        # Only allow if user has freelancer account type
        if value and not self.instance.is_freelancer:
            raise serializers.ValidationError("User is not a freelancer")
        return value

    def validate_client_profile(self, value):
        # Only allow if user has client account type
        if value and not self.instance.is_client:
            raise serializers.ValidationError("User is not a client")
        return value

    def update(self, instance, validated_data):
        # Extract nested data
        professional_data = validated_data.pop("professional_profile", None)
        preferences_data = validated_data.pop("preferences", None)
        freelancer_data = validated_data.pop("freelancer_profile", None)
        client_data = validated_data.pop("client_profile", None)

        # Update main user instance
        instance = super().update(instance, validated_data)

        # Update or create related profiles
        if professional_data:
            professional_profile, created = (
                UserProfessionalProfile.objects.get_or_create(user=instance)
            )
            for key, value in professional_data.items():
                setattr(professional_profile, key, value)
            professional_profile.save()

        if preferences_data:
            preferences, created = UserPreferences.objects.get_or_create(user=instance)
            for key, value in preferences_data.items():
                setattr(preferences, key, value)
            preferences.save()

        if freelancer_data and instance.is_freelancer:
            freelancer_profile, created = FreelancerProfile.objects.get_or_create(
                user=instance
            )
            for key, value in freelancer_data.items():
                setattr(freelancer_profile, key, value)
            freelancer_profile.save()

        if client_data and instance.is_client:
            client_profile, created = ClientProfile.objects.get_or_create(user=instance)
            for key, value in client_data.items():
                setattr(client_profile, key, value)
            client_profile.save()

        # Recalculate profile completion
        instance.calculate_profile_completion()
        instance.save()
        return instance


class UserListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for user lists"""

    full_name = serializers.ReadOnlyField()
    account_types = serializers.ReadOnlyField()
    professional_profile = UserProfessionalProfileSerializer(read_only=True)
    freelancer_profile = FreelancerProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "full_name",
            "account_types",
            "profile_picture",
            "country",
            "city",
            "is_verified",
            "last_activity",
            "professional_profile",
            "freelancer_profile",
        ]


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for changing password"""

    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=8)
    confirm_password = serializers.CharField(required=True)

    def validate(self, data):
        if data["new_password"] != data["confirm_password"]:
            raise serializers.ValidationError("New passwords don't match")
        return data

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect")
        return value


class AccountTypeManagementSerializer(serializers.Serializer):
    """Serializer for adding/removing account types"""

    account_type = serializers.ChoiceField(choices=["client", "freelancer", "admin"])
    action = serializers.ChoiceField(choices=["add", "remove"])

    def validate(self, data):
        user = self.context["request"].user
        account_type = data["account_type"]
        action = data["action"]

        if action == "add":
            if account_type in user.account_types:
                raise serializers.ValidationError(
                    f"User already has {account_type} account type"
                )
        elif action == "remove":
            if account_type not in user.account_types:
                raise serializers.ValidationError(
                    f"User doesn't have {account_type} account type"
                )
            if len(user.account_types) == 1:
                raise serializers.ValidationError("Cannot remove the last account type")

        return data
