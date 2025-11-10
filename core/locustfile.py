# locustfile.py
from locust import HttpUser, task, between
import random
import json
import logging

class ContentumUser(HttpUser):
    """
    Locust пользователь для нагрузочного тестирования Contentum API
    """
    wait_time = between(1, 3)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.token = None
        self.user_id = None
        self.chat_ids = []
        self.headers = {}
    
    def on_start(self):
        """Выполняется при запуске каждого виртуального пользователя"""
        self.user_id = f"loadtest{random.randint(10000, 99999)}@test.com"
        self.password = "LoadTestPass123"
        
        # Регистрация нового пользователя
        registration_data = {
            "email": self.user_id,
            "fullName": f"Load Test User {random.randint(1, 1000)}",
            "password": self.password,
            "passwordConfirm": self.password
        }
        
        with self.client.post("/api/users/", 
                            json=registration_data, 
                            catch_response=True,
                            name="User Registration") as response:
            
            if response.status_code == 201:
                # Успешная регистрация - логинимся
                self._login_user()
            elif response.status_code == 400:
                # Пользователь уже существует - пробуем войти
                logging.info(f"User {self.user_id} already exists, trying to login")
                self._login_user()
            else:
                response.failure(f"Registration failed: {response.status_code} - {response.text}")
    
    def _login_user(self):
        """Аутентификация пользователя"""
        login_data = {
            "email": self.user_id,
            "password": self.password
        }
        
        with self.client.post("/api/auth/login/", 
                            json=login_data, 
                            catch_response=True,
                            name="User Login") as response:
            
            if response.status_code == 200:
                self.token = response.json()['access']
                self.headers = {"Authorization": f"Bearer {self.token}"}
                logging.info(f"Successfully authenticated user: {self.user_id}")
                
                # Получаем существующие чаты пользователя
                self._get_user_chats()
            else:
                response.failure(f"Login failed: {response.status_code} - {response.text}")
    
    def _get_user_chats(self):
        """Получение списка чатов пользователя"""
        if not self.token:
            return
            
        with self.client.get("/api/chats/", 
                           headers=self.headers,
                           catch_response=True,
                           name="Get User Chats") as response:
            
            if response.status_code == 200:
                data = response.json()
                # Сохраняем ID существующих чатов для дальнейшего использования
                self.chat_ids = [chat['id'] for chat in data.get('results', [])]
                logging.info(f"Found {len(self.chat_ids)} existing chats")
            elif response.status_code != 200:
                response.failure(f"Failed to get chats: {response.status_code}")
    
    @task(4)
    def view_chats_list(self):
        """Просмотр списка чатов пользователя"""
        if not self.token:
            return
            
        with self.client.get("/api/chats/", 
                           headers=self.headers,
                           catch_response=True,
                           name="View Chats List") as response:
            
            if response.status_code == 200:
                data = response.json()
                # Обновляем список чатов
                self.chat_ids = [chat['id'] for chat in data.get('results', [])]
            elif response.status_code == 401:
                # Токен истек - пробуем перелогиниться
                self._login_user()
                response.failure("Token expired, re-login required")
            else:
                response.failure(f"Failed to get chats list: {response.status_code}")
    
    @task(2)
    def create_new_chat(self):
        """Создание нового чата с начальным сообщением"""
        if not self.token:
            return
            
        chat_data = {
            "title": f"Load Test Chat {random.randint(1000, 9999)}",
            "initialMessage": f"Тестовое сообщение для нагрузочного тестирования #{random.randint(1, 1000)}"
        }
        
        with self.client.post("/api/chats/", 
                            json=chat_data,
                            headers=self.headers,
                            catch_response=True,
                            name="Create New Chat") as response:
            
            if response.status_code == 201:
                # Добавляем ID нового чата в список
                chat_id = response.json()['data']['id']
                self.chat_ids.append(chat_id)
                logging.info(f"Successfully created chat: {chat_id}")
            elif response.status_code == 400:
                error_msg = response.json().get('message', 'Unknown error')
                response.failure(f"Chat creation validation error: {error_msg}")
            elif response.status_code == 401:
                self._login_user()
                response.failure("Token expired during chat creation")
            else:
                response.failure(f"Chat creation failed: {response.status_code}")
    
    @task(6)
    def send_message_to_chat(self):
        """Отправка сообщения в случайный чат пользователя"""
        if not self.token or not self.chat_ids:
            # Если нет чатов, создаем новый
            self.create_new_chat()
            return
        
        # Выбираем случайный чат из существующих
        chat_id = random.choice(self.chat_ids)
        
        message_content = self._generate_message_content()
        message_data = {
            "content": message_content
        }
        
        with self.client.post(f"/api/chats/{chat_id}/send_message/", 
                            json=message_data,
                            headers=self.headers,
                            catch_response=True,
                            name="Send Message to Chat") as response:
            
            if response.status_code == 201:
                pass  # Сообщение успешно отправлено
            elif response.status_code == 400:
                error_data = response.json()
                error_msg = error_data.get('message', 'Validation error')
                response.failure(f"Message validation error: {error_msg}")
            elif response.status_code == 404:
                # Чат не найден - удаляем из списка
                self.chat_ids.remove(chat_id)
                response.failure(f"Chat {chat_id} not found, removed from list")
            elif response.status_code == 401:
                self._login_user()
                response.failure("Token expired during message sending")
            else:
                response.failure(f"Message sending failed: {response.status_code}")
    
    @task(3)
    def view_chat_messages(self):
        """Просмотр сообщений в случайном чате"""
        if not self.token or not self.chat_ids:
            return
        
        chat_id = random.choice(self.chat_ids)
        
        with self.client.get(f"/api/chats/{chat_id}/messages/", 
                           headers=self.headers,
                           catch_response=True,
                           name="View Chat Messages") as response:
            
            if response.status_code == 200:
                data = response.json()
                message_count = data.get('count', 0)
                # Логируем для отладки
                if message_count > 0:
                    pass  # Сообщения успешно получены
            elif response.status_code == 404:
                self.chat_ids.remove(chat_id)
                response.failure(f"Chat {chat_id} not found for messages view")
            elif response.status_code == 401:
                self._login_user()
                response.failure("Token expired during messages view")
            else:
                response.failure(f"Failed to get messages: {response.status_code}")
    
    @task(1)
    def get_user_profile(self):
        """Получение профиля текущего пользователя"""
        if not self.token:
            return
            
        with self.client.get("/api/users/profile/", 
                           headers=self.headers,
                           catch_response=True,
                           name="Get User Profile") as response:
            
            if response.status_code == 200:
                pass  # Профиль успешно получен
            elif response.status_code == 401:
                self._login_user()
                response.failure("Token expired during profile request")
            else:
                response.failure(f"Failed to get profile: {response.status_code}")
    
    def _generate_message_content(self):
        """Генерация разнообразного контента для сообщений"""
        message_types = [
            # Пляжная тематика (триггерит специфический ответ)
            "Хочу создать контент на тему пляжа и моря с пальмами",
            "Нужны идеи для медиа про отпуск на море",
            "Пляжная тематика с белым песком и бирюзовой водой",
            
            # Городская тематика
            "Создай урбан контент с небоскребами и неоновыми огнями", 
            "Городская тематика в стиле футуризм",
            "Ночной город с высотными зданиями",
            
            # Природная тематика
            "Нужен контент про природу: горы и леса",
            "Пейзаж с водопадом в лесной чаще",
            "Горный пейзаж с заснеженными вершинами",
            
            # Общие запросы
            "Помоги сгенерировать медиа-контент для социальных сетей",
            "Нужны идеи для визуального контента",
            "Создай что-то креативное для моего проекта"
        ]
        
        return random.choice(message_types)


