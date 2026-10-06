import pytest
import time
import requests
from playwright.sync_api import Page

BASE_URL = "http://127.0.0.1:8000"


class APIClient:
    def __init__(self, base_url=BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def register_user(self, full_name="Test User", email=None, password="password123"):
        if email is None:
            email = f"test_{int(time.time() * 1000)}@example.com"

        payload = {
            "full_name": full_name,
            "email": email,
            "password": password
        }
        res = self.session.post(f"{self.base_url}/api/auth/register", json=payload)
        return res, email, password

    def login_user(self, email, password="password123"):
        # FastAPI OAuth2PasswordRequestForm використовує application/x-www-form-urlencoded
        return self.session.post(
            f"{self.base_url}/api/auth/login",
            data={"username": email, "password": password}
        )

    def get_auth_token(self, email, password="password123"):
        res = self.login_user(email, password)
        if res.status_code == 200:
            data = res.json()
            token = data.get("access_token") or data.get("token")
            user = data.get("user") or {}
            user_id = user.get("id") or data.get("user_id") or data.get("id")
            return token, user_id
        return None, None

    def create_user_and_auth(self, full_name="Test User", email=None, password="password123"):
        reg_res, email, password = self.register_user(full_name, email, password)
        user_id = None
        user_data = {}
        if reg_res.status_code in (200, 201):
            try:
                reg_data = reg_res.json()
                user_data = reg_data
                user_id = reg_data.get("id") or (reg_data.get("user") or {}).get("id")
            except Exception:
                pass

        token, login_user_id = self.get_auth_token(email, password)
        if not user_id:
            user_id = login_user_id

        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return {
            "id": user_id,
            "email": email,
            "password": password,
            "token": token,
            "headers": headers,
            "register_response": reg_res,
            "user_data": user_data
        }

    def create_ticket(self, headers, title="Test Ticket", description="Description", ticket_type="Bug", status="ToDo", priority="Medium"):
        payload = {
            "title": title,
            "description": description,
            "type": ticket_type,
            "status": status,
            "priority": priority
        }
        return self.session.post(f"{self.base_url}/api/tickets", json=payload, headers=headers)


@pytest.fixture
def api_client():
    return APIClient(BASE_URL)


@pytest.fixture
def test_user(api_client):
    user = api_client.create_user_and_auth()
    yield user
    # Hard delete cleanup в кінці тесту
    if user.get("id") and user.get("token"):
        try:
            api_client.session.delete(
                f"{BASE_URL}/api/users/{user['id']}?hard_delete=true",
                headers={"Authorization": f"Bearer {user['token']}"},
                timeout=5
            )
        except Exception:
            pass


@pytest.fixture(scope="function")
def authenticated_page(page: Page):
    # Унікальний email для кожного прогону
    user_email = f"test_{int(time.time() * 1000)}@example.com"
    user_password = "password123"

    page.goto(BASE_URL)

    # Очищуємо localStorage для ізоляції кожного тесту
    page.evaluate("() => localStorage.clear()")
    page.reload()

    # Перемикаємось на форму реєстрації
    page.locator("p.cursor-pointer").click()
    page.fill("input[x-model='authForm.fullName']", "Test User")
    page.fill("input[x-model='authForm.email']", user_email)
    page.fill("input[x-model='authForm.password']", user_password)

    # Приймаємо alert про успішну реєстрацію
    page.once("dialog", lambda dialog: dialog.accept())
    page.click("button:has-text('Зареєструватися')")

    # Вхід у систему
    page.fill("input[x-model='authForm.email']", user_email)
    page.fill("input[x-model='authForm.password']", user_password)
    page.click("button:has-text('Увійти')")

    # Чекаємо завантаження дошки
    page.wait_for_selector("h1:has-text('Rapid Task')")

    yield page

    # Hard delete cleanup тестового користувача після завершення тесту
    try:
        token = page.evaluate("() => localStorage.getItem('token') || localStorage.getItem('access_token') || sessionStorage.getItem('token')")
        user_data = page.evaluate("() => localStorage.getItem('user') || sessionStorage.getItem('user')")
        user_id = None
        if user_data:
            import json
            try:
                user_obj = json.loads(user_data) if isinstance(user_data, str) else user_data
                user_id = user_obj.get("id") or user_obj.get("user_id")
            except Exception:
                pass

        if token:
            headers = {"Authorization": f"Bearer {token}"}
            if not user_id:
                res = requests.get(f"{BASE_URL}/api/auth/me", headers=headers, timeout=5)
                if res.status_code == 200:
                    user_id = res.json().get("id")
            if user_id:
                requests.delete(f"{BASE_URL}/api/users/{user_id}?hard_delete=true", headers=headers, timeout=5)
    except Exception:
        pass
