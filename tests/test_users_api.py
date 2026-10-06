import pytest
from conftest import BASE_URL


def test_soft_delete_user_via_delete_endpoint(api_client):
    # 1. Створюємо окремого адміна/чекера для очищення та перевірок
    admin_user = api_client.create_user_and_auth(full_name="Admin Checker")
    
    # 2. Створюємо тестового користувача і тікет для нього
    user = api_client.create_user_and_auth(full_name="User Soft Delete")
    user_id = user["id"]
    headers = user["headers"]

    ticket_res = api_client.create_ticket(headers=headers, title="Тікет перед деактивацією")
    assert ticket_res.status_code in (200, 201)
    ticket_id = ticket_res.json()["id"]

    # 3. Викликаємо м'яке видалення DELETE /api/users/{user_id} без hard_delete
    del_res = api_client.session.delete(
        f"{BASE_URL}/api/users/{user_id}",
        headers=headers
    )
    assert del_res.status_code == 204, f"Очікувався статус 204, отримано: {del_res.status_code}"

    # 4. Перевіряємо, що користувач більше не може увійти
    login_res = api_client.login_user(user["email"], user["password"])
    assert login_res.status_code in (400, 401, 403), "Деактивований користувач не повинен мати можливість увійти"

    # 5. Перевіряємо, що старий токен деактивовано (запити відхиляються)
    auth_check_res = api_client.session.get(f"{BASE_URL}/api/tickets/{ticket_id}", headers=headers)
    assert auth_check_res.status_code in (401, 403)

    # 6. Перевіряємо, що тікети деактивованого користувача зберігаються в базі (доступні іншим)
    get_ticket_res = api_client.session.get(f"{BASE_URL}/api/tickets/{ticket_id}", headers=admin_user["headers"])
    assert get_ticket_res.status_code == 200, "Тікети деактивованого користувача мають зберігатися"

    # 7. Очищення (hard delete) для тестової БД
    api_client.session.delete(
        f"{BASE_URL}/api/users/{user_id}?hard_delete=true",
        headers=admin_user["headers"]
    )
    api_client.session.delete(
        f"{BASE_URL}/api/users/{admin_user['id']}?hard_delete=true",
        headers=admin_user["headers"]
    )


def test_soft_delete_user_via_deactivate_endpoint(api_client):
    # 1. Створюємо окремого адміна/чекера для очищення
    admin_user = api_client.create_user_and_auth(full_name="Admin Deact")

    # 2. Створюємо тестового користувача
    user = api_client.create_user_and_auth(full_name="User To Deactivate")
    user_id = user["id"]
    headers = user["headers"]

    # 3. Викликаємо POST /api/users/{user_id}/deactivate
    deact_res = api_client.session.post(
        f"{BASE_URL}/api/users/{user_id}/deactivate",
        headers=headers
    )
    assert deact_res.status_code in (200, 204), f"Очікувався 200/204, отримано: {deact_res.status_code}"

    # 4. Перевіряємо статус is_active = False через GET запит від активного користувача
    user_res = api_client.session.get(f"{BASE_URL}/api/users/{user_id}", headers=admin_user["headers"])
    if user_res.status_code == 200:
        assert user_res.json().get("is_active") is False

    # 5. Вхід у систему заблоковано
    login_res = api_client.login_user(user["email"], user["password"])
    assert login_res.status_code in (400, 401, 403)

    # 6. Hard delete очищення
    api_client.session.delete(
        f"{BASE_URL}/api/users/{user_id}?hard_delete=true",
        headers=admin_user["headers"]
    )
    api_client.session.delete(
        f"{BASE_URL}/api/users/{admin_user['id']}?hard_delete=true",
        headers=admin_user["headers"]
    )


def test_hard_delete_user_via_users_endpoint(api_client):
    # 1. Створюємо перевіряючого (checker) заздалегідь, щоб ID не конфліктували
    checker = api_client.create_user_and_auth(full_name="Checker User")

    # 2. Створюємо тестового користувача і тікет для нього
    user = api_client.create_user_and_auth(full_name="User Hard Delete")
    user_id = user["id"]
    headers = user["headers"]

    ticket_res = api_client.create_ticket(headers=headers, title="Тікет для каскадного видалення")
    assert ticket_res.status_code in (200, 201)
    ticket_id = ticket_res.json()["id"]

    # 3. Викликаємо Hard Delete: DELETE /api/users/{user_id}?hard_delete=true
    del_res = api_client.session.delete(
        f"{BASE_URL}/api/users/{user_id}?hard_delete=true",
        headers=headers
    )
    assert del_res.status_code == 204

    # 4. Перевіряємо каскадне видалення тікета через активного користувача (checker)
    get_ticket_res = api_client.session.get(
        f"{BASE_URL}/api/tickets/{ticket_id}",
        headers=checker["headers"]
    )
    assert get_ticket_res.status_code == 404, "Створений тікет мав каскадно видалитись"

    # 5. Перевіряємо, що повторний запит видалення користувача повертає 404
    del_again = api_client.session.delete(
        f"{BASE_URL}/api/users/{user_id}?hard_delete=true",
        headers=checker["headers"]
    )
    assert del_again.status_code == 404

    # Очищаємо чекера
    api_client.session.delete(
        f"{BASE_URL}/api/users/{checker['id']}?hard_delete=true",
        headers=checker["headers"]
    )


def test_hard_delete_user_via_auth_users_endpoint(api_client):
    # 1. Створюємо перевіряючого заздалегідь
    checker = api_client.create_user_and_auth(full_name="Auth Checker")

    # 2. Створюємо тестового користувача
    user = api_client.create_user_and_auth(full_name="User Auth Delete")
    user_id = user["id"]
    headers = user["headers"]

    # 3. Викликаємо DELETE /api/auth/users/{user_id}?hard_delete=true
    del_res = api_client.session.delete(
        f"{BASE_URL}/api/auth/users/{user_id}?hard_delete=true",
        headers=headers
    )
    assert del_res.status_code == 204

    # 4. Повторне видалення повертає 404
    del_again = api_client.session.delete(
        f"{BASE_URL}/api/auth/users/{user_id}?hard_delete=true",
        headers=checker["headers"]
    )
    assert del_again.status_code == 404

    # Очищаємо чекера
    api_client.session.delete(
        f"{BASE_URL}/api/users/{checker['id']}?hard_delete=true",
        headers=checker["headers"]
    )


def test_delete_user_not_found(api_client, test_user):
    # Неіснуючий користувач
    del_res = api_client.session.delete(
        f"{BASE_URL}/api/users/9999999?hard_delete=true",
        headers=test_user["headers"]
    )
    assert del_res.status_code == 404

    del_auth_res = api_client.session.delete(
        f"{BASE_URL}/api/auth/users/9999999?hard_delete=true",
        headers=test_user["headers"]
    )
    assert del_auth_res.status_code == 404


def test_delete_user_unauthorized(api_client, test_user):
    user_id = test_user["id"]

    # Без токена
    res_no_auth = api_client.session.delete(f"{BASE_URL}/api/users/{user_id}")
    assert res_no_auth.status_code in (401, 403)

    # З невалідним токеном
    res_bad_token = api_client.session.delete(
        f"{BASE_URL}/api/users/{user_id}?hard_delete=true",
        headers={"Authorization": "Bearer invalid_token"}
    )
    assert res_bad_token.status_code in (401, 403)