class AdminUser(HttpUser):
    """
    Locust пользователь с правами администратора для тестирования админских функций
    """
    wait_time = between(2, 5)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.token = None
        self.headers = {}
    
    def on_start(self):
        """Аутентификация администратора"""
        # Используем предварительно созданного админа
        admin_credentials = {
            "email": "admin@test.com",  # Должен существовать в БД
            "password": "adminpass123"
        }
        
        with self.client.post("/api/auth/login/", 
                            json=admin_credentials,
                            catch_response=True,
                            name="Admin Login") as response:
            
            if response.status_code == 200:
                self.token = response.json()['access']
                self.headers = {"Authorization": f"Bearer {self.token}"}
                logging.info("Admin user successfully authenticated")
            else:
                response.failure(f"Admin login failed: {response.status_code}")
    
    @task(3)
    def view_all_chats(self):
        """Просмотр всех чатов системы (только для админа)"""
        if not self.token:
            return
            
        with self.client.get("/api/chats/", 
                           headers=self.headers,
                           catch_response=True,
                           name="Admin View All Chats") as response:
            
            if response.status_code == 200:
                data = response.json()
                chat_count = data.get('count', 0)
                # Логируем количество чатов для мониторинга
                if chat_count > 0:
                    pass
            elif response.status_code == 403:
                response.failure("Admin access denied for chats")
            else:
                response.failure(f"Admin chats view failed: {response.status_code}")
    
    @task(2)
    def view_all_users(self):
        """Просмотр списка всех пользователей (только для админа)"""
        if not self.token:
            return
            
        with self.client.get("/api/users/", 
                           headers=self.headers,
                           catch_response=True,
                           name="Admin View All Users") as response:
            
            if response.status_code == 200:
                data = response.json()
                user_count = data.get('count', 0)
                # Логируем количество пользователей
                if user_count > 0:
                    pass
            elif response.status_code == 403:
                response.failure("Admin access denied for users")
            else:
                response.failure(f"Admin users view failed: {response.status_code}")
    
    @task(1)
    def view_recent_messages(self):
        """Просмотр последних сообщений системы (только для админа)"""
        if not self.token:
            return
            
        with self.client.get("/api/messages/recent/", 
                           headers=self.headers,
                           catch_response=True,
                           name="Admin View Recent Messages") as response:
            
            if response.status_code == 200:
                data = response.json()
                message_count = data.get('count', 0)
                if message_count > 0:
                    pass
            elif response.status_code == 403:
                response.failure("Admin access denied for messages")
            else:
                response.failure(f"Admin messages view failed: {response.status_code}")


# Команды для запуска:
# locust -f locustfile.py --host=http://localhost:8000
# locust -f locustfile.py --host=http://localhost:8000 --users=100 --spawn-rate=10 --run-time=1h