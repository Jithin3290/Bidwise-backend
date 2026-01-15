"""
Email verification views
"""
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from ..utils import sqs


class SendEmailVerificationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            user = request.user

            if user.is_verified:
                return Response(
                    {"error": "Email is already verified"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            verification_code = user.generate_email_verification_token()

            # Send to SQS with task name and payload
            sqs.send_to_sqss("send_email_verification", {
                "user_id": user.id,
                "email": user.email,
                "full_name": user.full_name or user.username,
                "verification_code": verification_code
            })

            return Response(
                {"message": "Verification email queued for sending"},
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"error": f"Failed to queue verification email: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class VerifyEmailCodeView(APIView):
    """Verify email using the provided code"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            user = request.user
            code = request.data.get("code", "").strip()

            if not code:
                return Response(
                    {"error": "Verification code is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if len(code) != 6 or not code.isdigit():
                return Response(
                    {"error": "Invalid verification code format"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Check if email is already verified
            if user.is_verified:
                return Response(
                    {"error": "Email is already verified"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Validate the token
            if not user.is_email_verification_token_valid(code):
                security_profile = getattr(user, "security_profile", None)
                if (
                    security_profile
                    and security_profile.email_verification_expires
                    and timezone.now() > security_profile.email_verification_expires
                ):
                    user.clear_email_verification_token()
                    return Response(
                        {
                            "error": "Verification code has expired. Please request a new one."
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                else:
                    return Response(
                        {"error": "Invalid verification code"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # Mark email as verified and clear token
            user.is_verified = True
            user.clear_email_verification_token()
            user.save(update_fields=["is_verified"])

            return Response(
                {"message": "Email verified successfully"}, status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                {"error": f"An unexpected error occurred: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def resend_verification_email(request):
    """Resend verification email"""
    pass