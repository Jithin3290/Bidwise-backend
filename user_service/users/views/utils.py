"""
Utility functions and classes shared across views
"""
import random
import string
import requests
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from rest_framework.pagination import PageNumberPagination
from rest_framework_simplejwt.tokens import RefreshToken

from ..models import (
    FreelancerProfile,
    ClientProfile,
    UserProfessionalProfile,
    UserSecurity,
    UserPreferences,
)


class CustomRefreshToken(RefreshToken):
    @classmethod
    def for_user(cls, user):
        token = super().for_user(user)

        # Add custom claims including account_types
        token['user_id'] = str(user.id)
        token['username'] = user.username
        token['email'] = user.email
        token['account_types'] = list(user.account_types)
        token['is_staff'] = user.is_staff
        token['is_superuser'] = user.is_superuser

        return token


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def save_profile_picture_from_url(user, url):
    """Save profile picture from URL"""
    if not url:
        return
    try:
        response = requests.get(url)
        if response.status_code == 200:
            user.profile_picture.save(
                f"{user.pk}.jpg", ContentFile(response.content), save=True
            )
    except Exception:
        pass


def generate_random_password(length=12):
    """Generate a secure random password"""
    chars = string.ascii_letters + string.digits + string.punctuation
    return "".join(random.choice(chars) for _ in range(length))


def assign_user_to_group(user, group_name):
    """Assign user to a specific group"""
    try:
        group = Group.objects.get(name=group_name)
        user.groups.add(group)
        return True
    except Group.DoesNotExist:
        return False


def create_user_profiles(user, account_types):
    """Create user profiles based on account types"""
    # Create base profiles
    UserProfessionalProfile.objects.get_or_create(user=user)
    UserSecurity.objects.get_or_create(user=user)
    UserPreferences.objects.get_or_create(user=user)

    # Create specific profiles based on account types
    for account_type in account_types:
        if account_type == "freelancer":
            FreelancerProfile.objects.get_or_create(user=user)
        elif account_type == "client":
            ClientProfile.objects.get_or_create(user=user)