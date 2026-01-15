# users/service_urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Service-to-service endpoints
    path('users/<int:user_id>/profile/', views.get_user_profile_for_service, name='service-user-profile'),
    path('users/batch/', views.get_users_batch_for_service, name='service-users-batch'),
# Add these paths for bids service communication
    path('verify-token/', views.verify_token_for_service, name='service-verify-token'),
]