from locust import HttpUser, task, between
import random

class ContentumLoadUser(HttpUser):
    """
    МОДУЛЬ: Нагрузочное тестирование (Load)
    Ожидаемый результат: система выдерживает массовые регистрации, создание чатов, сообщений, сбор параметров.
    """
    wait_time = between(1, 2)

    def on_start(self):
        self.email = f"load{random.randint(10000,99999)}@yandex.ru"
        self.password = "LoadTestPass123"
        self.headers = {}
        self._register_and_login()

    def _register_and_login(self):
        reg_data = {
            "email": self.email,
            "fullName": "Load User",
            "password": self.password,
            "passwordConfirm": self.password
        }
        reg_resp = self.client.post("/api/users/", json=reg_data)
        if reg_resp.status_code != 201:
            print(f"Registration failed: {reg_resp.text}")
            self.headers = {}
            return
        login_data = {"email": self.email, "password": self.password}
        login_resp = self.client.post("/api/auth/login/", json=login_data)
        if login_resp.status_code == 200 and "access" in login_resp.json():
            token = login_resp.json()["access"]
            self.headers = {"Authorization": f"Bearer {token}"}
        else:
            print(f"Login failed: {login_resp.text}")
            self.headers = {}

    def _ensure_auth(self):
        # Если нет токена, пробуем залогиниться заново
        if not self.headers or "Authorization" not in self.headers:
            self._register_and_login()

    @task(2)
    def create_chat_and_flow(self):
        # Создание чата
        self._ensure_auth()
        chat_data = {
            "title": f"Load Chat {random.randint(1,1000)}",
            "initialMessage": "Хочу фото"
        }
        chat_resp = self.client.post("/api/chats/", json=chat_data, headers=self.headers)
        if chat_resp.status_code == 201 and "data" in chat_resp.json():
            chat_id = chat_resp.json()["data"]["id"]
            # Первый ответ
            msg_data = {"chat": chat_id, "content": "Фото"}
            self.client.post("/api/messages/", json=msg_data, headers=self.headers)
            # Остальные шаги flow (имитация 17 шагов)
            for step in range(1, 17):
                msg_data = {"chat": chat_id, "content": f"Ответ {step}"}
                self.client.post("/api/messages/", json=msg_data, headers=self.headers)

    @task(1)
    def assemble_prompt(self):
        self._ensure_auth()
        # Получаем параметры
        resp = self.client.get("/api/promptparameters/", headers=self.headers)
        results = resp.json().get("results", [])
        if resp.status_code == 200 and results:
            param_id = results[0]["id"]
            # Получаем шаблон (берём первый)
            tmpl_resp = self.client.get("/api/prompttemplates/", headers=self.headers)
            tmpl_results = tmpl_resp.json().get("results", [])
            if tmpl_resp.status_code == 200 and tmpl_results:
                template_id = tmpl_results[0]["id"]
                self.client.post("/api/promptactions/assemble/", json={
                    "prompt_parameters_id": param_id,
                    "template_id": template_id
                }, headers=self.headers)

    @task(1)
    def generate_media(self):
        self._ensure_auth()
        resp = self.client.get("/api/promptparameters/", headers=self.headers)
        results = resp.json().get("results", [])
        if resp.status_code == 200 and results:
            param_id = results[0]["id"]
            self.client.post("/api/promptactions/generate/", json={
                "prompt_parameters_id": param_id
            }, headers=self.headers)

    @task(1)
    def send_message(self):
        self._ensure_auth()
        # Получаем список чатов
        resp = self.client.get("/api/chats/", headers=self.headers)
        chats = resp.json().get("results", [])
        if resp.status_code == 200 and chats:
            chat_id = chats[0]["id"]
            msg_data = {"chat": chat_id, "content": "Сообщение для нагрузки"}
            self.client.post("/api/messages/", json=msg_data, headers=self.headers)

# Команды для запуска:
# locust -f core/locustfile.py --host=http://localhost:8000