import pytest
from conftest import BASE_URL


def test_delete_ticket_by_id_success(api_client, test_user):
    # 1. Створюємо тікет
    create_res = api_client.create_ticket(
        headers=test_user["headers"],
        title="Тікет для видалення за ID",
        description="Опис тікета",
        ticket_type="Bug",
        status="ToDo"
    )
    assert create_res.status_code in (200, 201), f"Не вдалося створити тікет: {create_res.text}"
    ticket = create_res.json()
    ticket_id = ticket["id"]

    # 2. Видаляємо тікет за числовим ID
    del_res = api_client.session.delete(
        f"{BASE_URL}/api/tickets/{ticket_id}",
        headers=test_user["headers"]
    )
    assert del_res.status_code == 204, f"Очікувався статус 204, отримано: {del_res.status_code}"

    # 3. Перевіряємо, що тікет більше не знайдено (404)
    get_res = api_client.session.get(
        f"{BASE_URL}/api/tickets/{ticket_id}",
        headers=test_user["headers"]
    )
    assert get_res.status_code == 404

    # 4. Повторне видалення повертає 404
    del_res_repeat = api_client.session.delete(
        f"{BASE_URL}/api/tickets/{ticket_id}",
        headers=test_user["headers"]
    )
    assert del_res_repeat.status_code == 404


def test_delete_ticket_by_key_success(api_client, test_user):
    # 1. Створюємо тікет
    create_res = api_client.create_ticket(
        headers=test_user["headers"],
        title="Тікет для видалення за Key",
        description="Опис тікета за ключем",
        ticket_type="Task",
        status="ToDo"
    )
    assert create_res.status_code in (200, 201), f"Не вдалося створити тікет: {create_res.text}"
    ticket = create_res.json()
    ticket_key = ticket.get("key") or ticket.get("ticket_key")
    ticket_id = ticket["id"]
    assert ticket_key, "Тікет повинен мати ключ (наприклад RT-1)"

    # 2. Видаляємо тікет за ключем
    del_res = api_client.session.delete(
        f"{BASE_URL}/api/tickets/key/{ticket_key}",
        headers=test_user["headers"]
    )
    assert del_res.status_code == 204, f"Очікувався статус 204, отримано: {del_res.status_code}"

    # 3. Перевіряємо, що тікет більше не існує
    get_res = api_client.session.get(
        f"{BASE_URL}/api/tickets/{ticket_id}",
        headers=test_user["headers"]
    )
    assert get_res.status_code == 404

    # 4. Повторне видалення за тим же ключем повертає 404
    del_res_repeat = api_client.session.delete(
        f"{BASE_URL}/api/tickets/key/{ticket_key}",
        headers=test_user["headers"]
    )
    assert del_res_repeat.status_code == 404


def test_delete_ticket_not_found(api_client, test_user):
    # Неіснуючий числовий ID
    res_id = api_client.session.delete(
        f"{BASE_URL}/api/tickets/9999999",
        headers=test_user["headers"]
    )
    assert res_id.status_code == 404

    # Неіснуючий ключ
    res_key = api_client.session.delete(
        f"{BASE_URL}/api/tickets/key/NONEXISTENT-99999",
        headers=test_user["headers"]
    )
    assert res_key.status_code == 404


def test_delete_ticket_unauthorized(api_client, test_user):
    # Створюємо тікет авторизовано
    create_res = api_client.create_ticket(
        headers=test_user["headers"],
        title="Тікет для перевірки авторизації"
    )
    assert create_res.status_code in (200, 201)
    ticket_id = create_res.json()["id"]

    # Спроба видалення без токена
    res_no_auth = api_client.session.delete(f"{BASE_URL}/api/tickets/{ticket_id}")
    assert res_no_auth.status_code in (401, 403)

    # Спроба видалення з невалідним токеном
    res_invalid_token = api_client.session.delete(
        f"{BASE_URL}/api/tickets/{ticket_id}",
        headers={"Authorization": "Bearer invalid_token_12345"}
    )
    assert res_invalid_token.status_code in (401, 403)
