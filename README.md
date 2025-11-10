# Contentum Django Backend

## Описание

Contentum — backend для генерации медиа-контента через чат-интерфейс.  
Пользователь (сотрудник) ведёт диалог с системой, отвечает на вопросы, система собирает параметры, формирует промпт и запускает генерацию (MVP — симуляция, далее интеграция с Kandinsky).

### Основные возможности

- JWT регистрация и авторизация (сотрудник/администратор)
- Чаты с системой: пошаговый сбор параметров
- Ограничение: только один незавершённый чат у пользователя
- Временные чаты удаляются через 10 минут, если нет ответа (пока нет этого)
- Автоматическое обогащение коротких параметров через Gigachat (заглушка)
- Генерация промпта и запуск задачи генерации (MVP — симуляция)
- Автоматическая проверка качества и перегенерация с перефразированием
- Админ: управление пользователями, просмотр логов и чатов

## Быстрый старт

### 1. Клонирование и установка

```bash 
git clone https://github.com/IvKhrom/contentumDjangoBackend.git
cd contentumDjangoBackend
python -m venv venv
venv\Scripts\activate   # Windows
# или
source venv/bin/activate # Linux/Mac

pip install -r requirements.txt
```

### 2. Настройка .env

Создайте файл `.env` (пример уже есть):

```
SECRET_KEY='your-secret-key'
DEBUG=True
DB_NAME='contentum_db'
DB_USER='postgres'
DB_PASSWORD='yourpassword'
DB_HOST='localhost'
DB_PORT='5432'
```

### 3. Миграции и запуск

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py runserver
```

### 4. Swagger/OpenAPI

Документация доступна по адресу:  
[http://localhost:8000/swagger/](http://localhost:8000/swagger/)

---

## Основные эндпоинты

- `/api/users/` — регистрация
- `/api/auth/login/` — JWT авторизация
- `/api/chats/` — список/создание чатов
- `/api/messages/` — отправка сообщений
- `/api/promptparameters/` — параметры промпта
- `/api/prompttemplates/` — шаблоны промпта
- `/api/promptactions/assemble/` — сборка промпта
- `/api/promptactions/generate/` — генерация медиа

---

## Роли

- **Сотрудник** — регистрируется самостоятельно, ведёт чаты, запускает генерацию
- **Администратор** — назначается вручную, управляет пользователями, шаблонами, логами

---

## Валидации, фильтры, сортировки

- Валидация email, пароля, уникальность, ограничения по незавершённым чатам
- Фильтры, поиск и сортировка доступны для всех основных моделей (через query-параметры)

---

## Тесты

Тесты находятся в `core/tests.py`.  
Запуск:  
```bash
python manage.py test
```

---