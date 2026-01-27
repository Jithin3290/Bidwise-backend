# jobs_service/urls.py - Main URL Configuration
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

@require_http_methods(["GET"])
def api_root(request):
    """API Root endpoint with service information"""
    return JsonResponse({
        'service': 'Jobs Service',
        'version': '1.0.0',
        'description': 'Microservice for managing job postings and applications',
        'endpoints': {
            'jobs': '//',
            'categories': '/api/jobs/categories/',
            'skills': '/api/jobs/skills/',
            'client_jobs': '/api/jobs/client/jobs/',
            'health': '/api/jobs/health/',
            'admin': '/admin/',
        },
        'authentication': {
            'type': 'JWT Bearer Token',
            'header': 'Authorization: Bearer <token>',
            'users_service': settings.USERS_SERVICE_URL,
        },
        'documentation': {
            'swagger': '/api/docs/',
            'postman': '/api/postman/',
        }
    })

@require_http_methods(["GET"])
def health_check(request):
    """Simple health check endpoint"""
    try:
        from django.db import connection
        from django.core.cache import cache
        
        # Test database connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        
        # Test cache connection
        cache.set('health_check', 'ok', 1)
        cache_status = cache.get('health_check') == 'ok'
        
        return JsonResponse({
            'status': 'healthy',
            'service': 'jobs-service',
            'database': 'connected',
            'cache': 'connected' if cache_status else 'disconnected',
            'version': '1.0.0'
        })
    except Exception as e:
        return JsonResponse({
            'status': 'unhealthy',
            'service': 'jobs-service',
            'error': str(e),
            'version': '1.0.0'
        }, status=503)
# jobs/urls.py
from django.urls import path
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(
    openapi.Info(
        title="Jobs Service API",
        default_version='v1',
        description="API documentation for Jobs Service",
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)


    # … your existing routes here …



urlpatterns = [
    # Admin interface
    path('admin/', admin.site.urls),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),

    # API root
    path('api/', api_root, name='api-root'),
    
    # Health check
    path('health/', health_check, name='health-check'),
    
    # Jobs API
    path('api/jobs/', include('jobs.urls')),
    
    # API Documentation (optional - you can add swagger later)
    # path('api/docs/', include('drf_spectacular.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    
    # Add debug toolbar URLs if available
    try:
        import debug_toolbar
        urlpatterns = [
            path('__debug__/', include(debug_toolbar.urls)),
        ] + urlpatterns
    except ImportError:
        pass

# Custom error handlers
def custom_404(request, exception):
    """Custom 404 handler"""
    return JsonResponse({
        'error': 'Endpoint not found',
        'status_code': 404,
        'message': f"The endpoint '{request.path}' was not found.",
        'available_endpoints': [
            '/api/jobs/',
            '/api/jobs/categories/',
            '/api/jobs/skills/',
            '/api/jobs/client/jobs/',
            '/health/',
        ]
    }, status=404)

def custom_500(request):
    """Custom 500 handler"""
    return JsonResponse({
        'error': 'Internal server error',
        'status_code': 500,
        'message': 'An unexpected error occurred. Please try again later.',
        'contact': 'support@yourcompany.com'
    }, status=500)

# Set custom error handlers
handler404 = custom_404
handler500 = custom_500