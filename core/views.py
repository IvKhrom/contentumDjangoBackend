# views.py
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from django.shortcuts import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter

from .models import User, Chat, Message, UserRole, MessageType, PromptTemplate, PromptParameters, PromptHistory, MediaGenerationTask, AuditLog
from .serializers import (
    UserSerializer, UserRegistrationSerializer, UserUpdateSerializer,
    CustomTokenObtainPairSerializer, ChatSerializer, MessageSerializer,
    ChatCreateSerializer, AdminChatSerializer,
    PromptTemplateSerializer, PromptParametersSerializer, PromptAssembleSerializer, PromptHistorySerializer, MediaGenerationTaskSerializer
)
from .utils import (
    assemble_prompt_from_template, simple_semantic_vector_from_params, 
    enrich_prompt_with_gigachat, quality_check_generated, 
    handle_user_message_and_advance, paraphrase_prompt, get_default_prompt_template,
    get_empty_chat
)

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter, SearchFilter]
    filterset_fields = ["role", "isActive", "dateJoined"]
    ordering_fields = ["dateJoined", "email", "fullName"]
    search_fields = ["email", "fullName"]

    def get_serializer_class(self):
        if self.action in ("create",):
            return UserRegistrationSerializer
        if self.action in ("partial_update", "update"):
            return UserUpdateSerializer
        return UserSerializer

    def get_permissions(self):
        if self.action == "create":
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        # Проверка для генерации схемы Swagger
        if getattr(self, 'swagger_fake_view', False):
            return User.objects.none()
            
        user = self.request.user
        if not user.is_authenticated:
            return User.objects.none()
        if user.role == UserRole.ADMIN:
            return User.objects.all()
        return User.objects.filter(id=user.id)

    def create(self, request, *args, **kwargs):
        serializer = UserRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        AuditLog.objects.create(
            user=user,
            action="user_registration",
            model_name="User",
            object_id=str(user.id),
            details={"email": user.email, "role": user.role}
        )
        
        return Response({
            "status": "success", 
            "message": "Пользователь создан", 
            "data": UserSerializer(user).data
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def me(self, request):
        return Response({
            "status": "success", 
            "message": "Профиль", 
            "data": UserSerializer(request.user).data
        })

    @action(detail=False, methods=["get"])
    def summary(self, request):
        from .utils import get_user_chats_summary
        data = get_user_chats_summary(request.user)
        return Response({
            "status": "success", 
            "message": "Сводка", 
            "data": data
        })

    def list(self, request, *args, **kwargs):
        if request.user.role != UserRole.ADMIN:
            return Response({
                "status": "error", 
                "message": "Доступ запрещён"
            }, status=status.HTTP_403_FORBIDDEN)
        return super().list(request, *args, **kwargs)

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

class ChatViewSet(viewsets.ModelViewSet):
    serializer_class = ChatSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter, SearchFilter]
    filterset_fields = ["isActive", "createdAt", "updatedAt"]
    ordering_fields = ["createdAt", "updatedAt", "title"]
    search_fields = ["title", "user__email", "user__fullName"]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Chat.objects.none()
            
        user = self.request.user
        if user.role == UserRole.ADMIN:
            return Chat.objects.all()
        return Chat.objects.filter(user=user, isActive=True)

    def get_serializer_class(self):
        if getattr(self, 'swagger_fake_view', False):
            return ChatSerializer
            
        if self.action == "create":
            return ChatCreateSerializer
        if self.request.user.role == UserRole.ADMIN:
            return AdminChatSerializer
        return ChatSerializer

    def perform_create(self, serializer):
        chat = serializer.save()
        
        AuditLog.objects.create(
            user=chat.user,
            action="chat_created",
            model_name="Chat",
            object_id=str(chat.id),
            details={"title": chat.title, "flow_step": chat.flow_step}
        )

    def perform_destroy(self, instance):
        instance.isActive = False
        instance.save(update_fields=["isActive", "updatedAt"])
        
        AuditLog.objects.create(
            user=instance.user,
            action="chat_deleted",
            model_name="Chat",
            object_id=str(instance.id),
            details={"title": instance.title}
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        chat = serializer.save()
        
        sys_msg = chat.messages.filter(messageType=MessageType.SYSTEM).order_by("createdAt").first()
        data = ChatSerializer(chat, context={"request": request}).data
        
        if sys_msg:
            data["initial_system_message"] = MessageSerializer(sys_msg).data
            
        return Response({
            "status": "success", 
            "message": "Чат создан", 
            "data": data
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def empty(self, request):
        """Проверка наличия пустых чатов"""
      
        chat = get_empty_chat(request.user)
        
        if chat:
            serializer = self.get_serializer(chat)
            return Response({
                "status": "success",
                "message": "Найден чат без пользовательских сообщений",
                "data": serializer.data
            })
        else:
            return Response({
                "status": "success",
                "message": "Нет чатов без пользовательских сообщений",
                "data": None
            })

    @action(detail=True, methods=["get"])
    def messages(self, request, pk=None):
        chat = self.get_object()
        qs = chat.messages.order_by("createdAt")
        page = self.paginate_queryset(qs)
        ser = MessageSerializer(page, many=True) if page is not None else MessageSerializer(qs, many=True)
        return self.get_paginated_response(ser.data) if page is not None else Response({
            "status": "success", 
            "data": ser.data
        })
    
    @action(detail=True, methods=['get'])
    def generation_status(self, request, pk=None):
        """Проверка статуса генерации для чата"""
        chat = self.get_object()
        
        # Ищем последнюю задачу генерации для этого чата
        task = MediaGenerationTask.objects.filter(chat=chat).order_by('-createdAt').first()
        
        if not task:
            return Response({
                "status": "success",
                "data": {
                    "generation_status": "no_task",
                    "message": "Задача генерации не найдена"
                }
            })
        
        return Response({
            "status": "success",
            "data": {
                "generation_status": task.status,
                "task_id": str(task.id),
                "has_image": bool(task.result_image_base64),
                "last_error": task.last_error,
                "created_at": task.createdAt,
                "updated_at": task.updatedAt
            }
        })
    
    @action(detail=True, methods=['get'])
    def generated_images(self, request, pk=None):
        """Получение всех сгенерированных изображений для чата"""
        chat = self.get_object()
        
        tasks = MediaGenerationTask.objects.filter(
            chat=chat, 
            status=MediaGenerationTask.Status.SUCCESS
        ).order_by('-createdAt')
        
        images_data = []
        for task in tasks:
            if task.result_image_base64:
                images_data.append({
                    "task_id": str(task.id),
                    "prompt": task.prompt_text,
                    "created_at": task.createdAt,
                    "image_url": f"/api/generation-tasks/{task.id}/image/",
                    "download_url": f"/api/generation-tasks/{task.id}/image/?format=file"
                })
        
        return Response({
            "status": "success",
            "data": {
                "chat_id": str(chat.id),
                "images_count": len(images_data),
                "images": images_data
            }
        })

class MessageViewSet(viewsets.ModelViewSet):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter, SearchFilter]
    filterset_fields = ["messageType", "createdAt", "chat"]
    ordering_fields = ["createdAt"]
    search_fields = ["content", "chat__title"]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Message.objects.none()
            
        user = self.request.user
        qs = Message.objects.select_related("chat", "chat__user").all()
        if user.role == UserRole.ADMIN:
            return qs
        return qs.filter(chat__user=user, chat__isActive=True)

    def perform_create(self, serializer):
        message = serializer.save()
        
        AuditLog.objects.create(
            user=message.chat.user,
            action="message_sent",
            model_name="Message",
            object_id=str(message.id),
            details={"chat": str(message.chat.id), "type": message.messageType}
        )

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        data["messageType"] = data.get("messageType", MessageType.USER)
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        msg = serializer.save()

        if msg.messageType == MessageType.USER:
            chat = msg.chat
            result = handle_user_message_and_advance(chat, msg)
            
            if result["type"] == "question":
                sys_msg = result["message"]
                return Response({
                    "status": "success", 
                    "message": "Ответ принят, задан следующий вопрос", 
                    "data": {
                        "user_message": MessageSerializer(msg).data, 
                        "system_message": MessageSerializer(sys_msg).data
                    }
                }, status=status.HTTP_201_CREATED)
            
            elif result["type"] == "completed":
                pp = result.get("prompt_parameters")
                ph = result.get("prompt_history")
                
                # ✅ ИСПРАВЛЕНО: Добавляем информацию о задаче генерации
                task = MediaGenerationTask.objects.filter(
                    prompt_history=ph, 
                    chat=msg.chat
                ).order_by('-createdAt').first()
                
                response_data = {
                    "prompt_parameters_id": pp.id, 
                    "prompt_history_id": ph.id,
                    "assembled_prompt": ph.assembled_prompt,
                    # ✅ ДОБАВЛЯЕМ ИНФОРМАЦИЮ ДЛЯ ПОЛУЧЕНИЯ ИЗОБРАЖЕНИЯ
                    "generation_task_id": task.id if task else None,
                    "image_url": f"/api/generation-tasks/{task.id}/image/" if task else None,
                    "message": "Генерация запущена. Изображение будет доступно через несколько секунд."
                }
                
                return Response({
                    "status": "success", 
                    "message": "Flow завершён, запущена генерация изображения", 
                    "data": response_data
                }, status=status.HTTP_201_CREATED)

        return Response({
            "status": "success", 
            "message": "Сообщение отправлено", 
            "data": MessageSerializer(msg).data
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def recent(self, request):
        qs = self.get_queryset().order_by("-createdAt")[:50]
        ser = MessageSerializer(qs, many=True)
        return Response({"status": "success", "data": ser.data})

class PromptTemplateViewSet(viewsets.ModelViewSet):
    queryset = PromptTemplate.objects.all()
    serializer_class = PromptTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [permissions.IsAuthenticated(), permissions.IsAdminUser()]
        return [permissions.IsAuthenticated()]

class PromptParametersViewSet(viewsets.ModelViewSet):
    queryset = PromptParameters.objects.all()
    serializer_class = PromptParametersSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return PromptParameters.objects.none()
            
        user = self.request.user
        if user.role == UserRole.ADMIN:
            return PromptParameters.objects.all()
        return PromptParameters.objects.filter(user=user)

    def perform_create(self, serializer):
        obj = serializer.save(user=self.request.user)
        obj.semantic_vector = simple_semantic_vector_from_params(obj.data)
        obj.save(update_fields=["semantic_vector"])

class PromptActionsViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=["post"])
    def assemble(self, request):
        ser = PromptAssembleSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        template = None
        if data.get("template_id"):
            template = get_object_or_404(PromptTemplate, id=data["template_id"])
        else:
            template = get_default_prompt_template()
            if template is None:
                return Response({
                    "status": "error", 
                    "message": "Нет активного шаблона промпта"
                }, status=status.HTTP_400_BAD_REQUEST)

        if data.get("prompt_parameters_id"):
            params = get_object_or_404(PromptParameters, id=data["prompt_parameters_id"])
            parameters = params.data
        else:
            parameters = data.get("parameters", {})

        enrich_keys = ["idea", "visual_associations"]
        for k in enrich_keys:
            if k in parameters and isinstance(parameters[k], str) and 0 < len(parameters[k]) < 80:
                parameters[k] = enrich_prompt_with_gigachat(parameters[k])

        assembled = assemble_prompt_from_template(template.template, parameters)

        ph = PromptHistory.objects.create(
            user=request.user,
            prompt_template=template,
            parameters=params if data.get("prompt_parameters_id") else None,
            assembled_prompt=assembled
        )

        return Response({
            "status": "success", 
            "message": "Промпт собран", 
            "data": {
                "assembled_prompt": assembled, 
                "history_id": ph.id
            }
        })

    @action(detail=False, methods=["post"])
    def generate(self, request):
        payload = request.data
        template = None
        
        if payload.get("template_id"):
            template = get_object_or_404(PromptTemplate, id=payload["template_id"])
        else:
            template = get_default_prompt_template()
            if template is None:
                return Response({
                    "status": "error", 
                    "message": "Нет активного шаблона промпта"
                }, status=status.HTTP_400_BAD_REQUEST)

        parameters = {}
        params_obj = None
        
        if payload.get("prompt_parameters_id"):
            params_obj = get_object_or_404(PromptParameters, id=payload["prompt_parameters_id"])
            parameters = params_obj.data
        elif payload.get("parameters"):
            parameters = payload.get("parameters")

        if isinstance(parameters, dict):
            for k in ["idea", "visual_associations"]:
                if k in parameters and isinstance(parameters[k], str) and 0 < len(parameters[k]) < 80:
                    parameters[k] = enrich_prompt_with_gigachat(parameters[k])

        assembled = assemble_prompt_from_template(template.template, parameters)
        ph = PromptHistory.objects.create(
            user=request.user, 
            prompt_template=template, 
            parameters=params_obj, 
            assembled_prompt=assembled
        )

        task = MediaGenerationTask.objects.create(
            user=request.user, 
            chat=None, 
            prompt_history=ph, 
            prompt_text=assembled, 
            status="PENDING"
        )
        
        AuditLog.objects.create(
            user=request.user, 
            action="create_generation_task", 
            model_name="MediaGenerationTask", 
            object_id=str(task.id), 
            details={"prompt_len": len(assembled)}
        )

        max_attempts = int(payload.get("max_attempts", 3))
        attempt = 0
        
        while attempt < max_attempts:
            attempt += 1
            task.status = "RUNNING"
            task.attempts = attempt
            task.save(update_fields=["status", "attempts", "updatedAt"])

            generated_meta = {"ok": attempt >= 2, "prompt_len": len(assembled)}
            generated_result = {"result_url": f"/media/generated/{task.id}.jpg"}

            ok = quality_check_generated(generated_meta)
            if ok:
                task.status = "SUCCESS"
                task.result_url = generated_result["result_url"]
                task.save(update_fields=["status", "result_url", "updatedAt"])
                
                AuditLog.objects.create(
                    user=request.user, 
                    action="generation_success", 
                    model_name="MediaGenerationTask", 
                    object_id=str(task.id), 
                    details={"attempt": attempt}
                )
                
                return Response({
                    "status": "success", 
                    "message": "Генерация успешно завершена", 
                    "data": {
                        "task_id": task.id, 
                        "result_url": task.result_url
                    }
                })
            else:
                assembled = paraphrase_prompt(assembled)
                ph = PromptHistory.objects.create(
                    user=request.user, 
                    prompt_template=template, 
                    parameters=params_obj, 
                    assembled_prompt=assembled
                )
                task.prompt_history = ph
                task.prompt_text = assembled
                task.save(update_fields=["prompt_history", "prompt_text", "updatedAt"])
                
                AuditLog.objects.create(
                    user=request.user, 
                    action="generation_retry", 
                    model_name="MediaGenerationTask", 
                    object_id=str(task.id), 
                    details={"attempt": attempt}
                )

        task.status = "FAILED"
        task.last_error = f"Quality check failed after {attempt} attempts"
        task.save(update_fields=["status", "last_error", "updatedAt"])
        
        AuditLog.objects.create(
            user=request.user, 
            action="generation_failed", 
            model_name="MediaGenerationTask", 
            object_id=str(task.id), 
            details={"attempts": attempt}
        )
        
        return Response({
            "status": "error", 
            "message": "Не удалось сгенерировать подходящий результат", 
            "data": {"task_id": task.id}
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


from django.http import HttpResponse
import base64
import re

class MediaGenerationTaskViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MediaGenerationTaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == UserRole.ADMIN:
            return MediaGenerationTask.objects.all()
        return MediaGenerationTask.objects.filter(user=user)

    @action(detail=True, methods=['get'])
    def image(self, request, pk=None):
        """Получение изображения в формате Base64 или как файл"""
        task = self.get_object()
        
        if not task.result_image_base64:
            return Response({
                "status": "error",
                "message": "Изображение еще не готово или произошла ошибка генерации"
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Определяем формат ответа
        response_format = request.query_params.get('format', 'json')
        
        if response_format == 'file':
            # ✅ ПЕРЕНАПРАВЛЯЕМ НА МЕТОД download_image
            return self.download_image(request, pk)
        else:
            # Возвращаем как JSON с Base64
            return Response({
                "status": "success",
                "data": {
                    "image_base64": task.result_image_base64,
                    "task_id": str(task.id),
                    "prompt": task.prompt_text,
                    "created_at": task.createdAt,
                    # ✅ ОБНОВЛЯЕМ URL ДЛЯ СКАЧИВАНИЯ
                    "download_url": f"http://{request.get_host()}/api/generation-tasks/{task.id}/download/"
                }
            })
    
    @action(detail=True, methods=['get'], url_path='download')
    def download_image(self, request, pk=None):
        """Скачивание изображения как файла"""
        task = self.get_object()
        
        if not task.result_image_base64:
            return Response({
                "status": "error",
                "message": "Изображение не найдено"
            }, status=status.HTTP_404_NOT_FOUND)
        
        try:
            # Убираем data:image/... префикс если есть
            image_data = task.result_image_base64
            if 'base64,' in image_data:
                image_data = image_data.split('base64,')[1]
            
            image_binary = base64.b64decode(image_data)
            response = HttpResponse(image_binary, content_type='image/png')
            response['Content-Disposition'] = f'attachment; filename="generated_image_{task.id}.png"'
            return response
        except Exception as e:
            return Response({
                "status": "error",
                "message": f"Ошибка декодирования изображения: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)