from functools import wraps

from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated


def has_group_permission(group_names):
    """
    Decorator to check if user belongs to specific groups
    Usage: @has_group_permission(['Admin', 'Moderator'])
    """
    if isinstance(group_names, str):
        group_names = [group_names]

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if request.user.is_authenticated:
                user_groups = request.user.groups.values_list("name", flat=True)
                if any(group in user_groups for group in group_names):
                    return view_func(request, *args, **kwargs)
            raise PermissionDenied("You don't have permission to access this resource")

        return _wrapped_view

    return decorator


def check_user_permission(user, permission_codename):
    """
    Check if user has specific permission
    """
    return user.has_perm(f"users.{permission_codename}")


def is_admin(user):
    """Check if user is in Admin group"""
    return user.groups.filter(name="Admin").exists()


def is_moderator(user):
    """Check if user is in Moderator group"""
    return user.groups.filter(name="Moderator").exists()


def is_client(user):
    """Check if user is in Client group"""
    return user.groups.filter(name="Client").exists()

class IsAdminUser(IsAuthenticated):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.is_staff