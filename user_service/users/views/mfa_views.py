"""
Multi-Factor Authentication (MFA) views
"""
from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from ..models import UserSecurity
from .utils import CustomRefreshToken


class MFASetupView(APIView):
    """Setup MFA for user"""
    permission_classes = [AllowAny]

    def post(self, request):
        # Get user from credentials instead of request.user
        email = request.data.get("email")
        password = request.data.get("password")

        if not email or not password:
            return Response(
                {"error": "Email and password required for MFA setup"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Authenticate user
        user = authenticate(username=email, password=password)
        if not user:
            return Response(
                {"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED
            )

        # Only allow admin users to setup MFA
        if not user.is_staff:
            return Response(
                {"error": "MFA is only available for admin users"},
                status=status.HTTP_403_FORBIDDEN,
            )

        security_profile, created = UserSecurity.objects.get_or_create(user=user)

        # Generate new secret if not exists
        if not security_profile.mfa_secret:
            security_profile.generate_mfa_secret()

        # Generate QR code
        qr_code = security_profile.generate_qr_code()

        return Response(
            {
                "qr_code": qr_code,
                "secret": security_profile.mfa_secret,
                "setup_complete": False,
            }
        )


class MFAVerifySetupView(APIView):
    """Verify MFA setup with token and issue JWT tokens"""
    permission_classes = [AllowAny]

    def post(self, request):
        token = request.data.get("token")
        email = request.data.get("email")
        password = request.data.get("password")

        if not token:
            return Response(
                {"error": "Token is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        if not email or not password:
            return Response(
                {"error": "Email and password required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Authenticate user
        user = authenticate(username=email, password=password)
        if not user:
            return Response(
                {"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED
            )

        security_profile = getattr(user, "security_profile", None)
        if not security_profile:
            return Response(
                {"error": "MFA not initialized"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Verify the token
        if security_profile.verify_totp(token):
            # Enable MFA and generate backup codes
            security_profile.mfa_enabled = True
            backup_codes = security_profile.generate_backup_codes()
            security_profile.save(update_fields=["mfa_enabled"])

            # Generate JWT tokens
            refresh = CustomRefreshToken.for_user(user)
            access = str(refresh.access_token)

            return Response(
                {
                    "success": True,
                    "message": "MFA has been successfully enabled",
                    "backup_codes": backup_codes,
                    "refresh": str(refresh),
                    "access": access,
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "username": user.username,
                        "account_types": getattr(user, "account_types", []),
                    },
                }
            )
        else:
            return Response(
                {"error": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST
            )


class MFAStatusView(APIView):
    """Get MFA status for user"""
    permission_classes = [AllowAny]

    def get(self, request):
        user = request.user
        security_profile = getattr(user, "security_profile", None)

        if not security_profile:
            return Response(
                {
                    "mfa_enabled": False,
                    "is_admin": user.is_staff,
                    "mfa_required": user.is_staff,
                }
            )

        return Response(
            {
                "mfa_enabled": security_profile.mfa_enabled,
                "is_admin": user.is_staff,
                "mfa_required": user.is_staff,
                "backup_codes_count": len(security_profile.mfa_backup_codes),
            }
        )