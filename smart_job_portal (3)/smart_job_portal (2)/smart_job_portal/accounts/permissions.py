from rest_framework import permissions

from .models import UserProfile


def get_user_role(user):
    """Return the user's role, or None if anonymous / no profile (e.g. createsuperuser)."""
    if not user or not user.is_authenticated:
        return None
    return UserProfile.objects.filter(user=user).values_list('role', flat=True).first()


class IsEmployer(permissions.BasePermission):
    message = 'Only employers can perform this action.'

    def has_permission(self, request, view):
        return get_user_role(request.user) == 'employer'


class IsJobSeeker(permissions.BasePermission):
    message = 'Only job seekers can perform this action.'

    def has_permission(self, request, view):
        return get_user_role(request.user) == 'jobseeker'


class IsEmployerOrReadOnly(permissions.BasePermission):
    """Anyone can read; only employers can write; only the owner can modify an object."""
    message = 'Only employers can create or modify jobs.'

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return get_user_role(request.user) == 'employer'

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.employer_id == request.user.id
