# bids_service/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from django.http import JsonResponse
from django.utils import timezone


# Simple health check function
def health_check(request):
    return JsonResponse({
        'status': 'healthy',
        'service': 'bids-service',
        'timestamp': timezone.now(),
        'version': '1.0.0',
    })


# Swagger/OpenAPI schema
schema_view = get_schema_view(
    openapi.Info(
        title="Bids Service API",
        default_version='v1',
        description="API documentation for the Bids microservice",
        terms_of_service="https://www.yourcompany.com/terms/",
        contact=openapi.Contact(email="api@yourcompany.com"),
        license=openapi.License(name="MIT License"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),

    # Health check endpoint (at root level for Docker health checks)
    path('health/', health_check, name='health-check'),

    # API endpoints (removed namespace to avoid conflict)
    path('api/bids/', include('bids.urls')),

    # API Documentation
    path('api/docs/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('api/redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path('api/schema/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
]

# Add debug toolbar URLs only when it's enabled
if settings.DEBUG and 'debug_toolbar' in settings.INSTALLED_APPS:
    urlpatterns = [
                      path('__debug__/', include('debug_toolbar.urls')),
                  ] + urlpatterns

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)