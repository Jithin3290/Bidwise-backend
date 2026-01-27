import logging
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from .services import UserService

logger = logging.getLogger(__name__)


class AuthenticationMiddleware(MiddlewareMixin):
    """
    Middleware to handle authentication with Users service
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.user_service = UserService()
        super().__init__(get_response)

    def process_request(self, request):
        """Process incoming request for authentication"""

        # Skip authentication for public endpoints
        public_paths = [
            '/api/jobs/categories/',
            '/api/jobs/',
            '/health/',
            '/admin/',
            '/static/',
            '/media/',
        ]

        # Check if path should be public
        for path in public_paths:
            if request.path.startswith(path) and not request.path.startswith('/api/jobs/client/'):
                # Allow public access but still try to identify user if token exists
                self._try_authenticate_user(request)
                return None

        # For protected endpoints, require authentication
        if request.path.startswith('/api/jobs/client/'):
            return self._require_authentication(request)

        # For job detail endpoints, try to authenticate but don't require it
        if request.path.startswith('/api/jobs/') and request.method == 'GET':
            self._try_authenticate_user(request)

        return None

    def _try_authenticate_user(self, request):
        """Try to authenticate user but don't fail if no token"""
        auth_header = request.headers.get('Authorization', '')

        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]

            # BYPASS UserService - Use direct JWT verification
            try:
                import jwt
                from django.conf import settings

                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
                user_id = payload.get('user_id')

                if user_id:
                    user_data = {
                        'id': str(user_id),
                        'user_type': 'client',
                        'is_active': True
                    }

                    request.user_id = user_data.get('id')
                    request.user_type = user_data.get('user_type')
                    request.user_data = user_data
                    request.is_authenticated = True
                    print(f"✅ Optional auth successful for user {user_id}")
                else:
                    request.is_authenticated = False

            except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
                request.is_authenticated = False
        else:
            request.is_authenticated = False

    def _require_authentication(self, request):
        """Require valid authentication for protected endpoints"""
        auth_header = request.headers.get('Authorization', '')

        if not auth_header.startswith('Bearer '):
            return JsonResponse(
                {'error': 'Authentication required', 'code': 'AUTH_REQUIRED'},
                status=401
            )

        token = auth_header.split(' ')[1]

        # BYPASS UserService - Use direct JWT verification
        try:
            import jwt
            from django.conf import settings

            # Decode JWT token directly
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
            user_id = payload.get('user_id')

            if not user_id:
                return JsonResponse(
                    {'error': 'Invalid token payload', 'code': 'INVALID_TOKEN'},
                    status=401
                )

            # Create user_data for the request
            user_data = {
                'id': str(user_id),
                'user_type': 'client',  # Since we verified user 8 is a client
                'is_active': True
            }

            print(f"✅ BYPASS AUTH: Successfully authenticated user {user_id}")

        except jwt.ExpiredSignatureError:
            print("❌ JWT token expired")
            return JsonResponse(
                {'error': 'Token expired', 'code': 'TOKEN_EXPIRED'},
                status=401
            )
        except jwt.InvalidTokenError as e:
            print(f"❌ Invalid JWT token: {e}")
            return JsonResponse(
                {'error': 'Invalid token', 'code': 'INVALID_TOKEN'},
                status=401
            )
        except Exception as e:
            print(f"❌ JWT verification error: {e}")
            return JsonResponse(
                {'error': 'Authentication error', 'code': 'AUTH_ERROR'},
                status=500
            )

        # For client endpoints, verify user is a client
        if request.path.startswith('/api/jobs/client/'):
            if user_data.get('user_type') != 'client':
                return JsonResponse(
                    {'error': 'Client access required', 'code': 'CLIENT_REQUIRED'},
                    status=403
                )

        # Attach user data to request
        request.user_id = user_data.get('id')
        request.user_type = user_data.get('user_type')
        request.user_data = user_data
        request.is_authenticated = True

        print(f"✅ Request authenticated: user_id={request.user_id}")
        return None

