# bids/authentication.py
import logging
import requests
import jwt
from django.conf import settings
from django.core.cache import cache
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
import hashlib

logger = logging.getLogger(__name__)


# bids/authentication.py - Update the AuthenticatedUser class

class AuthenticatedUser:
    """Lightweight user object for authenticated requests"""

    def __init__(self, user_data):
        self.user_id = str(user_data.get('user_id'))  # Make sure this is set
        self.id = user_data.get('user_id')  # Django compatibility
        self.pk = user_data.get('user_id')  # Django convention
        self.username = user_data.get('username', '')
        self.email = user_data.get('email', '')
        self.account_types = user_data.get('account_types', [])
        self.is_active = user_data.get('is_active', True)
        self.user_type = self._determine_primary_type()

        # Store full user data
        self._user_data = user_data

    def _determine_primary_type(self):
        """Determine primary user type from account_types"""
        if 'admin' in self.account_types:
            return 'admin'
        elif 'client' in self.account_types:
            return 'client'
        elif 'freelancer' in self.account_types:
            return 'freelancer'
        else:
            return self.account_types[0] if self.account_types else 'client'

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_user_data(self):
        """Get full user data"""
        return self._user_data

class JWTAuthentication(BaseAuthentication):
    """JWT Authentication using Users Service with fallback to local verification"""

    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION')

        if not auth_header or not auth_header.startswith('Bearer '):
            return None

        token = auth_header.split(' ')[1] if len(auth_header.split(' ')) > 1 else None
        if not token:
            return None

        user = self._verify_token_with_users_service(token)
        if not user:
            user = self._verify_token_locally(token)

        if not user:
            raise AuthenticationFailed('Invalid or expired token')

        if not user.is_active:
            raise AuthenticationFailed('User account is disabled')

        return (user, token)

    def _verify_token_with_users_service(self, token):
        """Verify JWT token with Users Service"""
        # cache_key = f"user_token_{hashlib.sha256(token.encode()).hexdigest()}"
        # cached_user = cache.get(cache_key)
        #
        # if cached_user:
        #     logger.debug("Token verification cache hit")
        #     # Wrap cached dict into AuthenticatedUser
        #     return AuthenticatedUser(cached_user)

        try:
            users_service_url = getattr(settings, 'USERS_SERVICE_URL', 'http://localhost:8000')
            auth_url = f"{users_service_url}/api/auth/user/"

            response = requests.get(
                auth_url,
                headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                timeout=10
            )

            if response.status_code == 200:
                user_data = response.json()
                transformed_data = {
                    'user_id': user_data.get('id'),
                    'id': user_data.get('id'),
                    'username': user_data.get('username'),
                    'email': user_data.get('email'),
                    'account_types': user_data.get('account_types', []),
                    'is_active': user_data.get('is_active', True),
                    'full_name': user_data.get('full_name', ''),
                    'profile_picture': user_data.get('profile_picture'),
                }

                # Cache the dict, not the AuthenticatedUser
                # cache.set(cache_key, transformed_data, 300)
                logger.debug(f"Token verified and cached for user {transformed_data['id']}")

                return AuthenticatedUser(transformed_data)

            else:
                logger.warning(f"Token verification failed: {response.status_code} - {response.text}")
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Error verifying token with Users Service: {e}")
            return None

    def _verify_token_locally(self, token):
        """Verify JWT token locally as fallback"""
        try:
            # Use the same secret key as the main application
            secret_key = getattr(settings, 'SECRET_KEY')

            # Decode the token
            payload = jwt.decode(token, secret_key, algorithms=['HS256'])

            user_id = payload.get('user_id')
            if not user_id:
                logger.warning("No user_id in token payload")
                return None

            # Create basic user data from token
            user_data = {
                'id': str(user_id),
                'user_id': str(user_id),
                'username': payload.get('username', ''),
                'email': payload.get('email', ''),
                'account_types': payload.get('account_types', ['client']),
                'is_active': True,
                'full_name': '',
                'profile_picture': None,
            }

            logger.info(f"Local token verification successful for user: {user_id}")
            return user_data

        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
        except Exception as e:
            logger.error(f"Error in local token verification: {e}")
            return None