# serializers.py
import json
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import User, Chat, Message, MessageType, PromptParameters, PromptTemplate, PromptHistory, MediaGenerationTask, UserRole
from .utils import validate_email_domain, next_question_for_chat, QUESTIONS_FLOW, has_empty_chat

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "fullName", "role", "dateJoined", "isActive"]
        read_only_fields = ["id", "role", "dateJoined", "isActive"]

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    passwordConfirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "fullName", "password", "passwordConfirm"]
        read_only_fields = ["id"]

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Пользователь с таким email уже существует")
        if not validate_email_domain(value):
            raise serializers.ValidationError("Домен email не поддерживается")
        return value.lower()

    def validate(self, attrs):
        if attrs.get("password") != attrs.pop("passwordConfirm", None):
            raise serializers.ValidationError({"passwordConfirm": "Пароли не совпадают"})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        return user

class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "fullName", "role", "isActive"]
        read_only_fields = ["id", "email"]

    def validate_role(self, value):
        if self.instance and self.instance.role == UserRole.ADMIN and value != UserRole.ADMIN:
            # Не позволяем снимать права администратора у самого себя
            if self.instance == self.context['request'].user:
                raise serializers.ValidationError("Нельзя снять права администратора у себя")
        return value

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        token["role"] = user.role
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = {"id": self.user.id, "email": self.user.email, "fullName": self.user.fullName, "role": self.user.role}
        return data

class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ["id", "chat", "content", "messageType", "createdAt"]
        read_only_fields = ["id", "createdAt"]

    def to_representation(self, instance):
        """Преобразуем сохраненный JSON в читаемый формат"""
        data = super().to_representation(instance)
        
        # Всегда пытаемся парсить JSON
        try:
            import json
            content_data = json.loads(data['content'])
            
            # Если парсинг успешен, используем результат
            if isinstance(content_data, dict):
                data['content'] = content_data
            elif isinstance(content_data, str):
                # Если это строка, оборачиваем в структуру
                data['content'] = {
                    "type": "text",
                    "info": content_data
                }
        except (json.JSONDecodeError, TypeError):
            # Если не JSON, оборачиваем строку в структуру
            data['content'] = {
                "type": "text",
                "info": data['content']
            }
        
        return data

    def to_internal_value(self, data):
        """Сохраняем данные в правильном формате"""
        # Делаем копию данных
        data_copy = data.copy()
        
        # Обрабатываем content отдельно
        content = data_copy.get('content', '')
        
        if isinstance(content, dict):
            # Если пришел dict, сериализуем в JSON
            import json
            data_copy['content'] = json.dumps(content, ensure_ascii=False)
        elif isinstance(content, str):
            # Если пришла строка, создаем структуру
            import json
            data_copy['content'] = json.dumps({
                "type": "text",
                "info": content
            }, ensure_ascii=False)
        elif content is None:
            data_copy['content'] = ''
        
        # Теперь вызываем родительский метод с преобразованными данными
        return super().to_internal_value(data_copy)
    
    def validate_content(self, value):
        """Валидация контента"""
        # Здесь value уже будет строкой после to_internal_value
        # Но нужно убедиться, что это не пустая строка
        if not value or not value.strip():
            raise serializers.ValidationError("Content не может быть пустым")
        
        # Проверяем, что это валидный JSON (если мы его создали)
        try:
            import json
            json.loads(value)
        except (json.JSONDecodeError, TypeError):
            # Если не JSON, это нормально - это может быть просто строка
            pass
            
        return value
    
    
class ChatSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)
    messageCount = serializers.SerializerMethodField()
    lastMessage = serializers.SerializerMethodField()

    class Meta:
        model = Chat
        fields = ["id", "user", "title", "createdAt", "updatedAt", "isActive", "is_temporary", "flow_step", "messages", "messageCount", "lastMessage"]
        read_only_fields = ["id", "user", "createdAt", "updatedAt", "messages", "messageCount", "lastMessage", "flow_step", "is_temporary"]

    def get_messageCount(self, obj):
        return obj.messages.count()

    def get_lastMessage(self, obj):
        last = obj.messages.order_by("-createdAt").first()
        if not last:
            return None
        return MessageSerializer(last).data

