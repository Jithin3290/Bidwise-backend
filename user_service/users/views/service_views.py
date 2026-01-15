"""
Service-to-service communication views
"""
import jwt
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from ..models import User


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def get_user_profile_for_service(request, user_id):
    """Get user profile for inter-service communication"""

    # Verify service token
    service_token = request.headers.get('Authorization', '').replace('Bearer ', '')
    expected_token = getattr(settings, 'SERVICE_TOKEN', 'secure-service-token-123')

    if service_token != expected_token:
        return Response({'error': 'Invalid service token'}, status=403)

    try:
        user = User.objects.get(id=user_id)

        # Get profile data
        profile = getattr(user, 'freelancer_profile', None) or getattr(user, 'client_profile', None)

        # Use username or email if first_name/last_name are empty
        first_name = user.first_name or user.username.split('@')[0] or 'User'
        last_name = user.last_name or ''

        # Basic user data
        user_data = {
            'id': user.id,
            'username': user.username,
            'first_name': first_name,
            'last_name': last_name,
            'email': user.email,
            'date_joined': user.date_joined.isoformat() if user.date_joined else None,
            'created_at': user.created_at.isoformat() if hasattr(user, 'created_at') and user.created_at else None,
            'is_active': user.is_active,
            'profile_picture': user.profile_picture.url if user.profile_picture else None,
            'country': getattr(user, 'country', ''),
            'city': getattr(user, 'city', ''),
            'location': f"{getattr(user, 'city', '')}, {getattr(user, 'country', '')}".strip(', '),
            'is_verified': getattr(user, 'is_verified', False),
        }

        # Add profile-specific data
        if profile:
            user_data.update({
                'rating': float(getattr(profile, 'average_rating', 0) or 0),
                'total_spent': float(getattr(profile, 'total_spent', 0) or 0),
            })
        else:
            user_data.update({
                'rating': 0.0,
                'total_spent': 0.0,
            })

        # Default values
        user_data['jobs_posted'] = 0

        return Response(user_data)

    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=404)
    except Exception as e:
        import traceback
        print(f"Error fetching user {user_id}: {e}")
        print(traceback.format_exc())
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_token_for_service(request):
    """Verify JWT token for service-to-service communication"""
    # Verify service token
    auth_header = request.headers.get('Authorization', '')
    service_token = getattr(settings, 'SERVICE_TOKEN', 'secure-service-token-123')

    if not auth_header.startswith(f'Bearer {service_token}'):
        return Response({'error': 'Unauthorized service'}, status=401)

    token = request.data.get('token')
    if not token:
        return Response({'error': 'Token required'}, status=400)

    try:
        # Verify the user token
        UntypedToken(token)  # This will raise an exception if invalid

        # Decode the token to get user info
        decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        user_id = decoded.get('user_id')

        if not user_id:
            return Response({'error': 'Invalid token payload'}, status=400)

        # Get user data
        user = User.objects.get(id=user_id)
        account_types = list(user.account_types)

        return Response({
            'valid': True,
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'account_types': account_types,
            'is_active': user.is_active
        })

    except (InvalidToken, TokenError, User.DoesNotExist, jwt.InvalidTokenError) as e:
        return Response({'error': 'Invalid token'}, status=400)
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def get_users_batch_for_service(request):
    """Batch fetch user profiles for service-to-service communication"""
    # Verify service token
    auth_header = request.headers.get('Authorization', '')
    service_token = settings.SERVICE_TOKEN

    if not auth_header.startswith(f'Bearer {service_token}'):
        return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)

    user_ids = request.data.get('user_ids', [])

    users = User.objects.filter(id__in=user_ids).select_related('profile')

    users_data = []
    for user in users:
        users_data.append({
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'profile_picture': user.profile.profile_picture.url if user.profile.profile_picture else None,
            'rating': float(user.profile.rating) if hasattr(user, 'profile') else 0.0,
            'total_spent': float(user.profile.total_spent) if hasattr(user, 'profile') else 0.0,
            'location': user.profile.location if hasattr(user, 'profile') else '',
            'is_verified': user.profile.is_verified if hasattr(user, 'profile') else False,
            'date_joined': user.date_joined,
        })

    return Response({'users': users_data})