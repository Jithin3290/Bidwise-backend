"""
Authentication views: Login, Register, Google OAuth
"""
from django.contrib.auth import authenticate, get_user_model
from django.conf import settings
from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated

from ..models import User, UserAccountType, UserSecurity
from ..serializers import (
    UserLoginSerializer,
    UserProfileSerializer,
    UserRegistrationSerializer,
    ChangePasswordSerializer,
)
from ..tasks import (
    send_welcome_email_task,
    process_profile_picture_task,
    update_profile_completion_task,
    sync_user_data_with_jobs_service,
)
from .utils import (
    CustomRefreshToken,
    generate_random_password,
    assign_user_to_group,
    create_user_profiles,
)

User = get_user_model()


@method_decorator(csrf_exempt, name="dispatch")
class GoogleLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        token = request.data.get("credential")
        requested_account_types = request.data.get("account_types")

        if not token:
            return Response({"error": "credential missing"}, status=400)

        try:
            # Get the client ID from settings
            client_id = settings.GOOGLE_OAUTH_CLIENT_ID
            print("GOOGLE CLIENT ID USED:", client_id)


            # CRITICAL: Actually verify the token and get user info
            idinfo = id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                client_id
            )

        except Exception as e:
            return Response({"error": f"Invalid token: {e}"}, status=400)

        # Extract user information
        email = idinfo.get("email")
        name = idinfo.get("name", "")
        picture_url = idinfo.get("picture")

        if not email:
            return Response({"error": "Invalid token: no email"}, status=400)

        # Handle user creation/login
        try:
            with transaction.atomic():
                user = User.objects.filter(email=email).first()

                if not user:
                    # Validate account types
                    valid_types = ["client", "freelancer"]
                    if not requested_account_types:
                        return Response(
                            {"error": "go to the registration page and select an account type"},
                            status=400,
                        )
                    if not all(acc_type in valid_types for acc_type in requested_account_types):
                        return Response({"error": "Invalid account_types"}, status=400)

                    # Safe name splitting
                    first_name = ""
                    last_name = ""

                    if name:
                        name_parts = name.strip().split()
                        if len(name_parts) >= 1:
                            first_name = name_parts[0]
                        if len(name_parts) >= 2:
                            last_name = " ".join(name_parts[1:])

                    # Create new user
                    username = email.split("@")[0]

                    user = User.objects.create(
                        email=email,
                        username=username,
                        first_name=first_name,
                        last_name=last_name,
                    )

                    random_password = generate_random_password()
                    user.set_password(random_password)
                    user.save()

                    # Create account types
                    for i, account_type in enumerate(requested_account_types):
                        UserAccountType.objects.create(
                            user=user,
                            account_type=account_type,
                            is_primary=(i == 0)
                        )

                        group_name = account_type.capitalize()
                        assign_user_to_group(user, group_name)

                    create_user_profiles(user, requested_account_types)

                    # CELERY INTEGRATION: Move profile completion to background task
                    update_profile_completion_task.delay(user.id)

                    # CELERY INTEGRATION: Send welcome email asynchronously
                    send_welcome_email_task.delay(user.id)

                    created = True
                else:
                    created = False

                # CELERY INTEGRATION: Handle profile picture asynchronously
                if picture_url and (created or not user.profile_picture):
                    process_profile_picture_task.delay(user.id, picture_url)

                # CELERY INTEGRATION: Sync user data with other services
                if created:
                    sync_user_data_with_jobs_service.delay(user.id)

            # Generate JWT tokens
            refresh = CustomRefreshToken.for_user(user)
            serializer = UserProfileSerializer(user)

            return Response(
                {
                    "user": serializer.data,
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                    "created": created,
                    "message": "Login successful. Profile setup tasks are being processed in the background."
                },
                status=200,
            )

        except Exception as e:
            print(f"=== DEBUG: Error in user creation/login: {e} ===")
            print(f"=== DEBUG: Error type: {type(e)} ===")
            import traceback
            traceback.print_exc()
            return Response({"error": str(e)}, status=400)

class GetUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        user_groups = list(user.groups.values_list("name", flat=True))
        user_permissions = list(user.get_all_permissions())

        profile_picture_url = (
            request.build_absolute_uri(user.profile_picture.url)
            if user.profile_picture
            else None
        )

        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "profile_picture": profile_picture_url,  # ✅ full image URL
            "account_types": list(user.account_types),
            "groups": user_groups,
            "permissions": user_permissions,
        })

class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()

            # Get account types from validated data
            account_types = serializer.validated_data.get("account_types", [])
            for account_type in account_types:
                group_name = account_type.capitalize()
                assign_user_to_group(user, group_name)

            # Trigger async tasks
            send_welcome_email_task.delay(user.id)
            update_profile_completion_task.delay(user.id)

            refresh = CustomRefreshToken.for_user(user)
            profile_serializer = UserProfileSerializer(user)

            return Response(
                {
                    "user": profile_serializer.data,
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                },
                status=status.HTTP_201_CREATED,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    permission_classes = [AllowAny]
    serializer_class = UserLoginSerializer

    @swagger_auto_schema(
        request_body=UserLoginSerializer,
        responses={
            200: openapi.Response('Successful login'),
            400: 'Bad request',
            401: 'Unauthorized'
        }
    )
    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")
        mfa_token = request.data.get("mfa_token")  # Optional MFA token

        if not email or not password:
            return Response(
                {"error": "Email and password are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request, username=email, password=password)
        if user is None:
            try:
                u = User.objects.get(email=email)
                u.increment_login_attempts()
            except User.DoesNotExist:
                pass
            return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.can_login():
            if user.is_account_locked:
                return Response(
                    {"error": "Account is temporarily locked due to too many failed login attempts"},
                    status=status.HTTP_423_LOCKED,
                )
            elif not user.is_active:
                return Response({"error": "Account is disabled"}, status=status.HTTP_403_FORBIDDEN)

        # Reset failed attempts after successful password validation
        user.reset_login_attempts()

        # Handle MFA if user.is_staff
        security_profile, _ = UserSecurity.objects.get_or_create(user=user)

        if user.is_staff:
            if not security_profile.mfa_secret or not security_profile.mfa_enabled:
                return Response(
                    {
                        "mfa_required": True,
                        "mfa_setup_required": True,
                        "message": "MFA setup is required for admin accounts",
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                if not mfa_token:
                    return Response(
                        {
                            "mfa_required": True,
                            "mfa_setup_required": False,
                            "message": "MFA token is required",
                        },
                        status=status.HTTP_200_OK,
                    )

                if not security_profile.verify_totp(mfa_token):
                    # Try backup code
                    if not security_profile.use_backup_code(mfa_token):
                        return Response({"error": "Invalid MFA token"}, status=status.HTTP_401_UNAUTHORIZED)

        # Generate JWT tokens
        refresh = CustomRefreshToken.for_user(user)

        # Save last login IP
        security_profile.last_login_ip = request.META.get("REMOTE_ADDR")
        security_profile.save(update_fields=["last_login_ip"])

        profile_serializer = UserProfileSerializer(user)

        return Response(
            {
                "user": profile_serializer.data,
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            }
        )


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Change user password"""
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid():
            user = request.user
            user.set_password(serializer.validated_data["new_password"])
            user.save()
            return Response({"message": "Password changed successfully"})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Legacy function for Google login (keeping for backward compatibility)
@csrf_exempt
def google_login(request):
    view = GoogleLoginView.as_view()
    return view(request)

