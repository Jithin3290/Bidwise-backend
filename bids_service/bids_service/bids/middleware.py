# bids/middleware.py
import logging
import time
from django.utils.deprecation import MiddlewareMixin
from .authentication import JWTAuthentication

logger = logging.getLogger(__name__)

from django.contrib.auth.models import AnonymousUser

class JWTAuthenticationMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # If request.user already set by AuthenticationMiddleware and is authenticated
        if getattr(request, "user", None) and request.user.is_authenticated:
            return None  # don’t override

        authenticator = JWTAuthentication()
        try:
            auth_result = authenticator.authenticate(request)
            if auth_result:
                user, token = auth_result
                request.user = user
                request.auth = token
            else:
                request.user = AnonymousUser()
                request.auth = None
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            request.user = AnonymousUser()
            request.auth = None
        return None


class RequestLoggingMiddleware(MiddlewareMixin):
    """Middleware to log API requests for monitoring"""

    def process_request(self, request):
        """Log incoming request"""
        request.start_time = time.time()

        # Log request details
        user_id = getattr(request.user, 'user_id', 'anonymous') if hasattr(request,
                                                                           'user') and request.user else 'anonymous'

        logger.info(
            f"Request: {request.method} {request.path} - User: {user_id} - IP: {self._get_client_ip(request)}"
        )

    def process_response(self, request, response):
        """Log response details"""
        if hasattr(request, 'start_time'):
            duration = time.time() - request.start_time

            user_id = getattr(request.user, 'user_id', 'anonymous') if hasattr(request,
                                                                               'user') and request.user else 'anonymous'

            logger.info(
                f"Response: {request.method} {request.path} - "
                f"Status: {response.status_code} - "
                f"Duration: {duration:.3f}s - "
                f"User: {user_id}"
            )

        return response

    def _get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class CORSMiddleware(MiddlewareMixin):
    """Custom CORS middleware for microservice communication"""

    def process_response(self, request, response):
        """Add CORS headers to response"""
        # Allow microservice communication
        allowed_origins = [
            'http://localhost:3000',
            'http://localhost:8000',  # Users service
            'http://localhost:8001',  # Jobs service
            'http://localhost:8080',  # API Gateway
            'http://127.0.0.1:3000',
            'http://127.0.0.1:8000',
            'http://127.0.0.1:8001',
            'http://127.0.0.1:8080',
        ]

        origin = request.META.get('HTTP_ORIGIN')
        if origin in allowed_origins:
            response['Access-Control-Allow-Origin'] = origin

        response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
        response['Access-Control-Allow-Headers'] = (
            'Content-Type, Authorization, X-Requested-With, Accept, Origin, '
            'X-CSRFToken, X-Service-Token'
        )
        response['Access-Control-Allow-Credentials'] = 'true'
        response['Access-Control-Max-Age'] = '86400'  # 24 hours

        return response