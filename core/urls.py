from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    UserViewSet, ChatViewSet, MessageViewSet, CustomTokenObtainPairView,
    PromptTemplateViewSet, PromptParametersViewSet, PromptActionsViewSet,
    MediaGenerationTaskViewSet
)

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")
router.register(r"chats", ChatViewSet, basename="chat")
router.register(r"messages", MessageViewSet, basename="message")
router.register(r"prompttemplates", PromptTemplateViewSet, basename="prompttemplate")
router.register(r"promptparameters", PromptParametersViewSet, basename="promptparameters")
router.register(r"promptactions", PromptActionsViewSet, basename="promptactions")
router.register(r"generation-tasks", MediaGenerationTaskViewSet, basename="generationtask")

urlpatterns = [
    path("", include(router.urls)),
    path("auth/login/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

]
