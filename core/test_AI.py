from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from .models import User, Chat, Message, PromptParameters, PromptTemplate, UserRole

def get_auth_headers(email, password, client):
    login_url = reverse('token_obtain_pair')
    resp = client.post(login_url, {'email': email, 'password': password}, format='json')
    assert resp.status_code == 200, f"Auth failed: {resp.data}"
    token = resp.data['access']
    return {'HTTP_AUTHORIZATION': f'Bearer {token}'}

class AITestCases(APITestCase):
    """
    МОДУЛЬ: Тестирование с помощью ИИ
    Ожидаемый результат: Проверка нестандартных сценариев, граничных значений, устойчивости.
    """
    def setUp(self):
        self.client = APIClient()
        self.email = 'aiuser@gmail.com'
        self.password = 'StrongPass123'
        reg_data = {
            'email': self.email,
            'fullName': 'AI User',
            'password': self.password,
            'passwordConfirm': self.password
        }
        reg_url = reverse('user-list')
        reg_resp = self.client.post(reg_url, reg_data, format='json')
        assert reg_resp.status_code == status.HTTP_201_CREATED, f"User registration failed: {reg_resp.data}"
        self.auth_headers = get_auth_headers(self.email, self.password, self.client)

    def test_create_chat_with_max_title_length(self):
        """Ожидаемый результат: чат создаётся с максимально допустимой длиной названия"""
        chat_url = reverse('chat-list')
        max_title = 'A' * 255
        chat_data = {'title': max_title, 'initialMessage': 'Тест'}
        resp = self.client.post(chat_url, chat_data, format='json', **self.auth_headers)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['data']['title'], max_title)

    def test_create_message_with_empty_content(self):
        """Ожидаемый результат: ошибка 400 при создании сообщения с пустым содержимым"""
        chat_url = reverse('chat-list')
        chat_data = {'title': 'AI Чат', 'initialMessage': 'Тест'}
        chat_resp = self.client.post(chat_url, chat_data, format='json', **self.auth_headers)
        chat_id = chat_resp.data['data']['id']
        messages_url = reverse('message-list')
        msg_data = {'chat': chat_id, 'content': ''}
        resp = self.client.post(messages_url, msg_data, format='json', **self.auth_headers)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bulk_create_chats(self):
        """Ожидаемый результат: система корректно обрабатывает массовое создание чатов"""
        chat_url = reverse('chat-list')
        for i in range(50):
            chat_data = {'title': f'AI Chat {i}', 'initialMessage': 'Тест'}
            resp = self.client.post(chat_url, chat_data, format='json', **self.auth_headers)
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_access_promptparameters_of_other_user(self):
        """Ожидаемый результат: ошибка 404 или 403 при попытке получить параметры другого пользователя"""
        other_email = 'otherai@gmail.com'
        other_password = 'StrongPass123'
        reg_data = {
            'email': other_email,
            'fullName': 'Other AI',
            'password': other_password,
            'passwordConfirm': other_password
        }
        reg_url = reverse('user-list')
        reg_resp = self.client.post(reg_url, reg_data, format='json')
        assert reg_resp.status_code == status.HTTP_201_CREATED, f"Other user registration failed: {reg_resp.data}"
        other_user = User.objects.get(email=other_email)
        params = PromptParameters.objects.create(
            user=other_user,
            data={'content_type': 'фото', 'idea': 'чужой'}
        )
        params_url = reverse('promptparameters-detail', kwargs={'pk': params.id})
        resp = self.client.get(params_url, **self.auth_headers)
        self.assertIn(resp.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

    def test_delete_prompt_template(self):
        """Ожидаемый результат: шаблон промпта удаляется, сборка промпта невозможна"""
        template = PromptTemplate.objects.create(
            name='AI шаблон',
            template='Тест шаблон',
            is_active=True
        )
        template_url = reverse('prompttemplate-detail', kwargs={'pk': template.id})
        resp = self.client.delete(template_url, **self.auth_headers)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        # Попытка собрать промпт после удаления
        params = PromptParameters.objects.create(
            user=User.objects.get(email=self.email),
            data={'content_type': 'фото', 'idea': 'тест'}
        )
        assemble_url = reverse('promptactions-assemble')
        data = {
            'prompt_parameters_id': str(params.id),
            'template_id': str(template.id)
        }
        resp2 = self.client.post(assemble_url, data, format='json', **self.auth_headers)
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_chat_without_initial_message(self):
        """Ожидаемый результат: чат создаётся даже без initialMessage"""
        chat_url = reverse('chat-list')
        chat_data = {'title': 'Без initialMessage'}
        resp = self.client.post(chat_url, chat_data, format='json', **self.auth_headers)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['data']['title'], 'Без initialMessage')

    def test_get_chats_pagination(self):
        """Ожидаемый результат: пагинация работает корректно"""
        chat_url = reverse('chat-list')
        for i in range(25):
            chat_data = {'title': f'Paginated Chat {i}', 'initialMessage': 'Тест'}
            self.client.post(chat_url, chat_data, format='json', **self.auth_headers)
        resp = self.client.get(f"{chat_url}?page=2", **self.auth_headers)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('results', resp.data)

    def test_update_user_fullname(self):
        """Ожидаемый результат: пользователь может обновить своё имя"""
        user_url = reverse('user-detail', kwargs={'pk': User.objects.get(email=self.email).id})
        update_data = {'fullName': 'AI User Updated'}
        resp = self.client.patch(user_url, update_data, format='json', **self.auth_headers)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['fullName'], 'AI User Updated')

    def test_get_me_profile(self):
        """Ожидаемый результат: эндпоинт /api/users/me/ возвращает профиль пользователя"""
        me_url = reverse('user-me')
        resp = self.client.get(me_url, **self.auth_headers)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('data', resp.data)
        self.assertEqual(resp.data['data']['email'], self.email)

    def test_get_user_summary(self):
        """Ожидаемый результат: эндпоинт /api/users/summary/ возвращает сводку по чатам"""
        summary_url = reverse('user-summary')
        resp = self.client.get(summary_url, **self.auth_headers)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('data', resp.data)
        self.assertIn('total_chats', resp.data['data'])