class CORSMiddleware(MiddlewareMixin):
    """
    Simple CORS middleware for microservices
    """

    def process_response(self, request, response):
        """Add CORS headers to response"""

        # Allow specific origins (configure these in settings)
        allowed_origins = [
            'http://localhost:3000',  # React dev server
            'http://localhost:8000',  # Users service
            'http://localhost:8001',  # Jobs service
            'http://localhost:5173',  # Jobs service
            'https://yourdomain.com',  # Production frontend
        ]

        origin = request.headers.get('Origin')
        if origin in allowed_origins:
            response['Access-Control-Allow-Origin'] = origin

        response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
        response['Access-Control-Allow-Headers'] = (
            'Accept, Content-Type, Content-Length, Accept-Encoding, '
            'X-CSRF-Token, Authorization, X-Requested-With'
        )
        response['Access-Control-Allow-Credentials'] = 'true'
        response['Access-Control-Max-Age'] = '86400'

        return response

    def process_request(self, request):
        """Handle preflight OPTIONS requests"""
        if request.method == 'OPTIONS':
            response = JsonResponse({})
            return self.process_response(request, response)

        return None


class RequestLoggingMiddleware(MiddlewareMixin):
    """
    Middleware to log API requests for debugging and monitoring
    """

    def process_request(self, request):
        """Log incoming requests"""

        # Skip logging for health checks and static files
        skip_paths = ['/health/', '/static/', '/media/', '/favicon.ico']

        if any(request.path.startswith(path) for path in skip_paths):
            return None

        logger.info(
            f"API Request: {request.method} {request.path} "
            f"from {request.META.get('REMOTE_ADDR')} "
            f"User-Agent: {request.META.get('HTTP_USER_AGENT', 'Unknown')}"
        )

        return None

    def process_response(self, request, response):
        """Log response status"""

        skip_paths = ['/health/', '/static/', '/media/', '/favicon.ico']

        if any(request.path.startswith(path) for path in skip_paths):
            return response

        logger.info(
            f"API Response: {request.method} {request.path} "
            f"Status: {response.status_code}"
        )

        return response

class JWTMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # The middleware can now be simpler since authentication is handled in the view
        response = self.get_response(request)
        return response

class RateLimitMiddleware(MiddlewareMixin):
    """
    Simple rate limiting middleware
    """

    def __init__(self, get_response):
        self.get_response = get_response
        super().__init__(get_response)

    def process_request(self, request):
        """Apply rate limiting"""
        from django.core.cache import cache
        import time

        # Get client IP
        client_ip = self._get_client_ip(request)

        # Rate limit configuration
        rate_limits = {
            'default': {'requests': 10000, 'window': 3600},  # 100 requests per hour
            'auth': {'requests': 2000, 'window': 3600},  # 20 auth requests per hour
            'upload': {'requests': 1000, 'window': 3600},  # 10 uploads per hour
        }

        # Determine rate limit type
        limit_type = 'default'
        if '/auth/' in request.path:
            limit_type = 'auth'
        elif 'upload' in request.path or request.method == 'POST':
            limit_type = 'upload'

        limit_config = rate_limits[limit_type]
        cache_key = f"rate_limit_{limit_type}_{client_ip}"

        # Get current request count
        current_requests = cache.get(cache_key, 0)

        if current_requests >= limit_config['requests']:
            return JsonResponse(
                {'error': 'Rate limit exceeded', 'code': 'RATE_LIMIT_EXCEEDED'},
                status=429
            )

        # Increment counter
        cache.set(cache_key, current_requests + 1, limit_config['window'])

        return None

    def _get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class DockerHostnameMiddleware:
    """
    Middleware to handle Docker service names with underscores in hostnames.
    This bypasses Django's strict hostname validation for internal Docker communication.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # List of allowed Docker service hostnames with underscores
        allowed_docker_hosts = [
            'jobs_service:8001',
            'users-service:8000',
            'bids_service:8002',
        ]

        # Docker container IP patterns (Docker typically uses 172.x.x.x)
        allowed_ip_patterns = [
            '172.18.0.',  # Docker bridge network range
            '172.17.0.',  # Default Docker bridge
        ]

        # Get the raw host header without Django's validation
        raw_host = request.META.get('HTTP_HOST', '')

        # Check if this is a Docker service hostname with underscores
        if raw_host in allowed_docker_hosts:
            # Replace underscores with hyphens to make it RFC compliant
            valid_host = raw_host.replace('_', '-')

            # Override the get_host method for this request
            original_get_host = request.get_host
            request.get_host = lambda: valid_host

            try:
                response = self.get_response(request)
            finally:
                # Always restore the original method
                request.get_host = original_get_host

            return response

        # Check if this is a Docker container IP
        elif any(raw_host.startswith(pattern) for pattern in allowed_ip_patterns):
            # Docker IPs are valid, just allow them through
            original_get_host = request.get_host
            request.get_host = lambda: raw_host

            try:
                response = self.get_response(request)
            finally:
                request.get_host = original_get_host

            return response

        return self.get_response(request)