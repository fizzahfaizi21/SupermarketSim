# src/game.py

from __future__ import annotations

import math
import random
import sys
import time
from typing import Dict, List, Optional

import pygame

from config.settings import *
from src.firebase_service import FirebaseService
from src.models import (
    PRODUCT_CATALOG,
    SHELF_LAYOUT,
    STAFF_POOL,
    UPGRADES,
    GameState,
    ShiftReport,
    generate_review,
    price_suggestion,
    random_customer,
)
from src.ui import (
    AnimatedValue,
    Button,
    SceneFader,
    TextInput,
    ToastManager,
    draw_badge,
    draw_shadowed_card,
    draw_text,
    draw_vertical_gradient,
)


class Session:
    def __init__(self):
        self.uid = ""
        self.id_token = ""
        self.email = ""
        self.username = ""

    def clear(self):
        self.uid = ""
        self.id_token = ""
        self.email = ""
        self.username = ""


class App:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption(TITLE)
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.running = True

        self.firebase = FirebaseService()
        self.toasts = ToastManager()
        self.fader = SceneFader()
        self.session = Session()

        self.state: Optional[GameState] = None
        self.scene = "auth"
        self.menu_modal: Optional[str] = None
        self.overlay: Optional[str] = None

        self.auth_inputs = {
            "username": TextInput((120, 320, 430, 56), "Username"),
            "email": TextInput((120, 400, 430, 56), "Email"),
            "password": TextInput((120, 480, 430, 56), "Password", password=True),
        }

        self.auth_buttons: List[Button] = []
        self.menu_buttons: List[Button] = []
        self.init_auth_buttons()
        self.init_menu_buttons()

        self.player = pygame.Vector2(250, 650)
        self.velocity = pygame.Vector2()
        self.day_timer = DAY_LENGTH_SECONDS
        self.spawn_timer = random.uniform(CUSTOMER_SPAWN_MIN, CUSTOMER_SPAWN_MAX)
        self.next_customer_id = 1
        self.customers: List[Dict] = []
        self.current_customer = None
        self.checkout_change_input = ""
        self.report_cache = None
        self.selected_shelf = 0
        self.overlay_anim = 0.0
        self.zone_rects = self._build_zones()

        self.settings = {
            "music": 80,
            "sfx": 85,
            "reduced_motion": False,
        }

        self.display_money = AnimatedValue(0)
        self.display_sales = AnimatedValue(0)
        self.display_satisfaction = AnimatedValue(0)
        self.display_stress = AnimatedValue(0)
        self.display_fatigue = AnimatedValue(0)
        self.display_score = AnimatedValue(0)

    # ---------- setup ----------
    def init_auth_buttons(self):
        self.auth_buttons = [
            Button((120, 575, 200, 56), "Log In", lambda: self.submit_auth("login"), accent=ACCENT, variant="primary", icon="▶"),
            Button((350, 575, 200, 56), "Register", lambda: self.submit_auth("register"), accent=ACCENT_2, variant="secondary", icon="+"),
        ]

    def init_menu_buttons(self):
        self.menu_buttons = [
            Button((88, 290, 300, 58), "New Game", self.new_game, accent=ACCENT, variant="menu", icon="▶"),
            Button((88, 365, 300, 58), "Load Save", self.load_game, accent=INFO, variant="menu", icon="↺"),
            Button((88, 440, 300, 58), "Leaderboard", lambda: self.open_menu_modal("leaderboard"), accent=ACCENT_2, variant="menu", icon="★"),
            Button((88, 515, 300, 58), "Settings", lambda: self.open_menu_modal("settings"), accent=(125, 145, 255), variant="menu", icon="⚙"),
            Button((88, 590, 300, 58), "Logout", self.logout, accent=DANGER, variant="danger", icon="⎋"),
        ]

    def _build_zones(self):
        return {
            "stock": pygame.Rect(90, 545, 185, 180),
            "checkout": pygame.Rect(1075, 535, 230, 180),
            "manager": pygame.Rect(1175, 135, 180, 120),
            "prices": pygame.Rect(590, 100, 255, 92),
            "break": pygame.Rect(85, 110, 180, 102),
        }

    # ---------- state helpers ----------
    def reset_runtime(self):
        self.overlay = None
        self.menu_modal = None
        self.overlay_anim = 0.0
        self.player.update(250, 650)
        self.velocity.update(0, 0)
        self.day_timer = DAY_LENGTH_SECONDS
        self.spawn_timer = random.uniform(CUSTOMER_SPAWN_MIN, CUSTOMER_SPAWN_MAX)
        self.next_customer_id = 1
        self.customers.clear()
        self.current_customer = None
        self.checkout_change_input = ""
        self.report_cache = None

    def sync_display_values(self):
        if not self.state:
            return
        self.display_money.set(self.state.money)
        self.display_sales.set(self.state.sales_today)
        self.display_satisfaction.set(self.state.satisfaction)
        self.display_stress.set(self.state.stress)
        self.display_fatigue.set(self.state.fatigue)
        self.display_score.set(self.state.score)

    def update_animated_values(self, dt: float):
        self.display_money.update(dt)
        self.display_sales.update(dt)
        self.display_satisfaction.update(dt)
        self.display_stress.update(dt)
        self.display_fatigue.update(dt)
        self.display_score.update(dt)

    def set_scene(self, scene_name: str):
        self.scene = scene_name
        self.fader.fade_in()

    def open_overlay(self, name: str):
        self.overlay = name
        self.overlay_anim = 0.0

    def close_overlay(self):
        self.overlay = None
        self.checkout_change_input = ""

    def open_menu_modal(self, name: str):
        self.menu_modal = name

    def close_menu_modal(self):
        self.menu_modal = None

    # ---------- auth / save ----------
    def new_game(self):
        if not self.session.uid:
            self.toasts.show("Log in first.", DANGER)
            return
        self.state = GameState(username=self.session.username, uid=self.session.uid)
        self.state.email = self.session.email
        self.reset_runtime()
        self.sync_display_values()
        self.set_scene("game")
        self.toasts.show("New market created.", SUCCESS)

    def load_game(self):
        if not self.session.uid:
            self.toasts.show("Log in first.", DANGER)
            return
        try:
            payload = self.firebase.load_game(self.session.uid, self.session.id_token)
            if payload:
                self.state = GameState.from_dict(payload)
                self.reset_runtime()
                self.sync_display_values()
                self.set_scene("game")
                self.toasts.show("Save loaded from Firebase.", SUCCESS)
            else:
                self.toasts.show("No save found. Starting a new game.", WARNING)
                self.new_game()
        except Exception as e:
            self.toasts.show(str(e), DANGER, 4)

    def logout(self):
        self.session.clear()
        self.state = None
        self.overlay = None
        self.menu_modal = None
        self.set_scene("auth")
        self.toasts.show("Logged out.", SUCCESS)

    def submit_auth(self, mode: str):
        username = self.auth_inputs["username"].text.strip()
        email = self.auth_inputs["email"].text.strip()
        password = self.auth_inputs["password"].text.strip()

        if mode == "register" and not username:
            self.toasts.show("Enter a username.", DANGER)
            return
        if not email or not password:
            self.toasts.show("Enter email and password.", DANGER)
            return

        try:
            if mode == "register":
                data = self.firebase.register(email, password, username)
                self.toasts.show("Registration successful.", SUCCESS)
            else:
                data = self.firebase.login(email, password)
                self.toasts.show("Login successful.", SUCCESS)

            self.session.uid = data["uid"]
            self.session.id_token = data["idToken"]
            self.session.email = data["email"]
            self.session.username = data["username"]
            self.set_scene("menu")
        except Exception as e:
            self.toasts.show(str(e), DANGER, 4)

    def save_current_game(self):
        if not self.state:
            return
        try:
            self.state.email = self.session.email
            self.firebase.save_game(self.state.uid, self.session.id_token, self.state.to_dict())
            self.toasts.show("Game saved.", SUCCESS)
        except Exception as e:
            self.toasts.show(str(e), DANGER, 4)

    # ---------- runtime ----------
    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self.handle_events()
            self.update(dt)
            self.draw()
            pygame.display.flip()

        pygame.quit()
        sys.exit()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return

            if self.scene == "auth":
                for inp in self.auth_inputs.values():
                    inp.handle_event(event)
                for btn in self.auth_buttons:
                    btn.handle_event(event)

            elif self.scene == "menu":
                if self.menu_modal:
                    self.handle_menu_modal_event(event)
                else:
                    for btn in self.menu_buttons:
                        btn.handle_event(event)

            elif self.scene == "game":
                self.handle_game_event(event)

    def handle_menu_modal_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.close_menu_modal()
            return

        if event.type == pygame.KEYDOWN and self.menu_modal == "settings":
            if event.key == pygame.K_LEFT:
                self.settings["music"] = max(0, self.settings["music"] - 5)
            elif event.key == pygame.K_RIGHT:
                self.settings["music"] = min(100, self.settings["music"] + 5)
            elif event.key == pygame.K_DOWN:
                self.settings["sfx"] = max(0, self.settings["sfx"] - 5)
            elif event.key == pygame.K_UP:
                self.settings["sfx"] = min(100, self.settings["sfx"] + 5)
            elif event.key == pygame.K_r:
                self.settings["reduced_motion"] = not self.settings["reduced_motion"]

    def handle_game_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.overlay:
                    self.close_overlay()
                else:
                    self.save_current_game()
                    self.set_scene("menu")
            elif event.key == pygame.K_e and not self.overlay:
                self.try_interact()
            elif self.overlay == "checkout":
                if event.key == pygame.K_BACKSPACE:
                    self.checkout_change_input = self.checkout_change_input[:-1]
                elif event.key == pygame.K_RETURN:
                    self.finish_checkout()
                elif event.unicode in "0123456789.":
                    self.checkout_change_input += event.unicode
                elif event.key == pygame.K_1:
                    self.resolve_complaint(True)
                elif event.key == pygame.K_2:
                    self.resolve_complaint(False)

            elif self.overlay == "manager":
                if pygame.K_1 <= event.key <= pygame.K_5:
                    idx = event.key - pygame.K_1
                    self.hire_candidate(idx)
                elif event.key == pygame.K_h:
                    self.fire_last_staff()
                elif event.key == pygame.K_p:
                    self.promote_last_staff()
                elif event.key == pygame.K_u:
                    self.buy_upgrade_by_index(0)
                elif event.key == pygame.K_i:
                    self.buy_upgrade_by_index(1)
                elif event.key == pygame.K_o:
                    self.buy_upgrade_by_index(2)
                elif event.key == pygame.K_m:
                    self.run_social_promo()

            elif self.overlay == "prices":
                if pygame.K_1 <= event.key <= pygame.K_4:
                    idx = event.key - pygame.K_1
                    self.apply_price_suggestion(idx)
                elif event.key == pygame.K_a:
                    for idx in range(4):
                        self.apply_price_suggestion(idx, silent=True)
                    self.toasts.show("Applied all suggested prices.", SUCCESS)

            elif self.overlay == "stock":
                if pygame.K_1 <= event.key <= pygame.K_4:
                    self.stock_shelf(event.key - pygame.K_1)

    def try_interact(self):
        if not self.state:
            return
        player_rect = pygame.Rect(self.player.x - 16, self.player.y - 16, 32, 32)

        for name, rect in self.zone_rects.items():
            if player_rect.colliderect(rect.inflate(46, 46)):
                if name == "break":
                    self.take_break()
                    return
                self.open_overlay(name)
                return

        for i, rect in enumerate(self.shelf_hitboxes()):
            if player_rect.colliderect(rect.inflate(34, 34)):
                self.open_overlay("stock")
                self.selected_shelf = i
                return

    def update(self, dt: float):
        self.fader.update(dt)
        self.toasts.update(dt)
        self.update_animated_values(dt)

        for inp in self.auth_inputs.values():
            inp.update(dt)
        for btn in self.auth_buttons:
            btn.update(dt)
        for btn in self.menu_buttons:
            btn.update(dt)

        if self.overlay:
            target = 1.0
        else:
            target = 0.0
        speed = 18.0 if not self.settings["reduced_motion"] else 28.0
        self.overlay_anim += (target - self.overlay_anim) * min(1.0, dt * speed)

        if self.scene == "game" and self.state:
            self.update_player(dt)

            if not self.overlay:
                self.day_timer -= dt
                self.spawn_timer -= dt

                self.state.stress = min(100, int(self.state.stress + STRESS_TICK * dt))
                self.state.fatigue = min(100, int(self.state.fatigue + FATIGUE_TICK * dt))

                if self.state.stress > 80:
                    self.state.satisfaction = max(0, self.state.satisfaction - 1)

                self.update_customers(dt)

                if self.spawn_timer <= 0 and len(self.customers) < MAX_CUSTOMERS:
                    self.spawn_customer()
                    base = random.uniform(CUSTOMER_SPAWN_MIN, CUSTOMER_SPAWN_MAX)
                    if time.time() < self.state.popularity_boost_until:
                        base *= 0.65
                    self.spawn_timer = max(3.2, base)

                if self.day_timer <= 0:
                    self.end_day()

            self.sync_display_values()

    def update_player(self, dt: float):
        keys = pygame.key.get_pressed()
        direction = pygame.Vector2(0, 0)

        if keys[pygame.K_w] or keys[pygame.K_UP]:
            direction.y -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            direction.y += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            direction.x -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            direction.x += 1

        speed = PLAYER_SPEED * (0.86 if self.state and self.state.fatigue > 60 else 1.0)
        if direction.length_squared() > 0:
            direction = direction.normalize()

        target_velocity = direction * speed
        self.velocity = self.velocity.lerp(target_velocity, min(1.0, dt * 8.0))
        self.player += self.velocity * dt

        self.player.x = max(46, min(WIDTH - 46, self.player.x))
        self.player.y = max(92, min(HEIGHT - 46, self.player.y))

    def update_customers(self, dt: float):
        updated = []
        for customer in self.customers:
            customer["patience"] -= 10 * dt
            customer["alpha"] = min(255, customer.get("alpha", 0) + int(255 * dt * CUSTOMER_FADE_SPEED))
            customer["x"] = min(customer["target_x"], customer.get("x", customer["target_x"] - 60) + 120 * dt)

            if customer["patience"] <= 0:
                self.state.satisfaction = max(0, self.state.satisfaction - 7)
                continue
            updated.append(customer)

        self.customers = updated

        if self.customers and self.current_customer is None:
            self.current_customer = self.customers[0]
        if self.current_customer and self.current_customer not in self.customers:
            self.current_customer = self.customers[0] if self.customers else None

    def spawn_customer(self):
        customer_obj = random_customer(self.next_customer_id, self.state.prices, self.state.demand)
        self.next_customer_id += 1

        row = len(self.customers)
        target_x = 1080 + (row % 2) * 72
        target_y = 510 - row * 62

        payload = {
            "id": customer_obj.id,
            "mood": customer_obj.mood,
            "patience": customer_obj.patience,
            "items": customer_obj.items,
            "complaint": customer_obj.complaint,
            "expected_total": customer_obj.expected_total,
            "pay_with": customer_obj.pay_with,
            "cash_given": customer_obj.cash_given,
            "alpha": 0,
            "x": target_x - 70,
            "target_x": target_x,
            "y": target_y,
        }
        self.customers.append(payload)

    def shelf_hitboxes(self):
        return [
            pygame.Rect(390, 250, 180, 122),
            pygame.Rect(635, 250, 180, 122),
            pygame.Rect(880, 250, 180, 122),
            pygame.Rect(1125, 250, 180, 122),
        ]

    # ---------- gameplay actions ----------
    def stock_shelf(self, idx: int):
        if not self.state:
            return

        categories = list(SHELF_LAYOUT.keys())
        category = categories[idx]
        product_key = SHELF_LAYOUT[category]
        capacity = SHELF_CAPACITY + (8 if self.state.upgrades.get("shelves") else 0)

        if self.state.shelves[category] >= capacity:
            self.toasts.show(f"{category.title()} shelf is already full.", WARNING)
            return

        if self.state.storage[product_key] <= 0:
            self.toasts.show(f"No {PRODUCT_CATALOG[product_key]['name']} left in storage.", DANGER)
            return

        moved = min(4, self.state.storage[product_key], capacity - self.state.shelves[category])
        self.state.storage[product_key] -= moved
        self.state.shelves[category] += moved
        self.state.score += moved * 2
        self.state.satisfaction = min(100, self.state.satisfaction + 1)
        self.toasts.show(f"+ Shelf Restocked: {moved} {PRODUCT_CATALOG[product_key]['name']}", SUCCESS)

    def resolve_complaint(self, good_response: bool):
        if not self.current_customer or not self.current_customer.get("complaint"):
            return

        if good_response:
            self.state.satisfaction = min(100, self.state.satisfaction + 4)
            self.toasts.show("Customer happy. Complaint resolved.", SUCCESS)
        else:
            self.state.satisfaction = max(0, self.state.satisfaction - 8)
            self.toasts.show("Customer upset by response.", DANGER)

        self.current_customer["complaint"] = ""

    def finish_checkout(self):
        if not self.current_customer or not self.state:
            return

        total = self.current_customer["expected_total"]
        for product_key, qty in self.current_customer["items"].items():
            category = PRODUCT_CATALOG[product_key]["category"]
            if self.state.shelves[category] < qty:
                self.toasts.show("Shelf stock too low for this sale.", DANGER)
                return

        if self.current_customer["pay_with"] == "cash":
            try:
                entered = float(self.checkout_change_input or "0")
            except ValueError:
                self.toasts.show("Enter a valid change amount.", DANGER)
                return

            expected_change = round(self.current_customer["cash_given"] - total, 2)
            if abs(entered - expected_change) > 0.01:
                self.state.satisfaction = max(0, self.state.satisfaction - 10)
                self.state.stress = min(100, self.state.stress + 8)
                self.toasts.show("Wrong change given.", DANGER)
                return

        for product_key, qty in self.current_customer["items"].items():
            category = PRODUCT_CATALOG[product_key]["category"]
            self.state.shelves[category] -= qty
            self.state.demand[product_key] = min(2.2, self.state.demand[product_key] + 0.06 * qty)

        self.state.money += total
        self.state.sales_today += total
        self.state.customers_served += 1
        self.state.score += int(total * 4)
        self.state.satisfaction = min(100, self.state.satisfaction + 2)

        transaction = {
            "total_amount": round(total, 2),
            "transaction_time": time.time(),
            "items": self.current_customer["items"],
            "pay_with": self.current_customer["pay_with"],
        }

        try:
            self.firebase.add_transaction(self.state.uid, self.session.id_token, transaction)
        except Exception:
            pass

        self.customers = [c for c in self.customers if c["id"] != self.current_customer["id"]]
        self.current_customer = self.customers[0] if self.customers else None
        self.checkout_change_input = ""
        self.toasts.show(f"+ ${total:.2f} Sale", SUCCESS)

        if self.current_customer is None:
            self.close_overlay()

    def hire_candidate(self, idx: int):
        if not self.state or idx >= len(STAFF_POOL):
            return

        candidate = STAFF_POOL[idx]
        if self.state.money < candidate["wage"]:
            self.toasts.show("Insufficient funds to hire.", DANGER)
            return

        self.state.money -= candidate["wage"]
        self.state.staff.append(dict(candidate))
        self.state.score += 15
        self.toasts.show(f"Employee hired: {candidate['name']}", SUCCESS)

    def fire_last_staff(self):
        if not self.state or not self.state.staff:
            self.toasts.show("No staff to fire.", WARNING)
            return

        fired = self.state.staff.pop()
        self.toasts.show(f"Employee removed: {fired['name']}", WARNING)

    def promote_last_staff(self):
        if not self.state or not self.state.staff:
            self.toasts.show("No staff to promote.", WARNING)
            return

        member = self.state.staff[-1]
        member["skill"] += 1
        member["wage"] += 10
        member["promoted"] = member.get("promoted", 0) + 1
        self.toasts.show(f"Promoted {member['name']}", SUCCESS)

    def buy_upgrade_by_index(self, idx: int):
        if not self.state:
            return

        key = list(UPGRADES.keys())[idx]
        upgrade = UPGRADES[key]

        if self.state.upgrades.get(key):
            self.toasts.show("Upgrade already owned.", WARNING)
            return

        if self.state.money < upgrade["cost"]:
            self.toasts.show("Not enough money for that upgrade.", DANGER)
            return

        self.state.money -= upgrade["cost"]
        self.state.upgrades[key] = True
        self.state.store_level += 1
        self.state.score += 30
        self.toasts.show(f"Purchased {upgrade['name']}", SUCCESS)

    def run_social_promo(self):
        if not self.state:
            return

        if self.state.money < PROMO_COST:
            self.toasts.show("Not enough money for promotion.", DANGER)
            return

        self.state.money -= PROMO_COST
        self.state.popularity_boost_until = time.time() + PROMO_EFFECT_SECONDS
        self.state.score += 20
        self.toasts.show("Promotion launched. Customer flow boosted.", SUCCESS)

    def apply_price_suggestion(self, idx: int, silent=False):
        if not self.state:
            return

        product_key = list(PRODUCT_CATALOG.keys())[idx]
        current = self.state.prices[product_key]
        stock = self.state.storage[product_key] + self.state.shelves[PRODUCT_CATALOG[product_key]["category"]]
        suggested = price_suggestion(current, stock, self.state.demand[product_key])
        self.state.prices[product_key] = suggested

        if suggested > PRODUCT_CATALOG[product_key]["base_price"] * 1.7:
            self.state.satisfaction = max(0, self.state.satisfaction - 5)

        if not silent:
            self.toasts.show(f"Price updated: {PRODUCT_CATALOG[product_key]['name']} → ${suggested:.2f}", SUCCESS)

    def take_break(self):
        if not self.state:
            return

        self.state.stress = max(0, self.state.stress - BREAK_RECOVERY)
        self.state.fatigue = max(0, self.state.fatigue - BREAK_RECOVERY // 2)
        self.toasts.show("Break taken. Stress reduced.", SUCCESS)

    def end_day(self):
        if not self.state:
            return

        wages = sum(m.get("wage", 0) for m in self.state.staff)
        self.state.money -= wages

        for product_key in self.state.storage:
            self.state.storage[product_key] += STORAGE_REPLENISH

        decor_bonus = 8 if self.state.upgrades.get("decor") else 0
        scanner_bonus = 8 if self.state.upgrades.get("scanner") else 0

        review = generate_review(self.state.satisfaction, scanner_bonus, decor_bonus)
        self.state.reviews.append(review)

        try:
            self.firebase.add_review(self.state.uid, self.session.id_token, review)
        except Exception:
            pass

        stocking_eff = min(
            100,
            int(sum(self.state.shelves.values()) / (len(self.state.shelves) * 15) * 100),
        )

        report = ShiftReport(
            day=self.state.day,
            funds=round(self.state.money, 2),
            sales=round(self.state.sales_today, 2),
            customers_served=self.state.customers_served,
            satisfaction=self.state.satisfaction,
            stocking_efficiency=stocking_eff,
            stress=self.state.stress,
            fatigue=self.state.fatigue,
            notes=f"Paid ${wages:.2f} in staff wages.",
        )

        self.state.reports.append(report.to_dict())
        self.report_cache = report.to_dict()

        try:
            self.firebase.add_report(self.state.uid, self.session.id_token, report.to_dict())
        except Exception:
            pass

        self.state.day += 1
        self.state.time_of_day = "day"
        self.state.sales_today = 0
        self.state.customers_served = 0
        self.state.stress = max(5, self.state.stress - 10)
        self.state.fatigue = max(5, self.state.fatigue - 7)

        self.day_timer = DAY_LENGTH_SECONDS
        self.spawn_timer = random.uniform(CUSTOMER_SPAWN_MIN, CUSTOMER_SPAWN_MAX)
        self.customers.clear()
        self.current_customer = None
        self.save_current_game()
        self.open_overlay("report")

    # ---------- drawing ----------
    def draw(self):
        draw_vertical_gradient(self.screen, BG_TOP, BG_BOTTOM)

        if self.scene == "auth":
            self.draw_auth()
        elif self.scene == "menu":
            self.draw_menu()
        elif self.scene == "game":
            self.draw_game()

        self.toasts.draw(self.screen)
        self.fader.draw(self.screen)

    def draw_auth(self):
        card = pygame.Rect(70, 120, 540, 610)
        draw_shadowed_card(self.screen, card, color=PANEL, radius=30)

        draw_text(self.screen, "ByteBit Market", (120, 180), size=BIG_TITLE, bold=True)
        draw_text(self.screen, "Modern supermarket simulator", (122, 236), size=BODY_SIZE, color=TEXT_MUTED)

        self.auth_inputs["username"].draw(self.screen)
        self.auth_inputs["email"].draw(self.screen)
        self.auth_inputs["password"].draw(self.screen)

        for btn in self.auth_buttons:
            btn.draw(self.screen)

        preview = pygame.Rect(680, 105, 690, 630)
        draw_shadowed_card(self.screen, preview, color=CARD, radius=30)
        self.draw_store_preview(preview)

    def draw_store_preview(self, rect: pygame.Rect):
        inset = rect.inflate(-34, -34)
        pygame.draw.rect(self.screen, FLOOR, inset, border_radius=26)

        for y in range(inset.y + 30, inset.bottom - 20, 34):
            pygame.draw.line(self.screen, AISLE, (inset.x + 20, y), (inset.right - 20, y), 1)

        for i in range(4):
            x = inset.x + 48 + i * 145
            shelf = pygame.Rect(x, inset.y + 130, 94, 238)
            pygame.draw.rect(self.screen, WOOD, shelf, border_radius=14)

            for layer in range(3):
                y = shelf.y + 28 + layer * 64
                pygame.draw.rect(self.screen, SHELF, (shelf.x + 8, y, shelf.width - 16, 12), border_radius=7)
                for p in range(4):
                    color = list(PRODUCT_CATALOG.values())[(i + p) % len(PRODUCT_CATALOG)]["color"]
                    pygame.draw.rect(self.screen, color, (shelf.x + 12 + p * 18, y - 24, 13, 24), border_radius=5)

        reg = pygame.Rect(inset.right - 180, inset.bottom - 150, 130, 95)
        pygame.draw.rect(self.screen, REGISTER, reg, border_radius=18)
        pygame.draw.rect(self.screen, FRIDGE, (inset.x + 45, inset.y + 45, 96, 112), border_radius=18)

        draw_text(self.screen, "Polished UI • Smooth overlays • Firebase cloud save", (inset.x + 24, inset.bottom - 54), size=BODY_SIZE, color=TEXT_DARK)

    def draw_menu(self):
        hero = pygame.Rect(50, 76, 1340, 710)
        draw_shadowed_card(self.screen, hero, color=PANEL, radius=34)

        draw_text(self.screen, f"Welcome back, {self.session.username}", (88, 126), size=BIG_TITLE, bold=True)
        draw_text(self.screen, "Manage inventory, staff, pricing, customers, and daily performance.", (90, 182), size=BODY_SIZE, color=TEXT_MUTED)

        for btn in self.menu_buttons:
            btn.draw(self.screen)

        cards = [
            ("Inventory", "Restock shelves, manage prices, avoid empty aisles.", ACCENT),
            ("Operations", "Checkout, customer flow, employee performance.", INFO),
            ("Progress", "Firebase saves, reports, reviews, leaderboard.", ACCENT_2),
        ]

        x = 470
        for title, body, color in cards:
            rect = pygame.Rect(x, 320, 260, 210)
            draw_shadowed_card(self.screen, rect, color=CARD, radius=26)
            draw_badge(self.screen, title, rect.x + 16, rect.y + 16, color=color)
            draw_text(self.screen, body, (rect.x + 20, rect.y + 86), size=BODY_SIZE, color=TEXT_MUTED)
            x += 295

        tip = pygame.Rect(470, 565, 650, 115)
        draw_shadowed_card(self.screen, tip, color=CARD_DARK, radius=24)
        draw_text(self.screen, "Flow", (490, 588), size=TITLE_SIZE, bold=True)
        draw_text(self.screen, "Login → Menu → Market Floor → Daily Report → Save/Leaderboard", (490, 628), size=BODY_SIZE, color=TEXT_MUTED)

        if self.menu_modal == "leaderboard":
            self.draw_menu_modal("Leaderboard", self.draw_leaderboard_content)
        elif self.menu_modal == "settings":
            self.draw_menu_modal("Settings", self.draw_settings_content)

    def draw_menu_modal(self, title: str, renderer):
        bg = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        bg.fill((6, 8, 16, 145))
        self.screen.blit(bg, (0, 0))

        panel = pygame.Rect(230, 120, 980, 610)
        draw_shadowed_card(self.screen, panel, color=PANEL, radius=28)
        draw_text(self.screen, title, (270, 155), size=TITLE_SIZE, bold=True)
        draw_text(self.screen, "Press ESC to close", (970, 160), size=SMALL_SIZE, color=TEXT_MUTED)
        renderer(panel)

    def draw_settings_content(self, panel: pygame.Rect):
        draw_text(self.screen, "Left/Right: music volume", (270, 230), size=BODY_SIZE, color=TEXT_MUTED)
        draw_text(self.screen, "Up/Down: SFX volume", (270, 265), size=BODY_SIZE, color=TEXT_MUTED)
        draw_text(self.screen, "R: toggle reduced motion", (270, 300), size=BODY_SIZE, color=TEXT_MUTED)

        rows = [
            ("Music", self.settings["music"]),
            ("SFX", self.settings["sfx"]),
        ]

        y = 380
        for label, value in rows:
            draw_text(self.screen, label, (280, y), size=TITLE_SIZE, bold=True)
            bar = pygame.Rect(430, y + 2, 420, 24)
            pygame.draw.rect(self.screen, PANEL_ALT, bar, border_radius=12)
            pygame.draw.rect(self.screen, ACCENT, (bar.x, bar.y, int(bar.width * value / 100), bar.height), border_radius=12)
            draw_text(self.screen, f"{value}%", (875, y - 2), size=BODY_SIZE)
            y += 82

        state_text = "On" if self.settings["reduced_motion"] else "Off"
        draw_text(self.screen, "Reduced Motion", (280, 555), size=TITLE_SIZE, bold=True)
        draw_badge(self.screen, state_text, 505, 548, color=WARNING if self.settings["reduced_motion"] else SUCCESS)

    def draw_game(self):
        self.draw_store_map()
        self.draw_hud()
        self.draw_customers()
        self.draw_player()

        if self.overlay:
            self.draw_overlay()

    def draw_store_map(self):
        floor = pygame.Rect(28, 74, WIDTH - 56, HEIGHT - 110)
        pygame.draw.rect(self.screen, FLOOR, floor, border_radius=24)

        for y in range(floor.y + 34, floor.bottom - 28, 40):
            pygame.draw.line(self.screen, AISLE, (floor.x + 16, y), (floor.right - 16, y), 1)

        zone_colors = {
            "stock": (214, 236, 244),
            "checkout": (214, 222, 248),
            "manager": (229, 220, 255),
            "prices": (223, 242, 220),
            "break": (251, 234, 209),
        }

        for name, rect in self.zone_rects.items():
            pygame.draw.rect(self.screen, zone_colors[name], rect, border_radius=20)
            pygame.draw.rect(self.screen, (255, 255, 255), rect, 2, border_radius=20)

            glow = pygame.Surface((rect.width + 30, rect.height + 30), pygame.SRCALPHA)
            pygame.draw.rect(glow, (*ZONE_GLOW, 28), glow.get_rect(), border_radius=26)
            self.screen.blit(glow, (rect.x - 15, rect.y - 15))

            draw_text(self.screen, name.title(), rect.center, size=BODY_SIZE, color=TEXT_DARK, bold=True, center=True)
            draw_text(self.screen, "Press E", (rect.centerx, rect.bottom - 18), size=SMALL_SIZE, color=(78, 88, 118), center=True)

        labels = list(SHELF_LAYOUT.keys())
        for i, rect in enumerate(self.shelf_hitboxes()):
            pygame.draw.rect(self.screen, WOOD, rect, border_radius=14)
            for level in range(3):
                y = rect.y + 22 + level * 32
                pygame.draw.rect(self.screen, SHELF, (rect.x + 10, y, rect.width - 20, 10), border_radius=6)

            category = labels[i]
            product_key = SHELF_LAYOUT[category]
            capacity = SHELF_CAPACITY + (8 if self.state.upgrades.get("shelves") else 0)
            qty = self.state.shelves[category]
            fill_ratio = min(1.0, qty / max(1, capacity))
            fill_color = PRODUCT_CATALOG[product_key]["color"]

            for item_index in range(min(qty, 9)):
                row = item_index // 3
                col = item_index % 3
                pygame.draw.rect(
                    self.screen,
                    fill_color,
                    (rect.x + 28 + col * 42, rect.y + 8 + row * 32, 24, 24),
                    border_radius=6,
                )

            bar = pygame.Rect(rect.x + 16, rect.bottom + 10, rect.width - 32, 10)
            pygame.draw.rect(self.screen, PANEL_ALT, bar, border_radius=5)
            pygame.draw.rect(self.screen, ACCENT if fill_ratio > 0.35 else WARNING if fill_ratio > 0.15 else DANGER,
                             (bar.x, bar.y, int(bar.width * fill_ratio), bar.height), border_radius=5)

            draw_text(self.screen, category.title(), (rect.x + 10, rect.bottom + 26), size=SMALL_SIZE, color=TEXT_DARK, bold=True)
            draw_text(self.screen, f"${self.state.prices[product_key]:.2f}", (rect.right - 58, rect.bottom + 24), size=SMALL_SIZE, color=TEXT_DARK)

    def draw_hud(self):
        top = pygame.Rect(18, 12, WIDTH - 36, 56)
        draw_shadowed_card(self.screen, top, color=PANEL, radius=18, shadow_offset=4)

        items = [
            ("Day", str(self.state.day)),
            ("Money", f"${self.display_money.value:.0f}"),
            ("Customers", str(len(self.customers))),
            ("Reputation", str(self.display_satisfaction.as_int())),
            ("Alerts", "Promo" if time.time() < self.state.popularity_boost_until else "None"),
        ]

        x = 40
        for label, value in items:
            draw_text(self.screen, label, (x, 22), size=SMALL_SIZE, color=TEXT_MUTED)
            draw_text(self.screen, value, (x, 40), size=BODY_SIZE, bold=True)
            x += 220

        bottom = pygame.Rect(22, HEIGHT - 92, 840, 56)
        draw_shadowed_card(self.screen, bottom, color=PANEL, radius=18, shadow_offset=4)

        metrics = [
            ("Stress", self.display_stress.as_int(), DANGER),
            ("Fatigue", self.display_fatigue.as_int(), WARNING),
            ("Score", self.display_score.as_int(), INFO),
        ]

        x = 42
        for label, value, color in metrics:
            draw_text(self.screen, label, (x, HEIGHT - 77), size=SMALL_SIZE, color=TEXT_MUTED)
            bar = pygame.Rect(x + 72, HEIGHT - 74, 150, 14)
            pygame.draw.rect(self.screen, PANEL_ALT, bar, border_radius=7)
            fill = 150 if label == "Score" else int(150 * min(100, value) / 100)
            pygame.draw.rect(self.screen, color, (bar.x, bar.y, fill, bar.height), border_radius=7)
            draw_text(self.screen, str(value), (bar.right + 12, HEIGHT - 79), size=SMALL_SIZE, bold=True)
            x += 268

        if time.time() < self.state.popularity_boost_until:
            draw_badge(self.screen, "PROMO BOOST ACTIVE", WIDTH - 290, HEIGHT - 84, color=SUCCESS)

    def draw_player(self):
        shadow = pygame.Surface((48, 22), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 55), shadow.get_rect())
        self.screen.blit(shadow, (self.player.x - 24, self.player.y + 12))
        pygame.draw.circle(self.screen, PLAYER, (int(self.player.x), int(self.player.y)), 18)
        pygame.draw.circle(self.screen, ACCENT, (int(self.player.x), int(self.player.y) - 22), 13)

    def draw_customers(self):
        for customer in self.customers[:6]:
            alpha = customer.get("alpha", 255)
            surf = pygame.Surface((50, 70), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*CUSTOMER, alpha), (25, 40), 16)
            pygame.draw.circle(surf, (255, 243, 232, alpha), (25, 18), 12)
            patience_ratio = max(0, customer["patience"]) / 100
            pygame.draw.rect(surf, (50, 54, 78, alpha), (7, 58, 36, 6), border_radius=3)
            fill_color = WARNING if patience_ratio > 0.4 else DANGER
            pygame.draw.rect(surf, (*fill_color, alpha), (7, 58, int(36 * patience_ratio), 6), border_radius=3)
            self.screen.blit(surf, (customer["x"], customer["y"]))

    def draw_overlay(self):
        bg = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        bg.fill((5, 8, 18, int(140 * self.overlay_anim)))
        self.screen.blit(bg, (0, 0))

        slide = int((1.0 - self.overlay_anim) * PANEL_SLIDE_DISTANCE)
        panel = pygame.Rect(170, 92 + slide, 1100, 678)
        draw_shadowed_card(self.screen, panel, color=PANEL, radius=30)

        title_map = {
            "stock": "Inventory & Stock Shelves",
            "checkout": "Checkout",
            "manager": "Employee Management & Upgrades",
            "prices": "Smart Pricing",
            "leaderboard": "Leaderboard",
            "report": "Daily Report",
            "reviews": "Customer Reviews",
        }

        draw_text(self.screen, title_map.get(self.overlay, self.overlay.title()), (210, 126 + slide), size=TITLE_SIZE, bold=True)
        draw_text(self.screen, "Press ESC to close", (990, 131 + slide), size=SMALL_SIZE, color=TEXT_MUTED)

        if self.overlay == "stock":
            self.draw_stock_overlay(panel)
        elif self.overlay == "checkout":
            self.draw_checkout_overlay(panel)
        elif self.overlay == "manager":
            self.draw_manager_overlay(panel)
        elif self.overlay == "prices":
            self.draw_prices_overlay(panel)
        elif self.overlay == "leaderboard":
            self.draw_leaderboard_overlay(panel)
        elif self.overlay == "report":
            self.draw_report_overlay(panel)
        elif self.overlay == "reviews":
            self.draw_reviews_overlay(panel)

    def draw_stock_overlay(self, panel: pygame.Rect):
        draw_text(self.screen, "Keys 1-4 restock the matching section.", (210, 170), color=TEXT_MUTED)

        categories = list(SHELF_LAYOUT.keys())
        x = 220
        for idx, category in enumerate(categories):
            rect = pygame.Rect(x, 225, 220, 330)
            draw_shadowed_card(self.screen, rect, color=CARD, radius=24)

            product_key = SHELF_LAYOUT[category]
            capacity = SHELF_CAPACITY + (8 if self.state.upgrades.get("shelves") else 0)
            fill_ratio = min(1.0, self.state.shelves[category] / max(1, capacity))

            draw_text(self.screen, f"{idx + 1}. {category.title()}", (rect.x + 20, rect.y + 24), size=TITLE_SIZE, bold=True)
            draw_text(self.screen, PRODUCT_CATALOG[product_key]["name"], (rect.x + 20, rect.y + 72), size=BODY_SIZE, color=TEXT_MUTED)
            draw_text(self.screen, f"Storage: {self.state.storage[product_key]}", (rect.x + 20, rect.y + 124), size=BODY_SIZE)
            draw_text(self.screen, f"Shelf: {self.state.shelves[category]}/{capacity}", (rect.x + 20, rect.y + 164), size=BODY_SIZE)
            draw_text(self.screen, f"Price: ${self.state.prices[product_key]:.2f}", (rect.x + 20, rect.y + 204), size=BODY_SIZE)

            color = PRODUCT_CATALOG[product_key]["color"]
            pygame.draw.rect(self.screen, PANEL_ALT, (rect.x + 20, rect.y + 260, 180, 14), border_radius=7)
            pygame.draw.rect(self.screen, color, (rect.x + 20, rect.y + 260, int(180 * fill_ratio), 14), border_radius=7)
            pygame.draw.rect(self.screen, color, (rect.x + 20, rect.y + 288, 84, 28), border_radius=10)

            x += 250

    def draw_checkout_overlay(self, panel: pygame.Rect):
        if not self.current_customer:
            draw_text(self.screen, "No customer currently waiting at checkout.", panel.center, size=TITLE_SIZE, color=TEXT_MUTED, center=True)
            return

        left = pygame.Rect(210, 180, 430, 500)
        right = pygame.Rect(670, 180, 560, 500)
        draw_shadowed_card(self.screen, left, color=CARD, radius=24)
        draw_shadowed_card(self.screen, right, color=CARD, radius=24)

        draw_text(self.screen, f"Customer #{self.current_customer['id']}", (left.x + 22, left.y + 24), size=TITLE_SIZE, bold=True)
        draw_text(self.screen, f"Mood: {self.current_customer['mood']}", (left.x + 22, left.y + 72), size=BODY_SIZE)
        draw_text(self.screen, f"Patience: {int(self.current_customer['patience'])}", (left.x + 22, left.y + 108), size=BODY_SIZE)
        draw_text(self.screen, f"Payment: {self.current_customer['pay_with']}", (left.x + 22, left.y + 144), size=BODY_SIZE)

        y = left.y + 210
        for product_key, qty in self.current_customer["items"].items():
            draw_text(self.screen, f"{PRODUCT_CATALOG[product_key]['name']} × {qty}", (left.x + 22, y), size=BODY_SIZE)
            draw_text(self.screen, f"${self.state.prices[product_key] * qty:.2f}", (left.right - 120, y), size=BODY_SIZE)
            y += 40

        draw_text(self.screen, f"Total: ${self.current_customer['expected_total']:.2f}", (left.x + 22, left.bottom - 72), size=TITLE_SIZE, bold=True)

        if self.current_customer.get("complaint"):
            draw_text(self.screen, "Complaint", (right.x + 24, right.y + 24), size=TITLE_SIZE, bold=True)
            draw_text(self.screen, self.current_customer["complaint"], (right.x + 24, right.y + 76), size=BODY_SIZE, color=TEXT_MUTED)
            draw_text(self.screen, "1. Good response", (right.x + 24, right.y + 142), size=BODY_SIZE, color=SUCCESS)
            draw_text(self.screen, "2. Poor response", (right.x + 24, right.y + 178), size=BODY_SIZE, color=DANGER)

        pay_y = right.y + 280
        if self.current_customer["pay_with"] == "cash":
            draw_text(self.screen, f"Cash given: ${self.current_customer['cash_given']:.2f}", (right.x + 24, pay_y), size=BODY_SIZE)
            expected = self.current_customer["cash_given"] - self.current_customer["expected_total"]
            draw_text(self.screen, f"Expected change: ${expected:.2f}", (right.x + 24, pay_y + 40), size=BODY_SIZE, color=TEXT_MUTED)

            inp = pygame.Rect(right.x + 24, pay_y + 100, 255, 56)
            draw_shadowed_card(self.screen, inp, color=PANEL_ALT, radius=18)
            placeholder = self.checkout_change_input or "Type change and press Enter"
            draw_text(self.screen, placeholder, (inp.x + 16, inp.y + 17), size=BODY_SIZE, color=TEXT if self.checkout_change_input else TEXT_MUTED)
        else:
            draw_text(self.screen, "Card payment — no change needed.", (right.x + 24, pay_y), size=BODY_SIZE)

        draw_badge(self.screen, "ENTER = COMPLETE SALE", right.x + 20, right.bottom - 70, color=ACCENT)

    def draw_manager_overlay(self, panel: pygame.Rect):
        draw_text(self.screen, "1-5 hire  •  H fire  •  P promote  •  U/I/O upgrades  •  M promo", (210, 170), color=TEXT_MUTED)

        x = 220
        for idx, candidate in enumerate(STAFF_POOL):
            rect = pygame.Rect(x, 220, 180, 245)
            draw_shadowed_card(self.screen, rect, color=CARD, radius=24)
            draw_text(self.screen, f"{idx + 1}. {candidate['name']}", (rect.x + 18, rect.y + 24), size=BODY_SIZE, bold=True)
            draw_text(self.screen, candidate["role"].title(), (rect.x + 18, rect.y + 66), size=BODY_SIZE, color=TEXT_MUTED)
            draw_text(self.screen, f"Wage ${candidate['wage']}", (rect.x + 18, rect.y + 114), size=BODY_SIZE)
            draw_text(self.screen, f"Skill {candidate['skill']}", (rect.x + 18, rect.y + 152), size=BODY_SIZE)
            x += 190

        staff_box = pygame.Rect(220, 500, 420, 200)
        draw_shadowed_card(self.screen, staff_box, color=CARD, radius=24)
        draw_text(self.screen, f"Employees ({len(self.state.staff)})", (staff_box.x + 20, staff_box.y + 20), size=TITLE_SIZE, bold=True)

        sy = staff_box.y + 70
        for member in self.state.staff[-4:]:
            draw_text(self.screen, f"{member['name']} • {member['role']} • skill {member['skill']}", (staff_box.x + 20, sy), size=BODY_SIZE)
            sy += 32

        up_box = pygame.Rect(680, 500, 550, 200)
        draw_shadowed_card(self.screen, up_box, color=CARD, radius=24)
        draw_text(self.screen, "Upgrades", (up_box.x + 20, up_box.y + 20), size=TITLE_SIZE, bold=True)

        labels = ["U", "I", "O"]
        for i, (key, value) in enumerate(UPGRADES.items()):
            owned = "Owned" if self.state.upgrades.get(key) else f"${value['cost']}"
            draw_text(self.screen, f"{labels[i]} • {value['name']} ({owned})", (up_box.x + 20, up_box.y + 72 + i * 36), size=BODY_SIZE)

        draw_text(self.screen, "M • Social promotion ($120)", (up_box.x + 20, up_box.bottom - 38), size=BODY_SIZE, color=SUCCESS)

    def draw_prices_overlay(self, panel: pygame.Rect):
        draw_text(self.screen, "1-4 apply suggested item price  •  A apply all", (210, 170), color=TEXT_MUTED)

        x = 220
        for idx, product_key in enumerate(PRODUCT_CATALOG):
            rect = pygame.Rect(x, 235, 230, 330)
            draw_shadowed_card(self.screen, rect, color=CARD, radius=24)

            current = self.state.prices[product_key]
            stock = self.state.storage[product_key] + self.state.shelves[PRODUCT_CATALOG[product_key]["category"]]
            suggested = price_suggestion(current, stock, self.state.demand[product_key])

            draw_text(self.screen, f"{idx + 1}. {PRODUCT_CATALOG[product_key]['name']}", (rect.x + 18, rect.y + 24), size=TITLE_SIZE, bold=True)
            draw_text(self.screen, f"Current: ${current:.2f}", (rect.x + 18, rect.y + 92), size=BODY_SIZE)
            draw_text(self.screen, f"Suggested: ${suggested:.2f}", (rect.x + 18, rect.y + 132), size=BODY_SIZE, color=SUCCESS)
            draw_text(self.screen, f"Demand: {self.state.demand[product_key]:.2f}", (rect.x + 18, rect.y + 176), size=BODY_SIZE)
            draw_text(self.screen, f"Stock: {stock}", (rect.x + 18, rect.y + 216), size=BODY_SIZE)

            diff = max(-0.4, min(0.4, suggested - current))
            bar = pygame.Rect(rect.x + 18, rect.y + 270, 180, 12)
            pygame.draw.rect(self.screen, PANEL_ALT, bar, border_radius=6)
            fill = int((diff + 0.4) / 0.8 * bar.width)
            pygame.draw.rect(self.screen, ACCENT if suggested >= current else WARNING, (bar.x, bar.y, fill, bar.height), border_radius=6)

            x += 250

    def draw_leaderboard_overlay(self, panel: pygame.Rect):
        draw_text(self.screen, "Live data from Firebase Realtime Database", (210, 170), color=TEXT_MUTED)

        rows = []
        try:
            raw = self.firebase.get_leaderboard(self.session.id_token) if self.session.id_token else {}
            for _, entry in (raw or {}).items():
                rows.append(entry)
            rows.sort(key=lambda x: x.get("score", 0), reverse=True)
        except Exception as e:
            draw_text(self.screen, str(e), (210, 220), size=BODY_SIZE, color=DANGER)
            rows = []

        table = pygame.Rect(210, 220, 1020, 460)
        draw_shadowed_card(self.screen, table, color=CARD, radius=24)

        headers = [("Rank", 250), ("Username", 380), ("Score", 700), ("Money", 860), ("Day", 1030)]
        for text, x in headers:
            draw_text(self.screen, text, (x, 252), size=BODY_SIZE, bold=True)

        y = 302
        if not rows:
            draw_text(self.screen, "No leaderboard entries yet.", table.center, size=BODY_SIZE, color=TEXT_MUTED, center=True)
            return

        for i, entry in enumerate(rows[:10], start=1):
            if i == 1:
                pygame.draw.rect(self.screen, (255, 213, 79, 30), (230, y - 10, 960, 34), border_radius=12)
            draw_text(self.screen, str(i), (252, y), size=BODY_SIZE)
            draw_text(self.screen, entry.get("username", "Player"), (380, y), size=BODY_SIZE)
            draw_text(self.screen, str(entry.get("score", 0)), (700, y), size=BODY_SIZE)
            draw_text(self.screen, f"${entry.get('money', 0):.2f}", (860, y), size=BODY_SIZE)
            draw_text(self.screen, str(entry.get("day", 1)), (1030, y), size=BODY_SIZE)
            y += 40

    def draw_report_overlay(self, panel: pygame.Rect):
        report = self.report_cache or (self.state.reports[-1] if self.state.reports else None)
        if not report:
            draw_text(self.screen, "No daily report yet.", panel.center, size=TITLE_SIZE, color=TEXT_MUTED, center=True)
            return

        metrics = [
            ("Funds", f"${report['funds']:.2f}", SUCCESS),
            ("Sales", f"${report['sales']:.2f}", INFO),
            ("Customers", str(report['customers_served']), ACCENT_2),
            ("Satisfaction", str(report['satisfaction']), WARNING),
            ("Stocking", str(report['stocking_efficiency']), SUCCESS),
            ("Stress", str(report['stress']), DANGER),
            ("Fatigue", str(report['fatigue']), WARNING),
        ]

        x = 220
        y = 220
        for idx, (label, value, color) in enumerate(metrics):
            rect = pygame.Rect(x, y, 220, 140)
            draw_shadowed_card(self.screen, rect, color=CARD, radius=24)
            draw_text(self.screen, label, (rect.x + 18, rect.y + 24), size=BODY_SIZE, color=TEXT_MUTED)
            draw_text(self.screen, value, (rect.x + 18, rect.y + 68), size=TITLE_SIZE, bold=True, color=color)

            x += 250
            if (idx + 1) % 4 == 0:
                x = 220
                y += 170

        note_rect = pygame.Rect(220, 570, 1010, 110)
        draw_shadowed_card(self.screen, note_rect, color=CARD, radius=24)
        draw_text(self.screen, f"Notes: {report['notes']}", (note_rect.x + 18, note_rect.y + 24), size=BODY_SIZE)
        draw_text(self.screen, "A review was generated and the game was auto-saved.", (note_rect.x + 18, note_rect.y + 60), size=BODY_SIZE, color=TEXT_MUTED)

    def draw_reviews_overlay(self, panel: pygame.Rect):
        reviews = list(reversed(self.state.reviews[-8:]))
        if not reviews:
            draw_text(self.screen, "No reviews yet.", panel.center, size=TITLE_SIZE, color=TEXT_MUTED, center=True)
            return

        y = 200
        for review in reviews:
            rect = pygame.Rect(220, y, 1000, 76)
            draw_shadowed_card(self.screen, rect, color=CARD, radius=18)
            draw_text(self.screen, "★" * review["stars"], (rect.x + 18, rect.y + 22), size=BODY_SIZE, color=ACCENT_2, bold=True)
            draw_text(self.screen, review["comment"], (rect.x + 140, rect.y + 22), size=BODY_SIZE)
            y += 92