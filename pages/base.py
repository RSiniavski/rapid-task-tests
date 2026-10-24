"""Tiny page objects. English UI strings are taken from static/js/i18n.js (tests run with rt_lang=en)."""
from playwright.sync_api import Page, expect


class Landing:
    def __init__(self, page: Page):
        self.p = page
        self.modal = page.locator("#auth-backdrop")

    def open(self):
        self.p.goto("/")
        return self

    def open_login(self):
        self.p.locator("[data-open-auth='login']").first.click()
        expect(self.modal).to_have_class(__import__("re").compile("open"))
        return self

    def open_register(self):
        self.p.locator("[data-open-auth='register']").first.click()
        expect(self.modal).to_have_class(__import__("re").compile("open"))
        return self

    def login(self, email, password):
        self.p.fill("#login-email", email)
        self.p.fill("#login-password", password)
        self.p.locator("#form-login button[type=submit]").click()

    def register(self, name, email, password):
        self.p.fill("#reg-name", name)
        self.p.fill("#reg-email", email)
        self.p.fill("#reg-password", password)
        self.p.locator("#form-register button[type=submit]").click()


class Dashboard:
    def __init__(self, page: Page):
        self.p = page

    def open(self):
        self.p.goto("/dashboard.html")
        self.p.wait_for_selector("h1")
        return self

    def card(self, name):
        return self.p.locator(".project-card", has_text=name)

    def create_project(self, name, key, lang="en"):
        self.p.get_by_role("button", name="＋ New project").first.click()
        dlg = self.p.locator(".modal-backdrop.open .modal")
        dlg.locator("input").nth(0).fill(name)
        dlg.locator("input").nth(1).fill(key)
        dlg.locator("select").select_option(lang)
        dlg.get_by_role("button", name="Create project").click()


class Board:
    def __init__(self, page: Page):
        self.p = page

    def open(self, project_id):
        self.p.goto(f"/board.html?project={project_id}")
        self.p.wait_for_selector(".kanban-col, .card")
        return self

    def column(self, name):
        return self.p.locator(".kanban-col", has=self.p.locator(".kanban-col-name", has_text=name)).first

    def ticket(self, key_or_title):
        return self.p.locator(".ticket-card", has_text=key_or_title).first


class Roadmap:
    def __init__(self, page: Page):
        self.p = page

    def open(self, project_id):
        self.p.goto(f"/roadmap.html?project={project_id}")
        self.p.wait_for_selector("#rm-viewport")
        return self

    def block(self, title):
        return self.p.locator(".rm-block", has_text=title).first
