from rest_framework import permissions


class IsAdminEdit(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        if request.method in permissions.SAFE_METHODS:
            return True
        return False


class IsFavouriteOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        if obj.favourite.user == request.user:
            return True
        if obj.favourite.id == request.session.get("fav_id", None):
            return True
        return False
