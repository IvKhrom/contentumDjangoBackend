# models.py
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
import uuid
import json

class UserRole(models.TextChoices):
    ADMIN = "ADMIN", "Администратор"
    EMPLOYEE = "EMPLOYEE", "Сотрудник"

class MessageType(models.TextChoices):
    SYSTEM = "SYSTEM", "Системное"
    USER = "USER", "Пользовательское"

class UserManager(BaseUserManager):
    def create_user(self, email, fullName, password=None, **extra_fields):
        if not email:
            raise ValueError('Email обязателен')
        if not fullName:
            raise ValueError('Полное имя обязательно')
        
        email = self.normalize_email(email)
        user = self.model(email=email, fullName=fullName, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, fullName, password=None, **extra_fields):
        extra_fields.setdefault('role', UserRole.ADMIN)
        extra_fields.setdefault('isActive', True)
        return self.create_user(email, fullName, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, verbose_name="Email")
    fullName = models.CharField(max_length=255, verbose_name="Полное имя")
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.EMPLOYEE, verbose_name="Роль")
    dateJoined = models.DateTimeField(default=timezone.now, verbose_name="Дата регистрации")
    isActive = models.BooleanField(default=True, verbose_name="Активен")
    
    objects = UserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['fullName']
    
    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
    
    def __str__(self):
        return f"{self.fullName} ({self.email})"
    
    @property
    def is_staff(self):
        return self.role == UserRole.ADMIN
    
    @property
    def is_admin(self):
        return self.role == UserRole.ADMIN

class Chat(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chats", verbose_name="Пользователь")
    title = models.CharField(max_length=255, verbose_name="Название чата")
    createdAt = models.DateTimeField(default=timezone.now, verbose_name="Дата создания")
    updatedAt = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    isActive = models.BooleanField(default=True, verbose_name="Активен")
    is_temporary = models.BooleanField(default=False, verbose_name="Временный")
    temp_created_at = models.DateTimeField(null=True, blank=True, verbose_name="Время создания временного чата")
    flow_step = models.IntegerField(default=0, verbose_name="Текущий шаг flow")
    
    class Meta:
        verbose_name = "Чат"
        verbose_name_plural = "Чаты"
        ordering = ["-createdAt"]
    
    def __str__(self):
        return f"{self.title} ({self.user.email})"

class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="messages", verbose_name="Чат")
    content = models.TextField(verbose_name="Содержание")
    messageType = models.CharField(max_length=20, choices=MessageType.choices, default=MessageType.USER, verbose_name="Тип сообщения")
    createdAt = models.DateTimeField(default=timezone.now, verbose_name="Дата создания")
    
    class Meta:
        verbose_name = "Сообщение"
        verbose_name_plural = "Сообщения"
        ordering = ["createdAt"]
    
    def __str__(self):
        return f"{self.messageType}: {self.content[:50]}..."

class PromptTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, verbose_name="Название шаблона")
    template = models.TextField(verbose_name="Шаблон промпта")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    createdAt = models.DateTimeField(default=timezone.now, verbose_name="Дата создания")
    updatedAt = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    class Meta:
        verbose_name = "Шаблон промпта"
        verbose_name_plural = "Шаблоны промптов"
    
    def __str__(self):
        return self.name

class PromptParameters(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="prompt_parameters", verbose_name="Пользователь")
    data = models.JSONField(default=dict, verbose_name="Параметры")
    semantic_vector = models.JSONField(default=dict, verbose_name="Семантический вектор")
    createdAt = models.DateTimeField(default=timezone.now, verbose_name="Дата создания")
    
    class Meta:
        verbose_name = "Параметры промпта"
        verbose_name_plural = "Параметры промптов"
    
    def __str__(self):
        return f"Параметры {self.user.email}"

class PromptHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="prompt_history", verbose_name="Пользователь")
    prompt_template = models.ForeignKey(PromptTemplate, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Шаблон промпта")
    parameters = models.ForeignKey(PromptParameters, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Параметры")
    assembled_prompt = models.TextField(verbose_name="Собранный промпт")
    createdAt = models.DateTimeField(default=timezone.now, verbose_name="Дата создания")
    
    class Meta:
        verbose_name = "История промптов"
        verbose_name_plural = "История промптов"
    
    def __str__(self):
        return f"Промпт {self.user.email}"

class MediaGenerationTask(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "В ожидании"
        RUNNING = "RUNNING", "Выполняется" 
        SUCCESS = "SUCCESS", "Успешно"
        FAILED = "FAILED", "Ошибка"
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="generation_tasks", verbose_name="Пользователь")
    chat = models.ForeignKey(Chat, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Чат")
    prompt_history = models.ForeignKey(PromptHistory, on_delete=models.CASCADE, verbose_name="История промпта")
    prompt_text = models.TextField(verbose_name="Текст промпта")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name="Статус")
    result_url = models.URLField(blank=True, null=True, verbose_name="URL результата")
    result_image_base64 = models.TextField(blank=True, null=True, verbose_name="Изображение (Base64)")  # НОВОЕ ПОЛЕ
    attempts = models.IntegerField(default=0, verbose_name="Попытки")
    last_error = models.TextField(blank=True, null=True, verbose_name="Последняя ошибка")
    createdAt = models.DateTimeField(default=timezone.now, verbose_name="Дата создания")
    updatedAt = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    
    class Meta:
        verbose_name = "Задача генерации"
        verbose_name_plural = "Задачи генерации"
    
    def __str__(self):
        return f"Задача {self.user.email}"

class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Пользователь")
    action = models.CharField(max_length=255, verbose_name="Действие")
    model_name = models.CharField(max_length=255, verbose_name="Модель")
    object_id = models.CharField(max_length=255, verbose_name="ID объекта")
    details = models.JSONField(default=dict, verbose_name="Детали")
    createdAt = models.DateTimeField(default=timezone.now, verbose_name="Дата создания")
    
    class Meta:
        verbose_name = "Лог аудита"
        verbose_name_plural = "Логи аудита"
        ordering = ["-createdAt"]
    
    def __str__(self):
        return f"{self.user.email} - {self.action}"