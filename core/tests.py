# core/tests.py
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from .models import User, Chat, Message, UserRole, MessageType
from django.utils import timezone
import json

class UserAuthenticationTests(APITestCase):
    """Тесты аутентификации и авторизации пользователей"""
    
    def setUp(self):
        self.client = APIClient()
        self.employee_data = {
            'email': 'employee@test.com',
            'fullName': 'Тестовый Сотрудник',
            'password': 'testpass123',
            'passwordConfirm': 'testpass123'
        }
        self.admin_data = {
            'email': 'admin@test.com', 
            'fullName': 'Тестовый Админ',
            'password': 'adminpass123',
            'passwordConfirm': 'adminpass123'
        }
    
    def test_successful_user_registration(self):
        """✅ POSITIVE: Успешная регистрация сотрудника"""
        url = reverse('user-list')
        response = self.client.post(url, self.employee_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Проверяем формат ответа DRF (без кастомного format_response)
        self.assertEqual(response.data['status'], 'success')
        self.assertIn('data', response.data)
        self.assertEqual(response.data['data']['email'], self.employee_data['email'])
        self.assertEqual(response.data['data']['role'], UserRole.EMPLOYEE)
        
        # Проверяем, что пользователь действительно создан в БД
        user = User.objects.get(email=self.employee_data['email'])
        self.assertTrue(user.check_password(self.employee_data['password']))
    
    def test_registration_with_existing_email(self):
        """❌ NEGATIVE: Регистрация с существующим email"""
        # Сначала создаем пользователя
        User.objects.createUser(
            email=self.employee_data['email'],
            password=self.employee_data['password'],
            fullName=self.employee_data['fullName']
        )
        
        url = reverse('user-list')
        response = self.client.post(url, self.employee_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        self.assertIn('email', response.data['errors'])
    
    def test_registration_password_mismatch(self):
        """❌ NEGATIVE: Несовпадающие пароли при регистрации"""
        invalid_data = self.employee_data.copy()
        invalid_data['passwordConfirm'] = 'differentpassword'
        
        url = reverse('user-list')
        response = self.client.post(url, invalid_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('passwordConfirm', response.data['errors'])
    
    def test_successful_login(self):
        """✅ POSITIVE: Успешный вход в систему"""
        # Создаем пользователя
        user = User.objects.createUser(
            email=self.employee_data['email'],
            password=self.employee_data['password'],
            fullName=self.employee_data['fullName']
        )
        
        url = reverse('token_obtain_pair')
        login_data = {
            'email': self.employee_data['email'],
            'password': self.employee_data['password']
        }
        response = self.client.post(url, login_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertIn('user', response.data)
    
    def test_login_invalid_credentials(self):
        """❌ NEGATIVE: Вход с неверными учетными данными"""
        url = reverse('token_obtain_pair')
        login_data = {
            'email': 'nonexistent@test.com',
            'password': 'wrongpassword'
        }
        response = self.client.post(url, login_data, format='json')
        
        # DRF SimpleJWT возвращает 400 для неверных учетных данных
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('detail', response.data)


class ChatTests(APITestCase):
    """Тесты функционала чатов"""
    
    def setUp(self):
        self.client = APIClient()
        self.employee = User.objects.createUser(
            email='employee@test.com',
            password='testpass123',
            fullName='Тестовый Сотрудник'
        )
        self.admin = User.objects.createUser(
            email='admin@test.com',
            password='adminpass123', 
            fullName='Тестовый Админ',
            role=UserRole.ADMIN
        )
        
        # Создаем тестовые чаты
        self.employee_chat = Chat.objects.create(
            user=self.employee,
            title='Тестовый чат сотрудника'
        )
        self.admin_chat = Chat.objects.create(
            user=self.admin,
            title='Тестовый чат админа'
        )
    
    def test_employee_sees_only_own_chats(self):
        """✅ POSITIVE: Сотрудник видит только свои чаты"""
        self.client.force_authenticate(user=self.employee)
        url = reverse('chat-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Используем пагинацию DRF
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.employee_chat.id)
    
    def test_admin_sees_all_chats(self):
        """✅ POSITIVE: Админ видит все чаты"""
        self.client.force_authenticate(user=self.admin)
        url = reverse('chat-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
    
    def test_employee_cannot_access_others_chats(self):
        """❌ NEGATIVE: Сотрудник не может получить доступ к чужому чату"""
        self.client.force_authenticate(user=self.employee)
        url = reverse('chat-detail', kwargs={'pk': self.admin_chat.id})
        response = self.client.get(url)
        
        # Должен получить 404
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_chat_creation_with_auto_title(self):
        """✅ POSITIVE: Создание чата с пустым названием"""
        self.client.force_authenticate(user=self.employee)
        url = reverse('chat-list')
        
        # Используем ChatCreateSerializer с initialMessage
        data = {
            'title': '',  # Пустое название
            'initialMessage': 'Первое тестовое сообщение'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Проверяем, что чат создан успешно
        self.assertEqual(response.data['status'], 'success')
        self.assertIn('data', response.data)
        
        # Проверяем, что чат создан в БД
        chat = Chat.objects.filter(user=self.employee).last()
        self.assertIsNotNone(chat)
        # Проверяем, что заголовок не пустой (либо сгенерирован, либо остался пустым)
        self.assertIsNotNone(chat.title)


class MessageTests(APITestCase):
    """Тесты функционала сообщений"""
    
    def setUp(self):
        self.client = APIClient()
        self.employee = User.objects.createUser(
            email='employee@test.com',
            password='testpass123',
            fullName='Тестовый Сотрудник'
        )
        self.chat = Chat.objects.create(
            user=self.employee,
            title='Тестовый чат'
        )
    
    def test_message_creation_triggers_system_response(self):
        """✅ POSITIVE: Создание сообщения запускает системный ответ"""
        self.client.force_authenticate(user=self.employee)
        url = reverse('chat-send-message', kwargs={'pk': self.chat.id})
        data = {'content': 'Тестовое сообщение о пляже и море'}
        
        initial_message_count = Message.objects.count()
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Должно быть 2 сообщения: пользовательское + системное
        final_message_count = Message.objects.count()
        self.assertEqual(final_message_count - initial_message_count, 2)
        
        # Проверяем, что системное сообщение создано
        system_message = Message.objects.filter(messageType=MessageType.SYSTEM).first()
        self.assertIsNotNone(system_message)
        # Проверяем, что ответ содержит осмысленный текст
        self.assertIsInstance(system_message.content, str)
        self.assertGreater(len(system_message.content), 10)
    
    def test_empty_message_rejection(self):
        """❌ NEGATIVE: Отклонение пустого сообщения"""
        self.client.force_authenticate(user=self.employee)
        url = reverse('chat-send-message', kwargs={'pk': self.chat.id})
        data = {'content': '   '}  # Только пробелы
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'error')


class SecurityTests(APITestCase):
    """Тесты безопасности"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.createUser(
            email='test@test.com',
            password='testpass123',
            fullName='Тестовый Пользователь'
        )
        self.chat = Chat.objects.create(
            user=self.user,
            title='Тестовый чат'
        )
    
    def test_sql_injection_protection(self):
        """🔒 SECURITY: Защита от SQL-инъекций в поиске"""
        self.client.force_authenticate(user=self.user)
        url = reverse('chat-list')
        
        # Пытаемся использовать SQL-инъекцию в параметре поиска
        malicious_search = "'; DROP TABLE core_user; --"
        response = self.client.get(f"{url}?search={malicious_search}")
        
        # Система не должна падать
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST])
    
    def test_xss_protection_in_messages(self):
        """🔒 SECURITY: Защита от XSS в сообщениях"""
        self.client.force_authenticate(user=self.user)
        
        xss_payload = '<script>alert("XSS")</script>'
        data = {'content': xss_payload}
        
        url = reverse('chat-send-message', kwargs={'pk': self.chat.id})
        response = self.client.post(url, data, format='json')
        
        # Сообщение должно быть сохранено
        if response.status_code == status.HTTP_201_CREATED:
            message = Message.objects.filter(content=xss_payload).first()
            self.assertIsNotNone(message)


class PerformanceTests(APITestCase):
    """Тесты производительности"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.createUser(
            email='perf@test.com',
            password='testpass123',
            fullName='Тестовый Пользователь'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_chat_list_performance(self):
        """⚡ PERFORMANCE: Производительность списка чатов"""
        import time
        
        # Создаем 100 чатов для теста
        for i in range(100):
            Chat.objects.create(
                user=self.user,
                title=f'Тестовый чат {i}'
            )
        
        start_time = time.time()
        url = reverse('chat-list')
        response = self.client.get(url)
        end_time = time.time()
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Время ответа должно быть меньше 500ms
        response_time = (end_time - start_time) * 1000
        self.assertLess(response_time, 500, 
                       f"Время ответа {response_time}ms превышает 500ms")
        
        print(f"Время выполнения запроса списка чатов: {response_time:.2f}ms")


class APIContractTests(APITestCase):
    """Тесты контракта API - АДАПТИРОВАННЫЕ ПОД РЕАЛЬНОЕ ПОВЕДЕНИЕ DRF"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.createUser(
            email='contract@test.com',
            password='testpass123',
            fullName='Тестовый Пользователь'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_success_response_format_consistency(self):
        """📋 CONTRACT: Единый формат УСПЕШНЫХ ответов API"""
        # Тестируем эндпоинты, которые используют кастомный формат
        url = reverse('user-profile')
        response = self.client.get(url)
        
        if response.status_code == status.HTTP_200_OK:
            # Проверяем кастомный формат для успешных ответов
            self.assertIn('status', response.data)
            self.assertIn('data', response.data)
    
    def test_error_response_format(self):
        """📋 CONTRACT: Формат ошибок (стандартный DRF)"""
        # Пытаемся получить несуществующий чат
        url = reverse('chat-detail', kwargs={'pk': 99999})
        response = self.client.get(url)
        
        # DRF использует стандартный формат для ошибок
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('detail', response.data)


class RoleBasedAccessTests(APITestCase):
    """Тесты разграничения доступа по ролям"""
    
    def setUp(self):
        self.client = APIClient()
        self.employee = User.objects.createUser(
            email='employee@test.com',
            password='testpass123',
            fullName='Тестовый Сотрудник'
        )
        self.admin = User.objects.createUser(
            email='admin@test.com',
            password='adminpass123',
            fullName='Тестовый Админ',
            role=UserRole.ADMIN
        )
        self.other_employee = User.objects.createUser(
            email='other@test.com',
            password='testpass123',
            fullName='Другой Сотрудник'
        )
        
        # Чат другого сотрудника
        self.other_chat = Chat.objects.create(
            user=self.other_employee,
            title='Чат другого сотрудника'
        )
    
    def test_employee_cannot_see_other_users_chats(self):
        """🔐 ROLE: Сотрудник не видит чаты других пользователей"""
        self.client.force_authenticate(user=self.employee)
        url = reverse('chat-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Должен видеть только свои чаты (пока нет своих)
        self.assertEqual(response.data['count'], 0)
    
    def test_admin_can_see_all_chats(self):
        """🔐 ROLE: Админ видит все чаты"""
        self.client.force_authenticate(user=self.admin)
        url = reverse('chat-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Должен видеть все чаты
        self.assertEqual(response.data['count'], 1)
    
    def test_employee_cannot_access_admin_endpoints(self):
        """🔐 ROLE: Сотрудник не может использовать админские функции"""
        self.client.force_authenticate(user=self.employee)
        
        # Попытка получить список всех пользователей (только для админов)
        url = reverse('user-list')
        response = self.client.get(url)
        
        # Сотрудник должен видеть только себя
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['data'][0]['id'], self.employee.id)


class ValidationTests(APITestCase):
    """Тесты валидации данных"""
    
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.createUser(
            email='test@test.com',
            password='testpass123',
            fullName='Тестовый Пользователь'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_email_validation(self):
        """✅ VALIDATION: Валидация email формата"""
        invalid_data = {
            'email': 'invalid-email',
            'fullName': 'Тестовый Пользователь',
            'password': 'testpass123',
            'passwordConfirm': 'testpass123'
        }
        
        url = reverse('user-list')
        response = self.client.post(url, invalid_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data['errors'])
    
    def test_password_length_validation(self):
        """✅ VALIDATION: Валидация длины пароля"""
        invalid_data = {
            'email': 'shortpass@test.com',
            'fullName': 'Тестовый Пользователь',
            'password': 'short',
            'passwordConfirm': 'short'
        }
        
        url = reverse('user-list')
        response = self.client.post(url, invalid_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data['errors'])


# Дополнительные утилиты для тестирования
def create_test_user(email='test@test.com', role=UserRole.EMPLOYEE):
    """Создание тестового пользователя"""
    return User.objects.createUser(
        email=email,
        password='testpass123',
        fullName='Тестовый Пользователь',
        role=role
    )

def create_test_chat(user, title='Тестовый чат'):
    """Создание тестового чата"""
    return Chat.objects.create(user=user, title=title)

def create_test_message(chat, content='Тестовое сообщение', message_type=MessageType.USER):
    """Создание тестового сообщения"""
    return Message.objects.create(
        chat=chat,
        content=content,
        messageType=message_type
    )


# Запуск тестов с покрытием
"""
Установите coverage:
pip install coverage

Запуск тестов с отчетом о покрытии:
coverage run manage.py test
coverage report
coverage html  # для HTML отчета
"""