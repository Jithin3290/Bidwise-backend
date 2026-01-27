# notifications/authentication.py
import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
import logging

logger = logging.getLogger(__name__)


class ServiceAuthentication(BaseAuthentication):
    """Authentication for service-to-service communication"""

    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION')

        if not auth_header or not auth_header.startswith('Bearer '):
            return None

        token = auth_header.split(' ')[1]
        service_token = getattr(settings, 'SERVICE_TOKEN', 'secure-service-token-123')

        if token != service_token:
            raise AuthenticationFailed('Invalid service token')

        # Return a simple service user object
        class ServiceUser:
            def __init__(self):
                self.id = 'service'
                self.user_id = 'service'
                self.is_authenticated = True
                self.is_service = True
                self.username = 'service'
                self.email = 'service@system.com'

            @property
            def pk(self):
                return self.id

        return (ServiceUser(), token)


class JWTAuthentication(BaseAuthentication):
    """JWT Authentication for user requests"""

    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION')

        if not auth_header or not auth_header.startswith('Bearer '):
            return None

        token = auth_header.split(' ')[1]

        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
            user_id = payload.get('user_id')

            if not user_id:
                raise AuthenticationFailed('Invalid token payload')

            # Create a simple user object
            class AuthenticatedUser:
                def __init__(self, user_data):
                    self.id = str(user_data.get('user_id'))
                    self.user_id = str(user_data.get('user_id'))
                    self.username = user_data.get('username', '')
                    self.email = user_data.get('email', '')
                    self.account_types = user_data.get('account_types', [])
                    self.is_authenticated = True

                @property
                def pk(self):
                    return self.id

                def __str__(self):
                    return f"User {self.username} ({self.user_id})"

            user = AuthenticatedUser(payload)
            return (user, token)

        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed('Token has expired')
        except jwt.InvalidTokenError as e:
            logger.error(f"Invalid token error: {e}")
            raise AuthenticationFailed('Invalid token')
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            raise AuthenticationFailed('Authentication failed')