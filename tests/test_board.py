from playwright.sync_api import Page, expect


def test_create_ticket(authenticated_page: Page):
    page = authenticated_page

    # 1. Відкриваємо модалку
    page.click("button:has-text('+ Створити тікет')")

    # 2. Заповнюємо форму
    ticket_title = "Автоматизований тестовий тікет"
    page.fill("input[x-model='newTicket.title']", ticket_title)
    page.select_option("select[x-model='newTicket.type']", "Bug")
    page.fill("textarea[x-model='newTicket.description']", "Це опис створений через Playwright")

    # 3. Сабмітимо форму конкретною кнопкою відправки
    page.click("form button[type='submit']")

    # 4. Перевіряємо, що тікет з'явився у колонці ToDo
    todo_col = page.locator(".kanban-col[data-status='ToDo']")
    expect(todo_col.locator(f"text={ticket_title}")).to_be_visible()


def test_drag_and_drop_ticket(authenticated_page: Page):
    page = authenticated_page

    # Створюємо тікет для перетягування
    page.click("button:has-text('+ Створити тікет')")
    ticket_title = "Тікет для Drag and Drop"
    page.fill("input[x-model='newTicket.title']", ticket_title)
    page.click("form button[type='submit']")

    # Елементи для перетягування
    card = page.locator(f"h4:has-text('{ticket_title}')")
    in_progress_col = page.locator(".kanban-col[data-status='In progress']")

    # Перетягуємо картку з ToDo в In progress
    card.drag_to(in_progress_col)

    # Перевіряємо, що картка дійсно опинилася в новій колонці
    expect(in_progress_col.locator(f"text={ticket_title}")).to_be_visible()


def test_open_ticket_modal(authenticated_page: Page):
    page = authenticated_page

    # Створюємо тікет
    page.click("button:has-text('+ Створити тікет')")
    ticket_title = "Перевірка поп-апа"
    page.fill("input[x-model='newTicket.title']", ticket_title)
    page.click("form button[type='submit']")

    # Клікаємо на картку
    page.click(f"h4:has-text('{ticket_title}')")

    # Перевіряємо відкриття поп-апа
    modal = page.locator("div[x-show='selectedTicket']")
    expect(modal).to_be_visible()
    expect(modal.locator("h2")).to_have_text(ticket_title)