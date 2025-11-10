# utils.py
import json
from datetime import datetime, timedelta
from django.core.serializers.json import DjangoJSONEncoder
from .models import Message, Chat, PromptParameters, PromptHistory, MessageType
from string import Formatter
import re

# Flow вопросов согласно документу "Параметры + промпт.docx"
QUESTIONS_FLOW = [
    ("content_type", "Что нужно создать — фото или видео? (content_type)", False),
    ("idea", "Кратко опишите идею или цель контента (idea)", False),
    ("emotion", "Какой эмоциональный тон нужен? (energy/nostalgic/романтичный/и т.д.)", False),
    ("relation_to_event", "Нужно ли привязать к событию? (прямая / тематическая / без привязки)", True),
    ("event_name", "Если да — укажите название события (event_name). Оставьте пустым, если нет.", True),
    ("event_genre", "Жанр события (event_genre).", True),
    ("event_description", "Краткое описание события (event_description).", True),
    ("visual_style", "Художественный стиль (visual_style).", False),
    ("composition_focus", "На что сделать акцент композиции (composition_focus).", False),
    ("color_palette", "Преобладающая палитра (color_palette).", True),
    ("visual_associations", "Слова-ассоциации (visual_associations). Несколько слов через запятую.", True),
    ("platform", "Платформа для публикации (platform).", True),
    ("aspect_ratio", "Формат кадра (aspect_ratio). Например 9:16, 1:1, 16:9.", True),
    ("duration", "Длительность в секундах (duration) — для видео.", True),
    ("slogan", "Текст/слоган, если нужен (slogan).", True),
    ("text_style", "Стиль текста (text_style).", True),
    ("variation_count", "Сколько вариантов нужно (variation_count).", True),
]

FLOW_KEYS = [k for k, _, _ in QUESTIONS_FLOW]

