from rest_framework import permissions
import re

class PublicDownloadPermission(permissions.BasePermission):
    """
    Разрешает доступ к определенным публичным эндпоинтам без аутентификации
    """
    def has_permission(self, request, view):
        public_patterns = [
            r"^/api/generation-tasks/[^/]+/download/$",
            r"^/api/generation-tasks/[^/]+/image/$",
            r"^/api/generation-tasks/[^/]+/image-file/$",
        ]
        
        if any(re.match(pattern, request.path) for pattern in public_patterns):
            return True
            
        return bool(request.user and request.user.is_authenticated)