class ChatCreateSerializer(serializers.ModelSerializer):
    initialMessage = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Chat
        fields = ["id", "title", "initialMessage"]

    def validate_title(self, value):
        if value is None or not str(value).strip():
            user = self.context["request"].user
            chat_count = Chat.objects.filter(user=user).count() + 1
            return f"Чат №{chat_count}"
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user
        
        # проверяем наличие чата без пользовательских сообщений
        
        if has_empty_chat(user):
            raise ValidationError("У вас есть чат без сообщений. Напишите хотя бы одно сообщение в существующем чате перед созданием нового.")
        
        return attrs

    def create(self, validated_data):
        initial_message = validated_data.pop("initialMessage", None)
        request = self.context.get("request")
        user = request.user
        
        # Создаем чат
        chat = Chat.objects.create(
            user=user, 
            is_temporary=False,
            **validated_data
        )
        
        # Создаем первый системный вопрос
        key, question_text, optional = next_question_for_chat(chat)
        if question_text:
            Message.objects.create(
                chat=chat, 
                content=question_text, 
                messageType=MessageType.SYSTEM
            )
        
        # Если есть начальное сообщение от пользователя, создаем его
        if initial_message:
            Message.objects.create(
                chat=chat,
                content=initial_message,
                messageType=MessageType.USER
            )
            
        return chat

class AdminChatSerializer(ChatSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_fullName = serializers.CharField(source='user.fullName', read_only=True)

    class Meta(ChatSerializer.Meta):
        fields = ChatSerializer.Meta.fields + ['user_email', 'user_fullName']

class PromptTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromptTemplate
        fields = ["id", "name", "template", "is_active", "createdAt", "updatedAt"]
        read_only_fields = ["id", "createdAt", "updatedAt"]

class PromptParametersSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromptParameters
        fields = ["id", "user", "data", "semantic_vector", "createdAt"]
        read_only_fields = ["id", "user", "semantic_vector", "createdAt"]

class PromptAssembleSerializer(serializers.Serializer):
    prompt_parameters_id = serializers.UUIDField(required=False)
    parameters = serializers.JSONField(required=False)
    template_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        if not attrs.get('prompt_parameters_id') and not attrs.get('parameters'):
            raise serializers.ValidationError("Необходимо указать либо prompt_parameters_id, либо parameters")
        return attrs

class PromptHistorySerializer(serializers.ModelSerializer):
    prompt_template_name = serializers.CharField(source='prompt_template.name', read_only=True)

    class Meta:
        model = PromptHistory
        fields = ["id", "user", "prompt_template", "prompt_template_name", "parameters", "assembled_prompt", "createdAt"]
        read_only_fields = ["id", "user", "createdAt"]

class MediaGenerationTaskSerializer(serializers.ModelSerializer):
    result_image_base64 = serializers.CharField(read_only=True, allow_null=True)
    
    class Meta:
        model = MediaGenerationTask
        fields = [
            "id", "user", "chat", "prompt_history", "prompt_text", 
            "status", "result_url", "result_image_base64",
            "attempts", "last_error", "createdAt", "updatedAt"
        ]
        read_only_fields = ["id", "user", "createdAt", "updatedAt"]

class FormGenerationSerializer(serializers.Serializer):
    """Сериализатор для формы с полным набором параметров"""
    
    # Основные параметры (из flow - 9 вопросов)
    idea = serializers.CharField(required=True, max_length=500)
    event_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=200)
    event_genre = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=100)
    visual_style = serializers.CharField(required=True, max_length=100)
    composition_focus = serializers.CharField(required=True, max_length=100)
    color_palette = serializers.CharField(required=True, max_length=100)
    visual_associations = serializers.CharField(required=True, max_length=500)
    platform = serializers.CharField(required=True, max_length=50)
    aspect_ratio = serializers.CharField(required=False, max_length=10)
    
    # Настройки генерации
    enable_photo_check = serializers.BooleanField(default=True)
    max_regeneration_attempts = serializers.IntegerField(default=3, min_value=1, max_value=10)
    
    def validate_aspect_ratio(self, value):
        if value is None:
            return "1:1"
        
        valid_ratios = ["9:16", "16:9", "1:1", "4:5", "2:3"]
        if value not in valid_ratios:
            raise serializers.ValidationError(f"Допустимые форматы: {', '.join(valid_ratios)}")
        return value
    
    def validate(self, attrs):
        # Устанавливаем aspect_ratio по умолчанию если не указан
        if 'aspect_ratio' not in attrs or attrs['aspect_ratio'] is None:
            attrs['aspect_ratio'] = "1:1"
        return attrs

class FormGenerationResponseSerializer(serializers.Serializer):
    """Сериализатор ответа для формы генерации"""
    task_id = serializers.UUIDField()
    status = serializers.CharField()
    assembled_prompt = serializers.CharField()
    image_url = serializers.CharField(required=False)
    download_url = serializers.CharField(required=False)
    generation_attempts = serializers.IntegerField()
    regeneration_attempts = serializers.IntegerField()
    problems_fixed = serializers.ListField(child=serializers.CharField(), required=False)
    estimated_time_seconds = serializers.IntegerField()