class CustomJSONEncoder(DjangoJSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def validate_email_domain(email):
    """Валидация домена email"""
    allowed_domains = ['gmail.com', 'yandex.ru', 'mail.ru', 'sberbank.ru']
    domain = email.split('@')[-1]
    return domain in allowed_domains

def assemble_prompt_from_template(template_text: str, parameters: dict) -> str:
    class SafeDict(dict):
        def __missing__(self, key):
            return ""

    params = {k: (v if v is not None else "") for k, v in parameters.items()}
    safe = SafeDict(params)
    
    try:
        return template_text.format_map(safe)
    except Exception:
        result = template_text
        for k, v in params.items():
            result = result.replace("{" + k + "}", str(v))
        for literal_text, field_name, format_spec, conversion in Formatter().parse(result):
            if field_name and "{" + field_name + "}" in result:
                result = result.replace("{" + field_name + "}", "")
        return result

def enrich_prompt_with_gigachat(short_text):
    """
    Заглушка для интеграции с GigaChat
    В реальной реализации здесь будет вызов API GigaChat
    """
    # Временная реализация - просто возвращаем обогащенный текст
    enrichment_map = {
        "театр": "великолепный театральный мир с богатой историей и культурой",
        "концерт": "захватывающее музыкальное представление с живым звуком",
        "выставка": "уникальная художественная экспозиция с современным искусством",
        "спектакль": "театральное представление с профессиональной актерской игрой",
    }
    
    for key, value in enrichment_map.items():
        if key in short_text.lower():
            return value
    
    return short_text + " - созданное с вниманием к деталям и художественному вкусу"

def simple_semantic_vector_from_params(parameters: dict) -> dict:
    """Создание простого семантического вектора из параметров"""
    vec = {}
    for k, v in parameters.items():
        try:
            vec[k] = len(str(v))
        except Exception:
            vec[k] = 0
    return vec

def quality_check_generated(result_meta: dict) -> bool:
    """Проверка качества сгенерированного контента"""
    if result_meta.get("ok") is True:
        return True
    prompt_len = result_meta.get("prompt_len", 0)
    return prompt_len >= 30

def next_question_for_chat(chat: Chat):
    """
    Возвращает (key, question_text, optional) для следующего шага или (None, None, None) если flow завершён.
    """
    step = chat.flow_step or 0
    if step < len(QUESTIONS_FLOW):
        key, text, optional = QUESTIONS_FLOW[step]
        return key, text, optional
    return None, None, None

def build_parameters_from_chat_messages(chat: Chat) -> dict:
    """
    Собирает параметры из сообщений чата
    """
    user_msgs = list(chat.messages.filter(messageType=MessageType.USER).order_by("createdAt"))
    params = {}
    
    for idx, (key, _, optional) in enumerate(QUESTIONS_FLOW):
        if idx < len(user_msgs):
            content = user_msgs[idx].content.strip()
            if content:  # Не сохраняем пустые ответы для опциональных полей
                params[key] = content
        elif not optional:
            # Для обязательных полей без ответа ставим пустую строку
            params[key] = ""
    
    return params

def handle_user_message_and_advance(chat: Chat, message: Message):
    """
    Обработчик пользовательского сообщения:
    - обновляет flow_step,
    - создаёт следующий системный вопрос,
    - если flow завершён — собирает PromptParameters и PromptHistory
    """
    from django.utils import timezone
    
    # Увеличиваем шаг
    chat.flow_step = (chat.flow_step or 0) + 1
    chat.updatedAt = timezone.now()
    
    chat.save(update_fields=["flow_step", "updatedAt"])

    # Проверяем, есть ли следующий вопрос
    next_key, next_text, optional = next_question_for_chat(chat)
    if next_text:
        # Создаем системное сообщение со следующим вопросом
        sys_msg = Message.objects.create(
            chat=chat, 
            content=next_text, 
            messageType=MessageType.SYSTEM
        )
        return {"type": "question", "message": sys_msg}

    # Flow завершён — собираем параметры
    params = build_parameters_from_chat_messages(chat)
    
    # Обогащаем короткие параметры через GigaChat
    enrich_keys = ["idea", "visual_associations"]
    for key in enrich_keys:
        if key in params and isinstance(params[key], str) and 0 < len(params[key]) < 80:
            params[key] = enrich_prompt_with_gigachat(params[key])
    
    # Сохраняем параметры
    pp = PromptParameters.objects.create(
        user=chat.user, 
        data=params, 
        semantic_vector=simple_semantic_vector_from_params(params)
    )
    
    # Создаем запись в истории промптов
    template = get_default_prompt_template()
    assembled_prompt = assemble_prompt_from_template(template.template, params) if template else ""
    
    ph = PromptHistory.objects.create(
        user=chat.user, 
        prompt_template=template,
        parameters=pp, 
        assembled_prompt=assembled_prompt
    )
    
    return {"type": "completed", "prompt_parameters": pp, "prompt_history": ph}

def get_default_prompt_template():
    """Получение активного шаблона промпта с созданием дефолтного если нет активных"""
    from .models import PromptTemplate
    
    template = PromptTemplate.objects.filter(is_active=True).first()
    
    if not template:
        # Создаем базовый шаблон если нет активных
        template = PromptTemplate.objects.create(
            name="Автоматически созданный шаблон",
            template="Создай {content_type} для {platform}. Идея: {idea}. Эмоция: {emotion}.",
            is_active=True
        )
    
    return template

def get_user_chats_summary(user):
    """Сводка по чатам пользователя"""
    chats = Chat.objects.filter(user=user, isActive=True)
    total_chats = chats.count()
    completed_chats = chats.filter(flow_step__gte=len(QUESTIONS_FLOW)).count()
    active_chats = total_chats - completed_chats
    
    return {
        "total_chats": total_chats,
        "completed_chats": completed_chats,
        "active_chats": active_chats,
        "total_messages": Message.objects.filter(chat__user=user).count()
    }

def has_unfinished_chat(user):
    """
    Проверяет, есть ли у пользователя незавершенный чат
    """
    return Chat.objects.filter(
        user=user, 
        isActive=True,
        flow_step__lt=len(QUESTIONS_FLOW)  # Чат не завершен
    ).exists()

def get_unfinished_chat(user):
    """
    Возвращает незавершенный чат пользователя, если есть
    """
    return Chat.objects.filter(
        user=user, 
        isActive=True,
        flow_step__lt=len(QUESTIONS_FLOW)
    ).first()

def cleanup_expired_temporary_chats(minutes=10):
    """
    Удаляет временные чаты, созданные больше minutes назад и у которых нет пользовательских ответов.
    """
    from django.utils import timezone
    cutoff = timezone.now() - timedelta(minutes=minutes)
    
    expired_chats = Chat.objects.filter(
        is_temporary=True, 
        temp_created_at__lt=cutoff
    )
    
    # Логируем удаление
    count = expired_chats.count()
    for chat in expired_chats:
        # Создаем запись в логах аудита
        from .models import AuditLog
        AuditLog.objects.create(
            user=chat.user,
            action="cleanup_expired_chat",
            model_name="Chat",
            object_id=str(chat.id),
            details={"title": chat.title, "created_at": chat.createdAt.isoformat()}
        )
    
    expired_chats.delete()
    return count

def paraphrase_prompt(prompt_text):
    """
    Перефразирование промпта для улучшения качества генерации
    """
    paraphrases = [
        "\n\nСделай формулировку более конкретной и насыщенной деталями.",
        "\n\nДобавь больше художественных деталей и эмоциональной насыщенности.",
        "\n\nСфокусируйся на композиции и визуальной гармонии.",
        "\n\nУсиль эмоциональное воздействие через цвет и свет.",
    ]
    
    # Простая эвристика - выбираем парафраз на основе длины промпта
    index = min(len(prompt_text) // 50, len(paraphrases) - 1)
    return prompt_text + paraphrases[index]