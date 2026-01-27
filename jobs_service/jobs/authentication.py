import jwt
from django.conf import settings
from rest_framework import authentication, exceptions


class MockUser:
    """Mock user object for JWT authentication"""

    def __init__(self, user_id, payload):
        self.id = user_id
        self.pk = user_id  # Add pk attribute for Django compatibility
        self.user_id = user_id
        self.payload = payload
        self.is_authenticated = True
        self.is_active = True
        self.is_anonymous = False
        self.username = payload.get('username', f'user_{user_id}')

    def __str__(self):
        return f"User {self.user_id}"

    def get_username(self):
        return self.username


class JWTAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return None

        token = auth_header.split(' ')[1]
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
            user_id = payload.get('user_id') or payload.get('id')

            if not user_id:
                raise exceptions.AuthenticationFailed('Invalid token: no user ID found')

            # Create a mock user object that Django REST Framework expects
            user = MockUser(user_id, payload)

            # Also set user_id on request for backward compatibility
            request.user_id = user_id
            request.jwt_payload = payload

            return (user, None)

        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed('Token expired')
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed('Invalid token')

