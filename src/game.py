# src/game.py

#note for others. game preview assets that shows up in main game are commented lines 2195-2220 and 2235-2428. if you need them. they are right there 
from __future__ import annotations

import math
import random
import sys
import time
from typing import Dict, List, Optional
from Dialogue import customer_dialogues
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
    get_font,
    lerp,
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

        # retro auth screen animation state
        self.auth_time: float = 0.0
        self.pixel_particles: list = []
        self._init_pixel_particles()
        self._init_preview_chars()

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

        if self.scene in ("auth", "menu"):
            self.auth_time += dt
            # drift particles upward and respawn
            for p in self.pixel_particles:
                p[1] -= p[4] * dt        # y  (speed)
                p[5] += dt               # age
                if p[1] < -8 or p[5] > p[6]:
                    self._respawn_particle(p)

        if self.scene in ("auth", "menu"):
            # update preview characters with smooth walk cycles
            # inset mirrors draw_store_preview: preview rect is (660,80,720,720) inflated by -20
            # corridors at ~0.19 / 0.41 / 0.66 / 0.91 of inset width
            preview_rect = pygame.Rect(660, 80, 720, 720)
            inset = preview_rect.inflate(-20, -20)
            iw, ih = inset.width, inset.height
            ix, iy = inset.x, inset.y

            for i, ch in enumerate(self._preview_chars):
                cfg = self._char_cfg[i]
                y_min_frac, y_max_frac, speed = cfg[0], cfg[1], cfg[2]

                y_min = iy + y_min_frac * ih
                y_max = iy + y_max_frac * ih

                # x is always the corridor centre for this character
                ch["x"] = ix + ch["x_frac"] * iw

                # initialise y on first frame (before any movement)
                if ch["y"] == 0.0:
                    ch["y"] = iy + ch["y_frac"] * ih
                    # also ensure vy is non-zero
                    if ch["vy"] == 0.0:
                        ch["vy"] = 1.0

                ch["walk_phase"] += dt * 8.0

                if ch["pause_t"] > 0:
                    ch["pause_t"] -= dt
                else:
                    # guarantee vy is non-zero before moving
                    if ch["vy"] == 0.0:
                        ch["vy"] = 1.0
                    ch["y"] += ch["vy"] * speed * dt
                    # bounce at bounds
                    if ch["y"] >= y_max:
                        ch["y"] = y_max
                        ch["vy"] = -abs(ch["vy"])
                        ch["pause_t"] = random.uniform(0.3, 1.0)
                    elif ch["y"] <= y_min:
                        ch["y"] = y_min
                        ch["vy"] = abs(ch["vy"])
                        ch["pause_t"] = random.uniform(0.3, 1.0)
                    # occasional random direction flip
                    if random.random() < 0.003:
                        ch["vy"] *= -1
                        ch["pause_t"] = random.uniform(0.2, 0.6)

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
            "posResponse": customer_obj.posRes,
            "negResponse": customer_obj.negRes,
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

    def _init_pixel_particles(self):
        self.pixel_particles = []
        for _ in range(80):
            p = [0, 0, 0, 0, 0, 0, 0]
            self._respawn_particle(p, fresh=True)
            self.pixel_particles.append(p)

    def _respawn_particle(self, p, fresh=False):
        # p = [x, y, size, color_idx, speed, age, lifetime]
        p[0] = random.randint(0, WIDTH)
        p[1] = random.randint(0, HEIGHT) if fresh else HEIGHT + 4
        p[2] = random.choice([3, 3, 4, 5, 6, 7])
        p[3] = random.randint(0, 3)
        p[4] = random.uniform(55, 130)
        p[5] = 0.0
        p[6] = random.uniform(2.0, 5.5)

    def _init_preview_chars(self):
        """Characters walk up and down the aisle corridors between shelf sections.
        Corridor centres (approximate fractions of inset width):
          Left wall → Grocery (0.09) → corridor ~0.19 → Frozen (0.29) →
          corridor ~0.41 → Deli (0.53) → corridor ~0.66 → Tech (0.79) → right wall
        """
        def make_char(x_frac, y_frac, vy, body_col, hat_col=None, label="", carrying=False):
            # vy must never start at 0 or char won't move until a random flip
            vy = vy if vy != 0.0 else 1.0
            return {
                "x_frac": float(x_frac),
                "x": 0.0,
                "y": 0.0,
                "vy": float(vy),
                "walk_phase": random.uniform(0, math.pi * 2),
                "body_col": body_col,
                "hat_col": hat_col,
                "label": label,
                "carrying": carrying,
                "pause_t": random.uniform(0.0, 0.6),  # stagger start
                "y_frac": float(y_frac),
                "moving": True,
            }

        # Each character is placed in a corridor gap, NOT inside a shelf.
        # Corridor x_fracs (midpoints between section centres):
        #   0.19 = between Grocery & Frozen
        #   0.41 = between Frozen & Deli
        #   0.66 = between Deli & Tech
        #   0.91 = right of Tech (near checkout)
        self._preview_chars = [
            # Customer 1 — grocery/frozen corridor, heading down
            make_char(0.19, 0.25,  1.0, (80, 140, 200)),
            # Customer 2 — frozen/deli corridor, heading up
            make_char(0.41, 0.70, -1.0, (200, 100, 80)),
            # Customer 3 — deli/tech corridor, heading down
            make_char(0.66, 0.40,  1.0, (140, 200, 100)),
            # Employee — grocery/frozen corridor (opposite side to C1), heading up
            make_char(0.19, 0.80, -1.0, (60, 160, 80), hat_col=(30, 100, 50), label="EMP", carrying=True),
            # Trainee — frozen/deli corridor, heading down (behind C2)
            make_char(0.41, 0.30,  1.0, (220, 200, 60), hat_col=(180, 160, 20), label="TRN"),
            # Cashier — near register, tiny vertical sway
            make_char(0.91, 0.82,  0.3, (80, 100, 210), hat_col=(40, 60, 160), label="CSH"),
        ]
        # Per-character: (y_min_frac, y_max_frac, speed_px_per_s)
        # y_min/max are fractions of inset height; keep away from shelf top sign band (~0.18)
        # and from the register/mat zone at the bottom (~0.88)
        self._char_cfg = [
            (0.20, 0.86, 70),   # C1
            (0.20, 0.86, 52),   # C2
            (0.20, 0.86, 60),   # C3
            (0.20, 0.86, 58),   # EMP
            (0.20, 0.86, 50),   # TRN
            (0.78, 0.88,  9),   # CSH — tiny sway only
        ]

    def draw_bytebit_logo(self, x: int, y: int, size: int = 80):
        """Pixel-art grocery store logo with storefront, awning, cart symbol, and produce."""
        s = size
        ps = max(2, s // 20)   # pixel unit size

        # bob animation
        bob = int(math.sin(self.auth_time * 2.2) * 4)
        y += bob

        # --- glow halo ---
        glow_r = s // 2 + 20
        glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        for radius in range(glow_r, 0, -3):
            alpha = max(0, int(55 * (1 - radius / glow_r)))
            pygame.draw.rect(glow_surf, (*ACCENT, alpha),
                             (glow_r - radius, glow_r - radius, radius * 2, radius * 2))
        self.screen.blit(glow_surf, (x + s // 2 - glow_r, y + s // 2 - glow_r))

        def px(gx, gy, color, w=1, h=1):
            pygame.draw.rect(self.screen, color,
                             (x + gx * ps, y + gy * ps, ps * w, ps * h))

        cols = s // ps
        rows = s // ps

        # --- background ---
        for gx in range(cols):
            for gy in range(rows):
                px(gx, gy, (20, 28, 52))

        # --- roof structure (triangular pixel peak) ---
        peak_col = (60, 80, 140)
        for gx in range(cols):
            px(gx, 0, peak_col)
            px(gx, 1, peak_col)
        # chimney-like peak centre
        mid = cols // 2
        for gy in range(-2, 2):
            pass  # skip, keep flat

        # --- awning: red/white striped ---
        awning_rows = 3
        for gy in range(2, 2 + awning_rows):
            for gx in range(cols):
                stripe_col = (210, 50, 50) if gx % 2 == 0 else (240, 240, 240)
                px(gx, gy, stripe_col)

        # awning scalloped bottom edge (alternating drop pixels)
        scallop_y = 2 + awning_rows
        for gx in range(cols):
            drop_col = (210, 50, 50) if gx % 2 == 0 else (180, 30, 30)
            px(gx, scallop_y, drop_col)

        # --- store facade (wall) ---
        wall_top = scallop_y + 1
        wall_bot = rows - 3
        wall_col = (235, 235, 220)
        for gx in range(cols):
            for gy in range(wall_top, wall_bot):
                px(gx, gy, wall_col)

        # --- sign strip above door ---
        sign_y = wall_top
        sign_h = 2
        sign_col = (40, 120, 200)
        for gx in range(1, cols - 1):
            for gy in range(sign_y, sign_y + sign_h):
                px(gx, gy, sign_col)

        # --- windows (left and right of door) ---
        win_w, win_h = 3, 3
        win_top = wall_top + sign_h + 1
        # flicker
        flicker = int(math.sin(self.auth_time * 4.0) * 15)
        win_col = (min(255, 190 + flicker), min(255, 230 + flicker), min(255, 140 + flicker))
        win_frame = (80, 60, 40)

        left_win_x = 1
        right_win_x = cols - 1 - win_w
        for wx in (left_win_x, right_win_x):
            # frame
            for gx in range(wx - 1, wx + win_w + 1):
                for gy in range(win_top - 1, win_top + win_h + 1):
                    px(gx, gy, win_frame)
            # glass
            for gx in range(wx, wx + win_w):
                for gy in range(win_top, win_top + win_h):
                    px(gx, gy, win_col)
            # window cross divider
            mid_wx = wx + win_w // 2
            mid_wy = win_top + win_h // 2
            for gx in range(wx, wx + win_w):
                px(gx, mid_wy, win_frame)
            for gy in range(win_top, win_top + win_h):
                px(mid_wx, gy, win_frame)

        # --- door (centre) ---
        door_w = max(3, cols // 4)
        door_h = wall_bot - win_top - sign_h
        door_x = mid - door_w // 2
        door_top = wall_bot - door_h
        door_col = (100, 140, 200)
        door_frame_col = (80, 60, 40)
        for gx in range(door_x - 1, door_x + door_w + 1):
            for gy in range(door_top - 1, wall_bot):
                px(gx, gy, door_frame_col)
        for gx in range(door_x, door_x + door_w):
            for gy in range(door_top, wall_bot):
                px(gx, gy, door_col)
        # door handle
        px(door_x + door_w - 1, door_top + door_h // 2, (230, 200, 60))

        # --- ground / step ---
        step_col = (160, 160, 150)
        for gx in range(cols):
            for gy in range(wall_bot, rows):
                px(gx, gy, step_col)

        # --- mini shopping cart icon (bottom-left corner) ---
        cart_x = 0
        cart_y = rows - 3
        # cart body pixel outline
        cart_col = (60, 180, 100)
        px(cart_x,     cart_y,     cart_col)
        px(cart_x + 1, cart_y,     cart_col)
        px(cart_x + 2, cart_y,     cart_col)
        px(cart_x + 2, cart_y + 1, cart_col)
        px(cart_x,     cart_y + 1, cart_col)
        # wheels
        px(cart_x,     cart_y + 2, (40, 40, 40))
        px(cart_x + 2, cart_y + 2, (40, 40, 40))

        # --- mini produce dots (top-right corner) ---
        produce_colors = [(232, 86, 86), (245, 180, 80), (100, 200, 80)]
        for pi, pc in enumerate(produce_colors):
            px(cols - 3 + pi, rows - 3, pc)

    def draw_auth(self):
        # ---------- retro pixel background ----------
        # scanline overlay
        scan_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        for sy in range(0, HEIGHT, 4):
            pygame.draw.line(scan_surf, (0, 0, 0, 28), (0, sy), (WIDTH, sy))
        self.screen.blit(scan_surf, (0, 0))

        # floating pixel particles (retro sparkles)
        particle_colors = [ACCENT, ACCENT_2, (255, 213, 79), (180, 220, 255)]
        for p in self.pixel_particles:
            age_frac = p[5] / max(0.001, p[6])
            alpha = int(200 * (1 - abs(age_frac * 2 - 1)))  # fade in and out
            c = particle_colors[p[3] % len(particle_colors)]
            ps = p[2]
            psurf = pygame.Surface((ps, ps), pygame.SRCALPHA)
            psurf.fill((*c, alpha))
            self.screen.blit(psurf, (int(p[0]), int(p[1])))

        # ---------- left login card ----------
        card = pygame.Rect(60, 80, 560, 720)
        # pixel-border card (hard edges, no radius)
        # shadow
        shadow_surf = pygame.Surface((card.width + 8, card.height + 8), pygame.SRCALPHA)
        shadow_surf.fill((0, 0, 0, 80))
        self.screen.blit(shadow_surf, (card.x + 4, card.y + 8))
        # card body
        pygame.draw.rect(self.screen, (22, 28, 50), card)
        # pixel border — 3px solid ACCENT
        pygame.draw.rect(self.screen, ACCENT, card, 3)
        # corner accent squares (retro corner pixels)
        corner_s = 8
        for cx, cy in [(card.x, card.y), (card.right - corner_s, card.y),
                       (card.x, card.bottom - corner_s), (card.right - corner_s, card.bottom - corner_s)]:
            pygame.draw.rect(self.screen, ACCENT_2, (cx, cy, corner_s, corner_s))

        # ---------- logo (animated, bobbing) ----------
        logo_size = 80
        logo_x = card.x + card.width // 2 - logo_size // 2
        logo_y = card.y + 30
        self.draw_bytebit_logo(logo_x, logo_y, size=logo_size)

        # ---------- BYTEBIT MARKET title — large pixelated look ----------
        # shadow offset text for depth
        title = "BYTEBIT"
        subtitle_word = "MARKET"
        title_size = 58
        sub_size = 44

        title_y = logo_y + logo_size + 22
        # pulsing glow color
        pulse = (math.sin(self.auth_time * 1.8) + 1) / 2   # 0..1
        glow_r = int(lerp(160, 220, pulse))
        glow_g = int(lerp(210, 255, pulse))
        glow_b = int(lerp(100, 160, pulse))
        title_color = (glow_r, glow_g, glow_b)

        # drop shadow
        draw_text(self.screen, title,
                  (card.centerx + 3, title_y + 3),
                  size=title_size, bold=True, color=(0, 0, 0), center=True)
        draw_text(self.screen, title,
                  (card.centerx, title_y),
                  size=title_size, bold=True, color=title_color, center=True)

        sub_y = title_y + title_size + 4
        draw_text(self.screen, subtitle_word,
                  (card.centerx + 2, sub_y + 2),
                  size=sub_size, bold=True, color=(0, 0, 0), center=True)
        draw_text(self.screen, subtitle_word,
                  (card.centerx, sub_y),
                  size=sub_size, bold=True, color=ACCENT_2, center=True)

        # tagline
        tag_y = sub_y + sub_size + 8
        draw_text(self.screen, "[ MODERN SUPERMARKET SIMULATOR ]",
                  (card.centerx, tag_y),
                  size=14, bold=True, color=TEXT_MUTED, center=True)

        # ---------- pixel divider line ----------
        div_y = tag_y + 24
        for dx in range(0, card.width - 40, 8):
            col = ACCENT if (dx // 8) % 2 == 0 else ACCENT_2
            pygame.draw.rect(self.screen, col, (card.x + 20 + dx, div_y, 6, 3))

        # ---------- input fields (repositioned below divider) ----------
        field_top = div_y + 18
        field_gap = 68
        for i, key in enumerate(["username", "email", "password"]):
            inp = self.auth_inputs[key]
            inp.rect.topleft = (card.x + 30, field_top + i * field_gap)
            inp.rect.width = card.width - 60
            inp.draw(self.screen)
            # thick pixel border around each field (3px, accent when active)
            border_col = ACCENT if inp.active else (80, 100, 160)
            pygame.draw.rect(self.screen, border_col, inp.rect, 3)

        # ---------- buttons (repositioned) ----------
        btn_y = field_top + 3 * field_gap + 10
        btn_w = (card.width - 80) // 2
        self.auth_buttons[0].base_rect = pygame.Rect(card.x + 30, btn_y, btn_w, 52)
        self.auth_buttons[1].base_rect = pygame.Rect(card.x + 50 + btn_w, btn_y, btn_w, 52)

        for i, btn in enumerate(self.auth_buttons):
            # pixel-style button shake on hover
            shake_x = int(math.sin(self.auth_time * 6 + i * 1.5) * 1.5 * btn.hover_t)
            shake_y = int(math.cos(self.auth_time * 5 + i) * 1.5 * btn.hover_t)
            orig = btn.base_rect.topleft
            btn.base_rect.x += shake_x
            btn.base_rect.y += shake_y
            btn.draw(self.screen)
            btn.base_rect.topleft = orig

        # ---------- right preview panel ----------
        preview = pygame.Rect(660, 80, 720, 720)
        # pixel border
        shadow_surf2 = pygame.Surface((preview.width + 8, preview.height + 8), pygame.SRCALPHA)
        shadow_surf2.fill((0, 0, 0, 80))
        self.screen.blit(shadow_surf2, (preview.x + 4, preview.y + 8))
        pygame.draw.rect(self.screen, (22, 28, 50), preview)
        pygame.draw.rect(self.screen, ACCENT_2, preview, 3)
        for cx, cy in [(preview.x, preview.y), (preview.right - corner_s, preview.y),
                       (preview.x, preview.bottom - corner_s), (preview.right - corner_s, preview.bottom - corner_s)]:
            pygame.draw.rect(self.screen, ACCENT, (cx, cy, corner_s, corner_s))

        self.draw_store_preview(preview)

        # blinking retro prompt at bottom of right panel
        if int(self.auth_time * 1.6) % 2 == 0:
            draw_text(self.screen, ">> PRESS LOG IN / REGISTER TO START <<",
                      (preview.centerx, preview.bottom - 58),
                      size=15, bold=True, color=(0, 0, 0), center=True)

    def draw_store_preview(self, rect: pygame.Rect):
        """Final animated store preview: windows, signs, detailed fridges, stacked carts."""
        t = self.auth_time
        inset = rect.inflate(-20, -20)
        iw, ih = inset.width, inset.height
        ix, iy = inset.x, inset.y

        # ── time-of-day cycle (120 s = full shift dawn→dusk) ──────────────
        CYCLE = 120.0
        day_frac = (t % CYCLE) / CYCLE          # 0=dawn … 1=dusk/night

        def sky_col(frac):
            # dawn(0) orange → morning(0.15) gold → day(0.35) blue
            # → afternoon(0.6) warm → dusk(0.8) orange-red → night(1) dark
            stops = [
                (0.00, (255, 160,  80)),   # dawn
                (0.12, (255, 210, 120)),   # sunrise
                (0.30, (130, 190, 255)),   # morning blue
                (0.55, (100, 170, 240)),   # midday
                (0.72, (255, 180,  90)),   # afternoon
                (0.85, (220,  90,  50)),   # dusk
                (1.00, ( 18,  20,  45)),   # night
            ]
            for i in range(len(stops) - 1):
                f0, c0 = stops[i]
                f1, c1 = stops[i + 1]
                if f0 <= frac <= f1:
                    local_t = (frac - f0) / (f1 - f0)
                    return tuple(int(lerp(c0[j], c1[j], local_t)) for j in range(3))
            return stops[-1][1]

        sky = sky_col(day_frac)

        # ── back wall (fills inset before anything else) ────────────────
        pygame.draw.rect(self.screen, (210, 205, 195), inset)

        # ── windows row at top of store ────────────────────────────────
        WIN_ROW_H = 52
        win_zone = pygame.Rect(ix, iy, iw, WIN_ROW_H)
        pygame.draw.rect(self.screen, (50, 55, 70), win_zone)   # wall header

        # 6 evenly spaced windows
        n_wins = 6
        win_w = 68
        win_h = 38
        win_gap = (iw - n_wins * win_w) // (n_wins + 1)
        for wi in range(n_wins):
            wx = ix + win_gap + wi * (win_w + win_gap)
            wy = iy + 7
            # outer frame
            pygame.draw.rect(self.screen, (80, 75, 65), (wx - 3, wy - 3, win_w + 6, win_h + 6), border_radius=4)
            # sky gradient in window
            for row in range(win_h):
                row_frac = row / max(1, win_h - 1)
                base = sky
                horizon = tuple(min(255, v + 30) for v in sky)
                rc = tuple(int(lerp(base[j], horizon[j], row_frac)) for j in range(3))
                pygame.draw.line(self.screen, rc, (wx, wy + row), (wx + win_w - 1, wy + row))
            # sun or moon
            sun_x = wx + int(win_w * 0.5 + math.sin(day_frac * math.pi * 2) * win_w * 0.35)
            sun_y = wy + int(win_h * 0.5 - math.cos(day_frac * math.pi * 2) * win_h * 0.32)
            if day_frac < 0.82:   # sun
                sun_col = (255, 240, 100) if day_frac < 0.65 else (255, 160, 60)
                pygame.draw.circle(self.screen, sun_col, (sun_x, sun_y), 6)
                # rays at midday
                if 0.3 < day_frac < 0.6:
                    for ang in range(0, 360, 45):
                        rx = int(math.cos(math.radians(ang)) * 9)
                        ry = int(math.sin(math.radians(ang)) * 9)
                        pygame.draw.line(self.screen, (255, 230, 80),
                                         (sun_x, sun_y), (sun_x + rx, sun_y + ry), 1)
            else:                 # moon
                pygame.draw.circle(self.screen, (230, 230, 210), (sun_x, sun_y), 5)
                pygame.draw.circle(self.screen, sky, (sun_x + 2, sun_y - 1), 4)  # crescent
            # window frame cross-bar
            pygame.draw.line(self.screen, (80, 75, 65), (wx + win_w // 2, wy), (wx + win_w // 2, wy + win_h), 1)
            pygame.draw.line(self.screen, (80, 75, 65), (wx, wy + win_h // 2), (wx + win_w, wy + win_h // 2), 1)
            # window sill
            pygame.draw.rect(self.screen, (100, 95, 85), (wx - 4, wy + win_h, win_w + 8, 5), border_radius=2)

        # time-of-day label on header bar
        hour_labels = ["DAWN","MORNING","MIDDAY","AFTERNOON","DUSK","NIGHT"]
        hour_idx = min(5, int(day_frac * 6))
        tod_lbl = get_font(9, bold=True).render(hour_labels[hour_idx], True, (200, 210, 220))
        self.screen.blit(tod_lbl, (ix + iw - tod_lbl.get_width() - 6, iy + WIN_ROW_H - 14))

        # ── floor (tile grid, extends to bottom) ──────────────────────
        floor_y = iy + WIN_ROW_H
        pygame.draw.rect(self.screen, FLOOR, (ix, floor_y, iw, ih - WIN_ROW_H))
        tile = 28
        for gx in range(ix, inset.right, tile):
            pygame.draw.line(self.screen, AISLE, (gx, floor_y), (gx, inset.bottom), 1)
        for gy in range(floor_y, inset.bottom, tile):
            pygame.draw.line(self.screen, AISLE, (ix, gy), (inset.right, gy), 1)

        # ── overhead sign helper ────────────────────────────────────
        font_sec  = get_font(10, bold=True)
        font_sign = get_font(11, bold=True)

        def draw_overhead_sign(cx, sign_y, text, bg_col, text_col=(255, 245, 200)):
            lbl = font_sign.render(text, True, text_col)
            pad = 8
            sw, sh = lbl.get_width() + pad * 2, lbl.get_height() + 6
            sx = cx - sw // 2
            # hanging wire
            pygame.draw.line(self.screen, (120, 120, 130), (cx, sign_y - 10), (cx, sign_y), 1)
            # sign body
            pygame.draw.rect(self.screen, bg_col, (sx, sign_y, sw, sh), border_radius=4)
            pygame.draw.rect(self.screen, tuple(max(0, v - 40) for v in bg_col),
                             (sx, sign_y, sw, sh), 2, border_radius=4)
            self.screen.blit(lbl, (sx + pad, sign_y + 3))

        # ── section layout ───────────────────────────────────────────────
        # Sections spread at 9/29/53/79 % of inset width.
        # Corridors (chars at 0.19 / 0.41 / 0.66 / 0.91) are each ≥ 40 px clear
        # so characters walk freely without touching any shelf edge.
        SEC_GROCERY_CX = ix + int(iw * 0.09)
        SEC_FROZEN_CX  = ix + int(iw * 0.29)
        SEC_DELI_CX    = ix + int(iw * 0.53)
        SEC_TECH_CX    = ix + int(iw * 0.79)
        SIGN_Y         = floor_y + 4
        # Shelves stop well above the entrance mat / register area
        SHELF_STOP_Y   = inset.bottom - 120

        draw_overhead_sign(SEC_GROCERY_CX, SIGN_Y, "GROCERY",  (60, 120, 60))
        draw_overhead_sign(SEC_FROZEN_CX,  SIGN_Y, "FROZEN",   (30, 90, 160))
        draw_overhead_sign(SEC_DELI_CX,    SIGN_Y, "DELI",     (160, 80, 40))
        draw_overhead_sign(SEC_TECH_CX,    SIGN_Y, "TECH",     (40, 40, 100))

        CONTENT_Y = floor_y + 32   # everything below signs starts here

        # ── helper: shelf unit ─────────────────────────────────────────
        def draw_shelf_unit(sx, sy, sw, sh, products, layers=3):
            pygame.draw.rect(self.screen, WOOD, (sx, sy, sw, sh), border_radius=5)
            # side shadow strip
            pygame.draw.rect(self.screen, tuple(max(0, v - 25) for v in WOOD),
                             (sx + sw - 6, sy, 6, sh), border_radius=5)
            layer_h = sh // (layers + 1)
            for li in range(layers):
                plank_y = sy + layer_h * (li + 1)
                pygame.draw.rect(self.screen, SHELF, (sx + 4, plank_y, sw - 10, 8), border_radius=2)
                # underside shadow
                pygame.draw.rect(self.screen, tuple(max(0, v - 20) for v in SHELF),
                                 (sx + 4, plank_y + 7, sw - 10, 2))
                slot_w = max(1, (sw - 12) // max(1, len(products)))
                for pi, (pcol, _) in enumerate(products):
                    shimmer = int(math.sin(t * 2.0 + sx * 0.02 + pi + li) * 8)
                    c = tuple(min(255, v + shimmer) for v in pcol)
                    pygame.draw.rect(self.screen, c,
                                     (sx + 6 + pi * slot_w, plank_y - 19, slot_w - 1, 19), border_radius=2)
                    # price tag
                    pygame.draw.rect(self.screen, (255, 250, 180),
                                     (sx + 6 + pi * slot_w, plank_y - 3, slot_w - 1, 3))

        # ── SECTION 1: Grocery — single shelf unit ─────────────────────
        grocery_products = [
            ((245, 180, 80), "chips"), ((195, 225, 255), "milk"),
            ((214, 169, 111), "bread"), ((232, 86, 86), "apple"),
        ]
        shelf_w = 52
        grocery_h = SHELF_STOP_Y - CONTENT_Y
        # ONE shelf only — centred on SEC_GROCERY_CX
        draw_shelf_unit(SEC_GROCERY_CX - shelf_w // 2, CONTENT_Y, shelf_w, grocery_h, grocery_products, layers=4)

        # ── SECTION 2: Frozen refrigerators ────────────────────────────
        frozen_defs = [
            ((160, 210, 255), "Frz.Fruit"),
            ((180, 240, 200), "Frz.Veg"),
            ((255, 200, 180), "Frz.Prot"),
        ]
        fridge_w, fridge_h = 46, SHELF_STOP_Y - CONTENT_Y
        fridge_gap = 5
        frozen_x0 = SEC_FROZEN_CX - (len(frozen_defs) * (fridge_w + fridge_gap)) // 2 + fridge_gap
        for fi, (fcol, fname) in enumerate(frozen_defs):
            fx = frozen_x0 + fi * (fridge_w + fridge_gap)
            fy = CONTENT_Y

            # ── outer casing ──────────────────────────────────────────
            CASE_COL  = (44, 74, 108)
            CASE_DARK = (30, 52, 80)
            pygame.draw.rect(self.screen, CASE_COL, (fx, fy, fridge_w, fridge_h), border_radius=5)
            # left/right edge shading
            pygame.draw.rect(self.screen, CASE_DARK, (fx, fy, 5, fridge_h), border_radius=5)
            pygame.draw.rect(self.screen, CASE_DARK, (fx + fridge_w - 5, fy, 5, fridge_h), border_radius=5)
            # top cap
            pygame.draw.rect(self.screen, (60, 100, 145), (fx, fy, fridge_w, 8), border_radius=5)
            # bottom kick plate
            pygame.draw.rect(self.screen, (30, 50, 75), (fx, fy + fridge_h - 8, fridge_w, 8), border_radius=3)

            # ── glass door panel — lighter tint so items show clearly ──
            GLASS_MARGIN = 6
            gx2, gy2 = fx + GLASS_MARGIN, fy + 10
            gw2, gh2 = fridge_w - GLASS_MARGIN * 2, fridge_h - 22
            # glass base — semi-transparent pale blue (not too dark)
            glass_surf = pygame.Surface((gw2, gh2), pygame.SRCALPHA)
            glass_surf.fill((200, 235, 255, 55))
            self.screen.blit(glass_surf, (gx2, gy2))
            # glass door frame
            pygame.draw.rect(self.screen, (55, 90, 130), (gx2, gy2, gw2, gh2), 2, border_radius=3)

            # ── products CLEARLY visible through glass ──────────────────
            item_rows = 4
            row_h = (gh2 - 8) // item_rows
            for ri in range(item_rows):
                ry2 = gy2 + 4 + ri * row_h
                # shelf plank inside fridge
                pygame.draw.rect(self.screen, (60, 100, 140), (gx2 + 2, ry2 + row_h - 4, gw2 - 4, 4))
                # item block — bright, saturated color
                shimmer = int(math.sin(t * 1.8 + fi * 2 + ri) * 6)
                ic = tuple(min(255, v + shimmer) for v in fcol)
                pygame.draw.rect(self.screen, ic, (gx2 + 3, ry2 + 2, gw2 - 6, row_h - 8), border_radius=2)
                # item outline for clarity
                pygame.draw.rect(self.screen, tuple(max(0, v - 40) for v in ic),
                                 (gx2 + 3, ry2 + 2, gw2 - 6, row_h - 8), 1, border_radius=2)
                # price sticker
                pygame.draw.rect(self.screen, (255, 250, 180), (gx2 + 3, ry2 + row_h - 9, gw2 - 6, 4))
                # tiny label
                item_lbl = font_sec.render(fname[:4], True, (40, 40, 60))
                self.screen.blit(item_lbl, (gx2 + max(1, gw2 // 2 - item_lbl.get_width() // 2), ry2 + 3))

            # ── door handle (vertical bar, right side) ──────────────
            hx = fx + fridge_w - GLASS_MARGIN - 4
            pygame.draw.rect(self.screen, (180, 190, 200), (hx, fy + fridge_h // 2 - 20, 5, 40), border_radius=3)
            for screw_y in [fy + fridge_h // 2 - 20, fy + fridge_h // 2 + 18]:
                pygame.draw.circle(self.screen, (140, 150, 160), (hx + 2, screw_y), 2)

            # ── temperature display (LED panel top) ─────────────────
            led_x, led_y = fx + 8, fy + 1
            pygame.draw.rect(self.screen, (10, 20, 35), (led_x, led_y, fridge_w - 16, 7), border_radius=2)
            temp_glow = int((math.sin(t * 2.0 + fi) + 1) * 4)
            pygame.draw.rect(self.screen, (0, min(255, 180 + temp_glow), 80),
                             (led_x + 2, led_y + 1, 18, 5), border_radius=1)

        # ── SECTION 3: Deli counter ─────────────────────────────────────
        deli_w  = 78
        deli_x0 = SEC_DELI_CX - deli_w // 2
        # back shelf tiers — stop at SHELF_STOP_Y
        BACK_H = SHELF_STOP_Y - CONTENT_Y
        back_shelf_col = (170, 140, 100)
        pygame.draw.rect(self.screen, back_shelf_col, (deli_x0, CONTENT_Y, deli_w, BACK_H), border_radius=4)
        deli_items = [
            ((214, 169, 111), "Bread"),
            ((255, 200, 120), "Donut"),
            ((210, 140, 160), "Cake"),
        ]
        tier_rows = 4
        tier_h = BACK_H // (tier_rows + 1)
        for tr in range(tier_rows):
            ty2 = CONTENT_Y + tier_h * (tr + 1)
            pygame.draw.rect(self.screen, (200, 170, 125), (deli_x0 + 3, ty2, deli_w - 6, 5), border_radius=2)
            for tpi in range(3):
                tcol, _ = deli_items[tpi % len(deli_items)]
                shimmer = int(math.sin(t * 1.5 + tr + tpi) * 8)
                tc = tuple(min(255, v + shimmer) for v in tcol)
                pygame.draw.ellipse(self.screen, tc,
                                    (deli_x0 + 6 + tpi * 22, ty2 - 14, 20, 13))
        # glass display counter (front)
        COUNTER_H = 55
        counter_y2 = CONTENT_Y + BACK_H - COUNTER_H - 2
        pygame.draw.rect(self.screen, (160, 130, 95), (deli_x0, counter_y2 + 20, deli_w, COUNTER_H), border_radius=5)
        # glass front panel
        pygame.draw.rect(self.screen, (170, 210, 245), (deli_x0 + 2, counter_y2, deli_w - 4, 24), border_radius=3)
        pygame.draw.rect(self.screen, (120, 175, 220), (deli_x0 + 2, counter_y2, deli_w - 4, 24), 2, border_radius=3)
        # items inside glass case
        for di, (dcol, dname) in enumerate(deli_items):
            ddx = deli_x0 + 6 + di * 22
            pygame.draw.ellipse(self.screen, dcol, (ddx, counter_y2 + 5, 20, 13))
            dlbl = get_font(8).render(dname, True, (70, 50, 30))
            self.screen.blit(dlbl, (ddx + 10 - dlbl.get_width() // 2, counter_y2 + 20))
        # counter top surface
        pygame.draw.rect(self.screen, (200, 175, 130), (deli_x0, counter_y2 + 18, deli_w, 6), border_radius=2)

        # ── SECTION 4: Tech display aisles ────────────────────────────
        # Three shelf aisles, each stocking all three device types stacked vertically.
        # The whole section is shorter than the other sections (stops higher up).
        TECH_STOP_Y  = SHELF_STOP_Y - 80        # tech ends noticeably shorter
        tech_aisle_h = TECH_STOP_Y - CONTENT_Y

        # Aisle shelf definitions: 3 aisles, each with phone + laptop + router stacked
        tech_aisles = [
            (-68, "AISLE A"),
            (  0, "AISLE B"),
            ( 68, "AISLE C"),
        ]
        # Device types shown on every shelf aisle (stacked top-to-bottom)
        tech_device_rows = [
            # (body_col,         screen_col,       name,    w,  h)
            ((55,  55,  68),  (90,  170, 255), "PHONE",  13, 22),
            ((38,  38,  48),  (130, 215, 255), "LAPTOP", 36, 24),
            ((175, 175, 195), (70,  190, 255), "ROUTER", 26, 17),
        ]

        for ai, (ax_off, alabel) in enumerate(tech_aisles):
            # shelf unit background
            shelf_ax = SEC_TECH_CX + ax_off
            shelf_aw = 52
            pygame.draw.rect(self.screen, WOOD,
                             (shelf_ax - shelf_aw // 2, CONTENT_Y, shelf_aw, tech_aisle_h),
                             border_radius=4)
            # side shadow
            pygame.draw.rect(self.screen, tuple(max(0, v - 25) for v in WOOD),
                             (shelf_ax + shelf_aw // 2 - 6, CONTENT_Y, 6, tech_aisle_h),
                             border_radius=4)

            # evenly distribute device rows along the shelf height
            num_rows = len(tech_device_rows)
            row_zone_h = tech_aisle_h // (num_rows + 1)

            for ri, (bcol, scol, dname, dw, dh) in enumerate(tech_device_rows):
                # shelf plank between rows
                plank_y = CONTENT_Y + row_zone_h * (ri + 1)
                pygame.draw.rect(self.screen, SHELF,
                                 (shelf_ax - shelf_aw // 2 + 3, plank_y, shelf_aw - 6, 7),
                                 border_radius=2)
                pygame.draw.rect(self.screen, tuple(max(0, v - 20) for v in SHELF),
                                 (shelf_ax - shelf_aw // 2 + 3, plank_y + 6, shelf_aw - 6, 2))

                # device centred above its plank
                tx2 = shelf_ax - dw // 2
                ty2 = plank_y - dh - 4

                sglow = int((math.sin(t * 2.8 + ai * 1.1 + ri * 0.9) + 1) * 12)

                # glow halo
                halo_surf = pygame.Surface((dw + 10, dh + 10), pygame.SRCALPHA)
                pygame.draw.rect(halo_surf, (*scol, 35 + sglow),
                                 halo_surf.get_rect(), border_radius=5)
                self.screen.blit(halo_surf, (tx2 - 5, ty2 - 5))

                # device body
                pygame.draw.rect(self.screen, bcol, (tx2, ty2, dw, dh), border_radius=3)
                # screen bezel
                pygame.draw.rect(self.screen, (20, 20, 30),
                                 (tx2 + 2, ty2 + 2, dw - 4, dh - 5), border_radius=2)
                # screen glow
                sc2 = tuple(min(255, v + sglow) for v in scol)
                pygame.draw.rect(self.screen, sc2,
                                 (tx2 + 3, ty2 + 3, dw - 6, dh - 8), border_radius=2)
                # UI bars on screen
                for bar_i in range(2):
                    bar_y2 = ty2 + 5 + bar_i * 5
                    bar_col = (255, 255, 255) if (int(t * 2 + bar_i + ri) % 4 < 2) else (180, 220, 255)
                    pygame.draw.rect(self.screen, bar_col,
                                     (tx2 + 4, bar_y2, dw - 10, 2), border_radius=1)
                # device outline
                pygame.draw.rect(self.screen, tuple(max(0, v - 20) for v in bcol),
                                 (tx2, ty2, dw, dh), 1, border_radius=3)
                # tiny device name label on plank
                dlbl = font_sec.render(dname, True, (190, 200, 220))
                self.screen.blit(dlbl, (tx2 + dw // 2 - dlbl.get_width() // 2, plank_y + 8))

            # price tag strip at the very bottom of each aisle
            pygame.draw.rect(self.screen, (255, 250, 180),
                             (shelf_ax - shelf_aw // 2 + 3, TECH_STOP_Y - 10, shelf_aw - 6, 6),
                             border_radius=2)

        # ── checkout counter ───────────────────────────────────────────
        counter_rect = pygame.Rect(inset.right - 165, inset.bottom - 120, 130, 78)
        pygame.draw.rect(self.screen, REGISTER, counter_rect, border_radius=7)
        pygame.draw.rect(self.screen, (55, 65, 75), counter_rect, 2, border_radius=7)
        # register screen
        scr_glow = int((math.sin(t * 3.0) + 1) * 18)
        pygame.draw.rect(self.screen, (0, min(255, 150 + scr_glow), min(255, 55 + scr_glow)),
                         (counter_rect.x + 7, counter_rect.y + 7, 44, 28), border_radius=3)
        # scanner laser line sweep
        laser_y = counter_rect.y + 42 + int(math.sin(t * 6) * 5)
        pygame.draw.line(self.screen, (255, 60, 60),
                         (counter_rect.x + 54, laser_y),
                         (counter_rect.right - 7, laser_y), 2)
        # conveyor belt stripes
        belt_x = counter_rect.x + 54
        for stripe in range(5):
            sx2 = belt_x + stripe * 13 + int(t * 18) % 13
            pygame.draw.line(self.screen, (70, 75, 80),
                             (sx2, counter_rect.y + 36), (sx2, counter_rect.y + 60), 2)

        # ── high-quality character renderer ────────────────────────────
        def draw_person_walk(px_pos, py_pos, body_color, hat_color, label,
                             carrying, walk_phase, facing_down, paused,
                             skin_tone=(224, 190, 155), hair_color=(60, 40, 25),
                             pant_color=(45, 50, 75), shoe_color=(32, 22, 16)):
            px_pos, py_pos = int(px_pos), int(py_pos)

            # smooth vertical bob (two bobs per stride)
            bob = 0 if paused else int(math.sin(walk_phase * 2) * 2.2)
            swing = 0.0 if paused else math.sin(walk_phase)
            a_swing = 0.0 if paused else math.sin(walk_phase + math.pi)  # arms opposite legs

            # ── soft ground shadow (oval, fades toward edges) ──────────
            shadow_surf = pygame.Surface((34, 10), pygame.SRCALPHA)
            for sx in range(17):
                alpha = int(90 * (1 - (sx / 17) ** 1.6))
                pygame.draw.line(shadow_surf, (0, 0, 0, alpha),
                                 (17 - sx, 5), (17 + sx, 5), 1)
            self.screen.blit(shadow_surf, (px_pos - 17, py_pos + 22))

            # ── leg geometry (two tapered legs with depth cue) ─────────
            # back leg drawn first (slightly darker, offset behind)
            leg_pairs = [(-4, swing), (3, -swing)]  # (x_off, y_swing)
            for li, (lx, lsw) in enumerate(leg_pairs):
                depth = li == 0  # first = back leg
                ly_extra = int(lsw * 8)
                leg_shade = tuple(max(0, v - (18 if depth else 0)) for v in pant_color)
                # upper leg (thigh)
                pygame.draw.rect(self.screen, leg_shade,
                                 (px_pos + lx - 1, py_pos + 8 + bob, 6, 7), border_radius=3)
                # lower leg (shin — slightly narrower)
                pygame.draw.rect(self.screen, leg_shade,
                                 (px_pos + lx, py_pos + 14 + bob + ly_extra, 5, 6), border_radius=2)
                # shoe — rounded, with sole highlight
                shoe_x = px_pos + lx - (1 if facing_down else 0)
                shoe_y = py_pos + 19 + bob + ly_extra
                pygame.draw.rect(self.screen, shoe_color,
                                 (shoe_x, shoe_y, 8, 4), border_radius=2)
                pygame.draw.line(self.screen,
                                 tuple(min(255, v + 22) for v in shoe_color),
                                 (shoe_x + 1, shoe_y + 1), (shoe_x + 6, shoe_y + 1), 1)

            # ── torso with fabric shading ───────────────────────────────
            torso_x, torso_y = px_pos - 8, py_pos - 8 + bob
            torso_w, torso_h = 16, 17

            # base shirt
            pygame.draw.rect(self.screen, body_color,
                             (torso_x, torso_y, torso_w, torso_h), border_radius=4)
            # left-side shadow strip (depth)
            shadow_col = tuple(max(0, v - 38) for v in body_color)
            pygame.draw.rect(self.screen, shadow_col,
                             (torso_x + torso_w - 5, torso_y + 2, 4, torso_h - 4), border_radius=2)
            # centre highlight (fabric sheen)
            hi_col = tuple(min(255, v + 42) for v in body_color)
            pygame.draw.rect(self.screen, hi_col,
                             (torso_x + 2, torso_y + 2, 4, 8), border_radius=2)
            # collar line
            collar_col = tuple(min(255, v + 60) for v in body_color)
            pygame.draw.line(self.screen, collar_col,
                             (torso_x + 4, torso_y + 2), (torso_x + 11, torso_y + 2), 1)

            # ── arms (swing opposite to legs) ──────────────────────────
            arm_col  = tuple(max(0, v - 22) for v in body_color)
            arm_hi   = tuple(min(255, v + 18) for v in body_color)
            skin_arm = tuple(max(0, v - 15) for v in skin_tone)
            # back arm
            bax = px_pos - 14
            bay = py_pos - 5 + int(a_swing * 7) + bob
            pygame.draw.rect(self.screen, arm_col, (bax, bay, 6, 11), border_radius=3)
            pygame.draw.rect(self.screen, arm_hi,  (bax + 1, bay + 1, 2, 5), border_radius=1)
            pygame.draw.rect(self.screen, skin_arm, (bax + 1, bay + 8, 4, 4), border_radius=2)
            # front arm
            fax = px_pos + 8
            fay = py_pos - 5 + int(-a_swing * 7) + bob
            pygame.draw.rect(self.screen, arm_col, (fax, fay, 6, 11), border_radius=3)
            pygame.draw.rect(self.screen, arm_hi,  (fax + 1, fay + 1, 2, 5), border_radius=1)
            pygame.draw.rect(self.screen, skin_arm, (fax + 1, fay + 8, 4, 4), border_radius=2)

            # ── head (circle base + detailed face) ─────────────────────
            hx, hy = px_pos, py_pos - 20 + bob
            head_r = 8

            # neck
            pygame.draw.rect(self.screen, skin_tone,
                             (hx - 3, hy + head_r - 2, 6, 5), border_radius=2)

            # head base circle
            pygame.draw.circle(self.screen, skin_tone, (hx, hy), head_r)
            # cheek blush
            pygame.draw.circle(self.screen, (235, 170, 155), (hx - 4, hy + 2), 3)
            pygame.draw.circle(self.screen, (235, 170, 155), (hx + 4, hy + 2), 3)
            # side shadow (gives roundness)
            side_shadow = pygame.Surface((head_r * 2, head_r * 2), pygame.SRCALPHA)
            pygame.draw.circle(side_shadow, (0, 0, 0, 40), (head_r * 2 - 4, head_r), head_r)
            self.screen.blit(side_shadow, (hx - head_r, hy - head_r))
            # brow ridge highlight
            pygame.draw.arc(self.screen, tuple(min(255, v + 28) for v in skin_tone),
                            (hx - 6, hy - 7, 12, 8), 0.2, math.pi - 0.2, 2)

            # eyes (whites + iris + pupil)
            eye_dir = 1 if facing_down else -1
            for ex_off in [-3, 3]:
                ex = hx + ex_off
                ey = hy - 2 + eye_dir
                # white
                pygame.draw.ellipse(self.screen, (245, 245, 250), (ex - 2, ey - 1, 4, 3))
                # iris
                pygame.draw.circle(self.screen, (60, 90, 140), (ex, ey + 1), 1)
                # pupil
                pygame.draw.circle(self.screen, (20, 18, 22), (ex, ey + 1), 0)
                # eyelid crease
                pygame.draw.line(self.screen, tuple(max(0, v - 30) for v in skin_tone),
                                 (ex - 2, ey - 1), (ex + 2, ey - 1), 1)

            # mouth (subtle smile)
            pygame.draw.arc(self.screen, (180, 100, 90),
                            (hx - 3, hy + 3, 6, 4), math.pi + 0.4, 2 * math.pi - 0.4, 1)

            # ── hair ────────────────────────────────────────────────────
            hair_hi = tuple(min(255, v + 35) for v in hair_color)
            # main hair mass on top
            pygame.draw.ellipse(self.screen, hair_color,
                                (hx - head_r, hy - head_r, head_r * 2, head_r + 2))
            # hair highlight
            pygame.draw.ellipse(self.screen, hair_hi,
                                (hx - 4, hy - head_r + 1, 5, 3))
            # side hair pieces
            pygame.draw.rect(self.screen, hair_color,
                             (hx - head_r - 1, hy - 3, 3, 6), border_radius=1)
            pygame.draw.rect(self.screen, hair_color,
                             (hx + head_r - 2, hy - 3, 3, 6), border_radius=1)

            # ── hat (employee/staff only) ────────────────────────────────
            if hat_color:
                hat_hi  = tuple(min(255, v + 35) for v in hat_color)
                hat_shd = tuple(max(0, v - 30) for v in hat_color)
                # brim
                pygame.draw.rect(self.screen, hat_shd,
                                 (hx - head_r - 2, hy - head_r + 2, head_r * 2 + 4, 5),
                                 border_radius=2)
                # crown
                pygame.draw.rect(self.screen, hat_color,
                                 (hx - 6, hy - head_r - 6, 12, 9), border_radius=3)
                # crown highlight
                pygame.draw.rect(self.screen, hat_hi,
                                 (hx - 4, hy - head_r - 5, 4, 4), border_radius=2)
                # badge pin
                pygame.draw.circle(self.screen, (255, 215, 40), (hx + 2, hy - head_r - 2), 2)
                pygame.draw.circle(self.screen, (200, 160, 20), (hx + 2, hy - head_r - 2), 2, 1)

            # ── carried stock box ────────────────────────────────────────
            if carrying:
                bx = px_pos + (10 if facing_down else -23)
                by = py_pos - 12 + bob
                # box body with subtle gradient (lighter top face)
                pygame.draw.rect(self.screen, (210, 170, 90),
                                 (bx, by, 16, 13), border_radius=2)
                # top face (lighter — catches light)
                pygame.draw.rect(self.screen, (230, 195, 115),
                                 (bx, by, 16, 4), border_radius=2)
                # side face (darker)
                pygame.draw.rect(self.screen, (160, 125, 60),
                                 (bx + 12, by + 3, 4, 10), border_radius=1)
                # tape stripe
                pygame.draw.rect(self.screen, (190, 60, 55),
                                 (bx + 1, by + 5, 14, 3))
                # box outline
                pygame.draw.rect(self.screen, (140, 105, 45),
                                 (bx, by, 16, 13), 1, border_radius=2)

            # ── role badge / name label ──────────────────────────────────
            if label:
                lsurf = font_sec.render(label, True, (220, 230, 245))
                lw = lsurf.get_width()
                # pill background
                pill = pygame.Surface((lw + 8, 13), pygame.SRCALPHA)
                pygame.draw.rect(pill, (20, 22, 38, 180), pill.get_rect(), border_radius=6)
                self.screen.blit(pill, (px_pos - lw // 2 - 4, py_pos + 24))
                self.screen.blit(lsurf, (px_pos - lw // 2, py_pos + 26))

        # draw all chars — each has unique skin tone, hair colour, pants
        CHAR_DETAILS = [
            # skin_tone,           hair_color,       pant_color,       shoe_color
            ((220, 185, 145), (55,  35, 22),  (45,  50,  80), (28, 20, 16)),  # C1 light
            ((175, 125,  85), (20,  15, 10),  (55,  40,  35), (22, 14, 10)),  # C2 medium-dark
            ((235, 200, 165), (140, 80,  30),  (35,  55,  45), (26, 18, 14)),  # C3 light-auburn
            ((160,  95,  60), (18,  12,  8),  (40,  48,  70), (24, 16, 12)),  # EMP dark
            ((210, 170, 130), (90,  55,  20),  (50,  44,  35), (30, 22, 18)),  # TRN medium
            ((225, 190, 155), (60,  45,  30),  (35,  38,  65), (25, 18, 14)),  # CSH light
        ]
        for idx, ch in enumerate(self._preview_chars):
            paused = ch["pause_t"] > 0
            facing_down = ch["vy"] >= 0
            sk, hr, pt, sh = CHAR_DETAILS[idx % len(CHAR_DETAILS)]
            draw_person_walk(
                ch["x"], ch["y"],
                ch["body_col"], ch["hat_col"], ch["label"],
                ch["carrying"], ch["walk_phase"], facing_down, paused,
                skin_tone=sk, hair_color=hr, pant_color=pt, shoe_color=sh,
            )

        # ── stacked cart corral (bottom-left corner) ────────────────
        STACK_X = ix + 8
        STACK_Y = inset.bottom - 85

        def draw_single_cart(cx, cy, item_col=None, small=False):
            """Perspective shopping cart — top-down with 3D depth cues."""
            s = 0.62 if small else 1.0
            bw = int(38 * s)   # basket width
            bh = int(24 * s)   # basket height (front face)
            dp = int(10 * s)   # depth offset (isometric back edge)

            cx, cy = int(cx), int(cy)

            # ── frame metal colour palette ───────────────────────────
            metal_mid  = (148, 158, 170)
            metal_hi   = (200, 210, 218)
            metal_shd  = (90,  98, 108)
            wheel_col  = (42,  44,  54)
            wheel_hi   = (75,  80,  92)

            # ── back (top) face of basket ───────────────────────────
            back_poly = [
                (cx + dp,      cy - dp),
                (cx + bw + dp, cy - dp),
                (cx + bw,      cy),
                (cx,           cy),
            ]
            pygame.draw.polygon(self.screen, metal_shd, back_poly)
            pygame.draw.polygon(self.screen, metal_mid, back_poly, 1)

            # ── front face of basket ────────────────────────────────
            pygame.draw.rect(self.screen, metal_mid, (cx, cy, bw, bh), border_radius=2)

            # wire grid on front face
            grid_col = tuple(max(0, v - 28) for v in metal_mid)
            for wx in range(cx + int(9*s), cx + bw, int(9*s)):
                pygame.draw.line(self.screen, grid_col, (wx, cy + 2), (wx, cy + bh - 2), 1)
            for wy in range(cy + int(8*s), cy + bh, int(8*s)):
                pygame.draw.line(self.screen, grid_col, (cx + 2, wy), (cx + bw - 2, wy), 1)

            # top rim highlight
            pygame.draw.rect(self.screen, metal_hi, (cx, cy, bw, int(3*s)), border_radius=1)

            # right side face (gives 3-D depth)
            side_poly = [
                (cx + bw,      cy),
                (cx + bw + dp, cy - dp),
                (cx + bw + dp, cy - dp + bh),
                (cx + bw,      cy + bh),
            ]
            pygame.draw.polygon(self.screen, metal_shd, side_poly)
            pygame.draw.polygon(self.screen, metal_mid, side_poly, 1)

            # ── item in basket (coloured product block) ─────────────
            if item_col:
                # item sits inside front face
                pad = int(5 * s)
                iw2 = bw - pad * 2
                ih2 = int((bh - pad) * 0.55)
                item_hi = tuple(min(255, v + 40) for v in item_col)
                item_shd = tuple(max(0, v - 30) for v in item_col)
                pygame.draw.rect(self.screen, item_col,
                                 (cx + pad, cy + pad, iw2, ih2), border_radius=2)
                pygame.draw.rect(self.screen, item_hi,
                                 (cx + pad, cy + pad, iw2, int(ih2 * 0.35)), border_radius=2)
                pygame.draw.rect(self.screen, item_shd,
                                 (cx + pad, cy + pad, iw2, ih2), 1, border_radius=2)

            # ── handle bar (back-top edge) ───────────────────────────
            hbw = int(16 * s)
            hbh = int(5 * s)
            hx2 = cx + bw - hbw - int(2*s) + dp
            hy2 = cy - dp - hbh
            pygame.draw.rect(self.screen, metal_hi,
                             (hx2, hy2, hbw, hbh), border_radius=2)
            # handle post
            pygame.draw.rect(self.screen, metal_mid,
                             (hx2 + hbw - int(4*s), cy - dp, int(4*s), int(14*s)),
                             border_radius=1)

            # ── front push bar ───────────────────────────────────────
            pygame.draw.rect(self.screen, metal_shd,
                             (cx - int(3*s), cy + int(5*s), int(4*s), int(15*s)),
                             border_radius=1)

            # ── axles and wheels ─────────────────────────────────────
            axle_y = cy + bh + int(2*s)
            # front axle
            pygame.draw.line(self.screen, metal_mid,
                             (cx + int(3*s), axle_y),
                             (cx + int(3*s), axle_y + int(8*s)), 2)
            pygame.draw.line(self.screen, metal_mid,
                             (cx + bw - int(5*s), axle_y),
                             (cx + bw - int(5*s), axle_y + int(8*s)), 2)
            wr = max(2, int(4 * s))
            wy2 = axle_y + int(8*s)
            for wxp in [cx + int(2*s), cx + int(7*s),
                        cx + bw - int(8*s), cx + bw - int(3*s)]:
                pygame.draw.circle(self.screen, wheel_col, (wxp, wy2), wr)
                pygame.draw.circle(self.screen, wheel_hi,  (wxp, wy2), max(1, wr - 1))
                # axle pin highlight
                pygame.draw.circle(self.screen, metal_hi, (wxp, wy2), max(1, wr - 2))

        # stacked carts (3 nested, offset slightly)
        for si in range(3):
            draw_single_cart(STACK_X + si * 6, STACK_Y - si * 3, small=True)

        # "CARTS" label on corral
        cl = font_sec.render("CARTS", True, (140, 148, 158))
        self.screen.blit(cl, (STACK_X + 2, STACK_Y - 14))

        # customer carts — pushed ahead of each customer character
        customer_chars = self._preview_chars[:3]
        for ci2, ch in enumerate(customer_chars):
            # place cart slightly ahead of the character in their walking direction
            cart_offset_y = 28 if ch["vy"] >= 0 else -38
            cx2 = int(ch["x"]) - 19     # centre cart on character x
            cy2 = int(ch["y"]) + cart_offset_y
            item_col2 = list(PRODUCT_CATALOG.values())[ci2 % len(PRODUCT_CATALOG)]["color"]
            draw_single_cart(cx2, cy2, item_col=item_col2)

        # ── entrance mat ────────────────────────────────────────────
        mat = pygame.Rect(inset.centerx - 50, inset.bottom - 18, 100, 14)
        pygame.draw.rect(self.screen, (65, 48, 30), mat, border_radius=3)
        draw_text(self.screen, "WELCOME", (mat.centerx, mat.y + 2),
                  size=9, bold=True, color=(200, 180, 140), center=True)

    def draw_menu(self):
        t = self.auth_time

        # ── scanline overlay (same as auth) ────────────────────────────
        scan_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        for sy in range(0, HEIGHT, 4):
            pygame.draw.line(scan_surf, (0, 0, 0, 28), (0, sy), (WIDTH, sy))
        self.screen.blit(scan_surf, (0, 0))

        # ── floating pixel particles ────────────────────────────────────
        particle_colors = [ACCENT, ACCENT_2, (255, 213, 79), (180, 220, 255)]
        for p in self.pixel_particles:
            age_frac = p[5] / max(0.001, p[6])
            alpha = int(200 * (1 - abs(age_frac * 2 - 1)))
            c = particle_colors[p[3] % len(particle_colors)]
            ps = p[2]
            psurf = pygame.Surface((ps, ps), pygame.SRCALPHA)
            psurf.fill((*c, alpha))
            self.screen.blit(psurf, (int(p[0]), int(p[1])))

        corner_s = 8

        # ── LEFT panel: buttons ─────────────────────────────────────────
        left = pygame.Rect(60, 80, 480, 720)
        shadow_l = pygame.Surface((left.width + 8, left.height + 8), pygame.SRCALPHA)
        shadow_l.fill((0, 0, 0, 80))
        self.screen.blit(shadow_l, (left.x + 4, left.y + 8))
        pygame.draw.rect(self.screen, (22, 28, 50), left)
        pygame.draw.rect(self.screen, ACCENT, left, 3)
        for cx, cy in [(left.x, left.y), (left.right - corner_s, left.y),
                       (left.x, left.bottom - corner_s), (left.right - corner_s, left.bottom - corner_s)]:
            pygame.draw.rect(self.screen, ACCENT_2, (cx, cy, corner_s, corner_s))

        # pixel divider under greeting
        div_y = left.y + 148
        for dx in range(0, left.width - 40, 8):
            col = ACCENT if (dx // 8) % 2 == 0 else ACCENT_2
            pygame.draw.rect(self.screen, col, (left.x + 20 + dx, div_y, 6, 3))

        # greeting text
        draw_text(self.screen, "WELCOME BACK", (left.centerx, left.y + 48),
                  size=14, bold=True, color=TEXT_MUTED, center=True)
        pulse = (math.sin(t * 1.8) + 1) / 2
        name_r = int(lerp(160, 220, pulse))
        name_g = int(lerp(210, 255, pulse))
        name_b = int(lerp(100, 160, pulse))
        draw_text(self.screen, self.session.username,
                  (left.centerx + 2, left.y + 92),
                  size=BIG_TITLE, bold=True, color=(0, 0, 0), center=True)
        draw_text(self.screen, self.session.username,
                  (left.centerx, left.y + 90),
                  size=BIG_TITLE, bold=True, color=(name_r, name_g, name_b), center=True)

        # reposition and draw menu buttons with pixel shake on hover
        btn_top = div_y + 28
        btn_gap = 78
        btn_w   = left.width - 60
        for i, btn in enumerate(self.menu_buttons):
            btn.base_rect = pygame.Rect(left.x + 30, btn_top + i * btn_gap, btn_w, 56)
            shake_x = int(math.sin(t * 6 + i * 1.5) * 1.5 * btn.hover_t)
            shake_y = int(math.cos(t * 5 + i) * 1.5 * btn.hover_t)
            orig = btn.base_rect.topleft
            btn.base_rect.x += shake_x
            btn.base_rect.y += shake_y
            btn.draw(self.screen)
            btn.base_rect.topleft = orig

        # ── RIGHT panel: logo + info cards ─────────────────────────────
        right = pygame.Rect(572, 80, 808, 720)
        shadow_r = pygame.Surface((right.width + 8, right.height + 8), pygame.SRCALPHA)
        shadow_r.fill((0, 0, 0, 80))
        self.screen.blit(shadow_r, (right.x + 4, right.y + 8))
        pygame.draw.rect(self.screen, (22, 28, 50), right)
        pygame.draw.rect(self.screen, ACCENT_2, right, 3)
        for cx, cy in [(right.x, right.y), (right.right - corner_s, right.y),
                       (right.x, right.bottom - corner_s), (right.right - corner_s, right.bottom - corner_s)]:
            pygame.draw.rect(self.screen, ACCENT, (cx, cy, corner_s, corner_s))

        # logo + BYTEBIT MARKET (top-right of panel, bobbing)
        logo_size = 72
        logo_x = right.right - logo_size - 32
        logo_y = right.y + 24
        self.draw_bytebit_logo(logo_x, logo_y, size=logo_size)

        title_x = right.right - logo_size - 160
        title_y_base = right.y + 32
        bob_offset = int(math.sin(t * 2.2) * 4)

        # drop shadow then lit text for BYTEBIT
        draw_text(self.screen, "BYTEBIT",
                  (title_x + 2, title_y_base + bob_offset + 2),
                  size=32, bold=True, color=(0, 0, 0), center=False)
        pulse2 = (math.sin(t * 1.8) + 1) / 2
        tc = (int(lerp(160, 220, pulse2)), int(lerp(210, 255, pulse2)), int(lerp(100, 160, pulse2)))
        draw_text(self.screen, "BYTEBIT",
                  (title_x, title_y_base + bob_offset),
                  size=32, bold=True, color=tc)
        draw_text(self.screen, "MARKET",
                  (title_x + 2, title_y_base + bob_offset + 38),
                  size=26, bold=True, color=(0, 0, 0))
        draw_text(self.screen, "MARKET",
                  (title_x, title_y_base + bob_offset + 36),
                  size=26, bold=True, color=ACCENT_2)

        # pixel divider under logo row
        ldiv_y = right.y + 118
        for dx in range(0, right.width - 40, 8):
            col = ACCENT_2 if (dx // 8) % 2 == 0 else ACCENT
            pygame.draw.rect(self.screen, col, (right.x + 20 + dx, ldiv_y, 6, 3))

        # tagline
        draw_text(self.screen, "[ MODERN SUPERMARKET SIMULATOR ]",
                  (right.centerx, ldiv_y + 20),
                  size=13, bold=True, color=TEXT_MUTED, center=True)

        # ── info cards row ──────────────────────────────────────────────
        cards = [
            ("INVENTORY",   "Restock shelves,\nmanage prices,\navoid empty aisles.", ACCENT,  "📦"),
            ("OPERATIONS",  "Checkout, customer\nflow, employee\nperformance.",       INFO,    "⚙"),
            ("PROGRESS",    "Firebase saves,\nreports, reviews,\nleaderboard.",       ACCENT_2,"★"),
        ]
        card_w   = 224
        card_h   = 210
        card_gap = 28
        cards_total_w = len(cards) * card_w + (len(cards) - 1) * card_gap
        card_x0  = right.centerx - cards_total_w // 2
        card_y   = ldiv_y + 52

        for ci, (ctitle, cbody, ccolor, _icon) in enumerate(cards):
            cx2 = card_x0 + ci * (card_w + card_gap)
            crect = pygame.Rect(cx2, card_y, card_w, card_h)

            # glowing card shadow
            glow_s = pygame.Surface((card_w + 22, card_h + 22), pygame.SRCALPHA)
            glow_a = int(30 + 20 * math.sin(t * 1.4 + ci))
            pygame.draw.rect(glow_s, (*ccolor, glow_a), glow_s.get_rect(), border_radius=20)
            self.screen.blit(glow_s, (cx2 - 11, card_y - 9))

            draw_shadowed_card(self.screen, crect, color=CARD, radius=18,
                               shadow_offset=6, border_color=ccolor, border_width=2)

            # colour bar accent at top of card
            bar_rect = pygame.Rect(cx2 + 4, card_y + 4, card_w - 8, 6)
            pygame.draw.rect(self.screen, ccolor, bar_rect, border_radius=3)

            draw_badge(self.screen, ctitle, crect.x + 14, crect.y + 20, color=ccolor)

            # multi-line body text
            line_y = crect.y + 76
            for line in cbody.split("\n"):
                draw_text(self.screen, line, (crect.x + 16, line_y),
                          size=BODY_SIZE, color=TEXT_MUTED)
                line_y += 28

            # animated corner pip
            pip_phase = math.sin(t * 2.5 + ci * 1.1)
            pip_r = int(4 + 2 * pip_phase)
            pip_col = tuple(min(255, v + int(40 * pip_phase)) for v in ccolor)
            pygame.draw.circle(self.screen, pip_col,
                               (crect.right - 18, crect.bottom - 18), pip_r)

        # ── flow strip ──────────────────────────────────────────────────
        flow_y = card_y + card_h + 28
        flow_rect = pygame.Rect(right.x + 20, flow_y, right.width - 40, 72)
        draw_shadowed_card(self.screen, flow_rect, color=(18, 22, 42), radius=18,
                           shadow_offset=4, border_color=ACCENT, border_width=1)
        # blinking prompt
        if int(t * 1.6) % 2 == 0:
            draw_text(self.screen, ">> SELECT AN OPTION TO BEGIN <<",
                      (flow_rect.centerx, flow_rect.y + 14),
                      size=13, bold=True, color=(0, 0, 0), center=True)
        draw_text(self.screen, ">> SELECT AN OPTION TO BEGIN <<",
                  (flow_rect.centerx, flow_rect.y + 13),
                  size=13, bold=True,
                  color=ACCENT if int(t * 1.6) % 2 == 0 else TEXT_MUTED,
                  center=True)
        draw_text(self.screen, "Login  →  Menu  →  Market Floor  →  Daily Report  →  Save / Leaderboard",
                  (flow_rect.centerx, flow_rect.y + 40),
                  size=BODY_SIZE, color=TEXT_MUTED, center=True)

        # ── stat badges (day / money) if save exists ────────────────────
        if self.state:
            stat_y = right.y + 138
            draw_badge(self.screen, f"Day {self.state.day}", right.x + 26, stat_y, color=INFO)
            draw_badge(self.screen, f"${self.state.money:.0f}", right.x + 116, stat_y, color=SUCCESS)

        if self.menu_modal == "leaderboard":
            self.draw_menu_modal("Leaderboard", self.draw_leaderboard_overlay)
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

    def draw_store_map(self):  # noqa: C901  (complex but intentional)
        t = self.auth_time  # shared animation clock

        # ── day/night cycle driven by day_timer ────────────────────────────
        day_frac = 1.0 - max(0.0, min(1.0, self.day_timer / max(1, DAY_LENGTH_SECONDS)))

        def sky_col(frac):
            stops = [
                (0.00, (255, 160,  80)),
                (0.12, (255, 210, 120)),
                (0.30, (130, 190, 255)),
                (0.55, (100, 170, 240)),
                (0.72, (255, 180,  90)),
                (0.85, (220,  90,  50)),
                (1.00, ( 18,  20,  45)),
            ]
            for i in range(len(stops) - 1):
                f0, c0 = stops[i]
                f1, c1 = stops[i + 1]
                if f0 <= frac <= f1:
                    lt = (frac - f0) / (f1 - f0)
                    return tuple(int(lerp(c0[j], c1[j], lt)) for j in range(3))
            return stops[-1][1]

        sky = sky_col(day_frac)

        # ── master floor rect ──────────────────────────────────────────────
        floor = pygame.Rect(28, 74, WIDTH - 56, HEIGHT - 110)
        pygame.draw.rect(self.screen, FLOOR, floor, border_radius=24)

        # ── windows row at top of store (matches preview) ──────────────────
        WIN_ROW_H = 52
        win_zone = pygame.Rect(floor.x, floor.y, floor.width, WIN_ROW_H)
        pygame.draw.rect(self.screen, (50, 55, 70), win_zone, border_radius=24)

        n_wins = 8
        win_w, win_h = 62, 34
        win_gap = (floor.width - n_wins * win_w) // (n_wins + 1)
        for wi in range(n_wins):
            wx = floor.x + win_gap + wi * (win_w + win_gap)
            wy = floor.y + 8
            pygame.draw.rect(self.screen, (80, 75, 65), (wx - 3, wy - 3, win_w + 6, win_h + 6), border_radius=4)
            for row in range(win_h):
                row_frac = row / max(1, win_h - 1)
                base = sky
                horizon = tuple(min(255, v + 28) for v in sky)
                rc = tuple(int(lerp(base[j], horizon[j], row_frac)) for j in range(3))
                pygame.draw.line(self.screen, rc, (wx, wy + row), (wx + win_w - 1, wy + row))
            # sun / moon
            sun_x = wx + int(win_w * 0.5 + math.sin(day_frac * math.pi * 2) * win_w * 0.36)
            sun_y = wy + int(win_h * 0.5 - math.cos(day_frac * math.pi * 2) * win_h * 0.32)
            if day_frac < 0.82:
                sc = (255, 240, 100) if day_frac < 0.65 else (255, 160, 60)
                pygame.draw.circle(self.screen, sc, (sun_x, sun_y), 5)
                if 0.3 < day_frac < 0.6:
                    for ang in range(0, 360, 45):
                        rx = int(math.cos(math.radians(ang)) * 8)
                        ry = int(math.sin(math.radians(ang)) * 8)
                        pygame.draw.line(self.screen, (255, 230, 80), (sun_x, sun_y), (sun_x + rx, sun_y + ry), 1)
            else:
                pygame.draw.circle(self.screen, (230, 230, 210), (sun_x, sun_y), 4)
                pygame.draw.circle(self.screen, sky, (sun_x + 2, sun_y - 1), 3)
            pygame.draw.line(self.screen, (80, 75, 65), (wx + win_w // 2, wy), (wx + win_w // 2, wy + win_h), 1)
            pygame.draw.line(self.screen, (80, 75, 65), (wx, wy + win_h // 2), (wx + win_w, wy + win_h // 2), 1)
            pygame.draw.rect(self.screen, (100, 95, 85), (wx - 4, wy + win_h, win_w + 8, 5), border_radius=2)

        # time-of-day label
        hour_labels = ["DAWN", "MORNING", "MIDDAY", "AFTERNOON", "DUSK", "NIGHT"]
        hour_idx = min(5, int(day_frac * 6))
        tod_lbl = get_font(9, bold=True).render(hour_labels[hour_idx], True, (200, 210, 220))
        self.screen.blit(tod_lbl, (floor.right - tod_lbl.get_width() - 14, floor.y + WIN_ROW_H - 14))

        # ── tiled floor below windows ──────────────────────────────────────
        floor_y = floor.y + WIN_ROW_H
        tile = 32
        for gx in range(floor.x, floor.right, tile):
            pygame.draw.line(self.screen, AISLE, (gx, floor_y), (gx, floor.bottom), 1)
        for gy in range(floor_y, floor.bottom, tile):
            pygame.draw.line(self.screen, AISLE, (floor.x + 4, gy), (floor.right - 4, gy), 1)

        # ── shared drawing helpers ─────────────────────────────────────────
        font_sec  = get_font(10, bold=True)
        font_sign = get_font(11, bold=True)

        # def draw_overhead_sign(cx, sign_y, text, bg_col, text_col=(255, 245, 200)):
        #     lbl = font_sign.render(text, True, text_col)
        #     pad = 9
        #     sw, sh = lbl.get_width() + pad * 2, lbl.get_height() + 6
        #     sx = cx - sw // 2
        #     pygame.draw.line(self.screen, (120, 120, 130), (cx, sign_y - 10), (cx, sign_y), 1)
        #     pygame.draw.rect(self.screen, bg_col, (sx, sign_y, sw, sh), border_radius=4)
        #     pygame.draw.rect(self.screen, tuple(max(0, v - 40) for v in bg_col), (sx, sign_y, sw, sh), 2, border_radius=4)
        #     self.screen.blit(lbl, (sx + pad, sign_y + 3))

        # def draw_shelf_unit(sx, sy, sw, sh, products, layers=3):
        #     pygame.draw.rect(self.screen, WOOD, (sx, sy, sw, sh), border_radius=5)
        #     pygame.draw.rect(self.screen, tuple(max(0, v - 25) for v in WOOD), (sx + sw - 6, sy, 6, sh), border_radius=5)
        #     layer_h = sh // (layers + 1)
        #     for li in range(layers):
        #         plank_y = sy + layer_h * (li + 1)
        #         pygame.draw.rect(self.screen, SHELF, (sx + 4, plank_y, sw - 10, 8), border_radius=2)
        #         pygame.draw.rect(self.screen, tuple(max(0, v - 20) for v in SHELF), (sx + 4, plank_y + 7, sw - 10, 2))
        #         slot_w = max(1, (sw - 12) // max(1, len(products)))
        #         for pi, (pcol, _) in enumerate(products):
        #             shimmer = int(math.sin(t * 2.0 + sx * 0.02 + pi + li) * 8)
        #             c = tuple(min(255, v + shimmer) for v in pcol)
        #             pygame.draw.rect(self.screen, c, (sx + 6 + pi * slot_w, plank_y - 19, slot_w - 1, 19), border_radius=2)
        #             pygame.draw.rect(self.screen, (255, 250, 180), (sx + 6 + pi * slot_w, plank_y - 3, slot_w - 1, 3))

        # ── section layout (4 sections across the store width) ────────────
        # The store floor spans floor.x … floor.right.  We place 4 sections at
        # 9 / 28 / 52 / 74 % of floor width, leaving corridor gaps between them.
        iw = floor.width
        ix = floor.x
        SIGN_Y      = floor_y + 4
        SHELF_STOP_Y = floor.bottom - 130   # shelves stop above the mat / register area
        CONTENT_Y   = floor_y + 30

        SEC_GROCERY_CX = ix + int(iw * 0.10)
        SEC_FROZEN_CX  = ix + int(iw * 0.30)
        SEC_DELI_CX    = ix + int(iw * 0.53)
        SEC_TECH_CX    = ix + int(iw * 0.74)

        # draw_overhead_sign(SEC_GROCERY_CX, SIGN_Y, "GROCERY", (60, 120, 60))
        # draw_overhead_sign(SEC_FROZEN_CX,  SIGN_Y, "FROZEN",  (30, 90, 160))
        # draw_overhead_sign(SEC_DELI_CX,    SIGN_Y, "DELI",    (160, 80, 40))
        # draw_overhead_sign(SEC_TECH_CX,    SIGN_Y, "TECH",    (40, 40, 100))

        # # ── SECTION 1: Grocery shelves (live game state) ───────────────────
        # grocery_products = [
        #     ((245, 180, 80), "chips"), ((195, 225, 255), "milk"),
        #     ((214, 169, 111), "bread"), ((232, 86, 86), "apple"),
        # ]
        # shelf_w  = 56
        # grocery_h = SHELF_STOP_Y - CONTENT_Y
        # draw_shelf_unit(SEC_GROCERY_CX - shelf_w // 2, CONTENT_Y, shelf_w, grocery_h, grocery_products, layers=4)

        # # ── SECTION 2: Frozen refrigerators ───────────────────────────────
        # frozen_defs = [
        #     ((160, 210, 255), "Frz.Fruit"),
        #     ((180, 240, 200), "Frz.Veg"),
        #     ((255, 200, 180), "Frz.Prot"),
        # ]
        # fridge_w, fridge_h = 50, SHELF_STOP_Y - CONTENT_Y
        # fridge_gap = 6
        # frozen_x0 = SEC_FROZEN_CX - (len(frozen_defs) * (fridge_w + fridge_gap)) // 2 + fridge_gap
        # for fi, (fcol, fname) in enumerate(frozen_defs):
        #     fx = frozen_x0 + fi * (fridge_w + fridge_gap)
        #     fy = CONTENT_Y
        #     CASE_COL  = (44, 74, 108)
        #     CASE_DARK = (30, 52, 80)
        #     pygame.draw.rect(self.screen, CASE_COL, (fx, fy, fridge_w, fridge_h), border_radius=5)
        #     pygame.draw.rect(self.screen, CASE_DARK, (fx, fy, 5, fridge_h), border_radius=5)
        #     pygame.draw.rect(self.screen, CASE_DARK, (fx + fridge_w - 5, fy, 5, fridge_h), border_radius=5)
        #     pygame.draw.rect(self.screen, (60, 100, 145), (fx, fy, fridge_w, 8), border_radius=5)
        #     pygame.draw.rect(self.screen, (30, 50, 75), (fx, fy + fridge_h - 8, fridge_w, 8), border_radius=3)
        #     GLASS_MARGIN = 6
        #     gx2, gy2 = fx + GLASS_MARGIN, fy + 10
        #     gw2, gh2 = fridge_w - GLASS_MARGIN * 2, fridge_h - 22
        #     glass_surf = pygame.Surface((gw2, gh2), pygame.SRCALPHA)
        #     glass_surf.fill((200, 235, 255, 55))
        #     self.screen.blit(glass_surf, (gx2, gy2))
        #     pygame.draw.rect(self.screen, (55, 90, 130), (gx2, gy2, gw2, gh2), 2, border_radius=3)
        #     item_rows = 4
        #     row_h = (gh2 - 8) // item_rows
        #     for ri in range(item_rows):
        #         ry2 = gy2 + 4 + ri * row_h
        #         pygame.draw.rect(self.screen, (60, 100, 140), (gx2 + 2, ry2 + row_h - 4, gw2 - 4, 4))
        #         shimmer = int(math.sin(t * 1.8 + fi * 2 + ri) * 6)
        #         ic = tuple(min(255, v + shimmer) for v in fcol)
        #         pygame.draw.rect(self.screen, ic, (gx2 + 3, ry2 + 2, gw2 - 6, row_h - 8), border_radius=2)
        #         pygame.draw.rect(self.screen, tuple(max(0, v - 40) for v in ic), (gx2 + 3, ry2 + 2, gw2 - 6, row_h - 8), 1, border_radius=2)
        #         pygame.draw.rect(self.screen, (255, 250, 180), (gx2 + 3, ry2 + row_h - 9, gw2 - 6, 4))
        #         item_lbl = font_sec.render(fname[:4], True, (40, 40, 60))
        #         self.screen.blit(item_lbl, (gx2 + max(1, gw2 // 2 - item_lbl.get_width() // 2), ry2 + 3))
        #     hx = fx + fridge_w - GLASS_MARGIN - 4
        #     pygame.draw.rect(self.screen, (180, 190, 200), (hx, fy + fridge_h // 2 - 20, 5, 40), border_radius=3)
        #     led_x, led_y = fx + 8, fy + 1
        #     pygame.draw.rect(self.screen, (10, 20, 35), (led_x, led_y, fridge_w - 16, 7), border_radius=2)
        #     temp_glow = int((math.sin(t * 2.0 + fi) + 1) * 4)
        #     pygame.draw.rect(self.screen, (0, min(255, 180 + temp_glow), 80), (led_x + 2, led_y + 1, 18, 5), border_radius=1)

        # # ── SECTION 3: Deli counter ────────────────────────────────────────
        # deli_w  = 82
        # deli_x0 = SEC_DELI_CX - deli_w // 2
        # BACK_H  = SHELF_STOP_Y - CONTENT_Y
        # back_shelf_col = (170, 140, 100)
        # pygame.draw.rect(self.screen, back_shelf_col, (deli_x0, CONTENT_Y, deli_w, BACK_H), border_radius=4)
        # deli_items = [
        #     ((214, 169, 111), "Bread"),
        #     ((255, 200, 120), "Donut"),
        #     ((210, 140, 160), "Cake"),
        # ]
        # tier_rows = 4
        # tier_h = BACK_H // (tier_rows + 1)
        # for tr in range(tier_rows):
        #     ty2 = CONTENT_Y + tier_h * (tr + 1)
        #     pygame.draw.rect(self.screen, (200, 170, 125), (deli_x0 + 3, ty2, deli_w - 6, 5), border_radius=2)
        #     for tpi in range(3):
        #         tcol, _ = deli_items[tpi % len(deli_items)]
        #         shimmer = int(math.sin(t * 1.5 + tr + tpi) * 8)
        #         tc = tuple(min(255, v + shimmer) for v in tcol)
        #         pygame.draw.ellipse(self.screen, tc, (deli_x0 + 6 + tpi * 24, ty2 - 14, 22, 13))
        # COUNTER_H = 58
        # counter_y2 = CONTENT_Y + BACK_H - COUNTER_H - 2
        # pygame.draw.rect(self.screen, (160, 130, 95), (deli_x0, counter_y2 + 20, deli_w, COUNTER_H), border_radius=5)
        # pygame.draw.rect(self.screen, (170, 210, 245), (deli_x0 + 2, counter_y2, deli_w - 4, 24), border_radius=3)
        # pygame.draw.rect(self.screen, (120, 175, 220), (deli_x0 + 2, counter_y2, deli_w - 4, 24), 2, border_radius=3)
        # for di, (dcol, dname) in enumerate(deli_items):
        #     ddx = deli_x0 + 6 + di * 24
        #     pygame.draw.ellipse(self.screen, dcol, (ddx, counter_y2 + 5, 20, 13))
        #     dlbl = get_font(8).render(dname, True, (70, 50, 30))
        #     self.screen.blit(dlbl, (ddx + 10 - dlbl.get_width() // 2, counter_y2 + 20))
        # pygame.draw.rect(self.screen, (200, 175, 130), (deli_x0, counter_y2 + 18, deli_w, 6), border_radius=2)

        # # ── SECTION 4: Tech aisles ─────────────────────────────────────────
        # TECH_STOP_Y  = SHELF_STOP_Y - 60
        # tech_aisle_h = TECH_STOP_Y - CONTENT_Y
        # tech_aisles = [(-72, "AISLE A"), (0, "AISLE B"), (72, "AISLE C")]
        # tech_device_rows = [
        #     ((55,  55,  68), (90,  170, 255), "PHONE",  14, 22),
        #     ((38,  38,  48), (130, 215, 255), "LAPTOP", 38, 24),
        #     ((175, 175, 195), (70, 190, 255), "ROUTER", 28, 17),
        # ]
        # for ai, (ax_off, alabel) in enumerate(tech_aisles):
        #     shelf_ax = SEC_TECH_CX + ax_off
        #     shelf_aw = 54
        #     pygame.draw.rect(self.screen, WOOD, (shelf_ax - shelf_aw // 2, CONTENT_Y, shelf_aw, tech_aisle_h), border_radius=4)
        #     pygame.draw.rect(self.screen, tuple(max(0, v - 25) for v in WOOD), (shelf_ax + shelf_aw // 2 - 6, CONTENT_Y, 6, tech_aisle_h), border_radius=4)
        #     num_rows = len(tech_device_rows)
        #     row_zone_h = tech_aisle_h // (num_rows + 1)
        #     for ri, (bcol, scol, dname, dw, dh) in enumerate(tech_device_rows):
        #         plank_y = CONTENT_Y + row_zone_h * (ri + 1)
        #         pygame.draw.rect(self.screen, SHELF, (shelf_ax - shelf_aw // 2 + 3, plank_y, shelf_aw - 6, 7), border_radius=2)
        #         pygame.draw.rect(self.screen, tuple(max(0, v - 20) for v in SHELF), (shelf_ax - shelf_aw // 2 + 3, plank_y + 6, shelf_aw - 6, 2))
        #         tx2 = shelf_ax - dw // 2
        #         ty2 = plank_y - dh - 4
        #         sglow = int((math.sin(t * 2.8 + ai * 1.1 + ri * 0.9) + 1) * 12)
        #         halo_surf = pygame.Surface((dw + 10, dh + 10), pygame.SRCALPHA)
        #         pygame.draw.rect(halo_surf, (*scol, 35 + sglow), halo_surf.get_rect(), border_radius=5)
        #         self.screen.blit(halo_surf, (tx2 - 5, ty2 - 5))
        #         pygame.draw.rect(self.screen, bcol, (tx2, ty2, dw, dh), border_radius=3)
        #         pygame.draw.rect(self.screen, (20, 20, 30), (tx2 + 2, ty2 + 2, dw - 4, dh - 5), border_radius=2)
        #         sc2 = tuple(min(255, v + sglow) for v in scol)
        #         pygame.draw.rect(self.screen, sc2, (tx2 + 3, ty2 + 3, dw - 6, dh - 8), border_radius=2)
        #         for bar_i in range(2):
        #             bar_y2 = ty2 + 5 + bar_i * 5
        #             bar_col = (255, 255, 255) if (int(t * 2 + bar_i + ri) % 4 < 2) else (180, 220, 255)
        #             pygame.draw.rect(self.screen, bar_col, (tx2 + 4, bar_y2, dw - 10, 2), border_radius=1)
        #         pygame.draw.rect(self.screen, tuple(max(0, v - 20) for v in bcol), (tx2, ty2, dw, dh), 1, border_radius=3)
        #         dlbl = font_sec.render(dname, True, (190, 200, 220))
        #         self.screen.blit(dlbl, (tx2 + dw // 2 - dlbl.get_width() // 2, plank_y + 8))
        #     pygame.draw.rect(self.screen, (255, 250, 180), (shelf_ax - shelf_aw // 2 + 3, TECH_STOP_Y - 10, shelf_aw - 6, 6), border_radius=2)

        # ── checkout register (bottom-right, matching preview) ─────────────
        # counter_rect = pygame.Rect(floor.right - 175, floor.bottom - 108, 130, 72)
        # pygame.draw.rect(self.screen, REGISTER, counter_rect, border_radius=7)
        # pygame.draw.rect(self.screen, (55, 65, 75), counter_rect, 2, border_radius=7)
        # scr_glow = int((math.sin(t * 3.0) + 1) * 18)
        # pygame.draw.rect(self.screen, (0, min(255, 150 + scr_glow), min(255, 55 + scr_glow)),
        #                  (counter_rect.x + 7, counter_rect.y + 7, 44, 26), border_radius=3)
        # laser_y = counter_rect.y + 40 + int(math.sin(t * 6) * 5)
        # pygame.draw.line(self.screen, (255, 60, 60),
        #                  (counter_rect.x + 54, laser_y), (counter_rect.right - 7, laser_y), 2)
        # belt_x = counter_rect.x + 54
        # for stripe in range(5):
        #     sx2 = belt_x + stripe * 12 + int(t * 18) % 12
        #     pygame.draw.line(self.screen, (70, 75, 80),
        #                      (sx2, counter_rect.y + 34), (sx2, counter_rect.y + 56), 2)

        # # ── cart corral (bottom-left corner, matching preview) ─────────────
        # STACK_X = floor.x + 10
        # STACK_Y = floor.bottom - 90

        # def draw_single_cart(cx, cy, item_col=None, small=False):
        #     s  = 0.62 if small else 1.0
        #     bw = int(38 * s)
        #     bh = int(24 * s)
        #     dp = int(10 * s)
        #     cx, cy = int(cx), int(cy)
        #     metal_mid = (148, 158, 170)
        #     metal_hi  = (200, 210, 218)
        #     metal_shd = (90,  98, 108)
        #     wheel_col = (42,  44,  54)
        #     wheel_hi  = (75,  80,  92)
        #     back_poly = [(cx + dp, cy - dp), (cx + bw + dp, cy - dp), (cx + bw, cy), (cx, cy)]
        #     pygame.draw.polygon(self.screen, metal_shd, back_poly)
        #     pygame.draw.polygon(self.screen, metal_mid, back_poly, 1)
        #     pygame.draw.rect(self.screen, metal_mid, (cx, cy, bw, bh), border_radius=2)
        #     grid_col = tuple(max(0, v - 28) for v in metal_mid)
        #     for wx in range(cx + int(9*s), cx + bw, int(9*s)):
        #         pygame.draw.line(self.screen, grid_col, (wx, cy + 2), (wx, cy + bh - 2), 1)
        #     for wy in range(cy + int(8*s), cy + bh, int(8*s)):
        #         pygame.draw.line(self.screen, grid_col, (cx + 2, wy), (cx + bw - 2, wy), 1)
        #     pygame.draw.rect(self.screen, metal_hi, (cx, cy, bw, int(3*s)), border_radius=1)
        #     side_poly = [(cx+bw, cy), (cx+bw+dp, cy-dp), (cx+bw+dp, cy-dp+bh), (cx+bw, cy+bh)]
        #     pygame.draw.polygon(self.screen, metal_shd, side_poly)
        #     pygame.draw.polygon(self.screen, metal_mid, side_poly, 1)
        #     hbw = int(16 * s); hbh = int(5 * s)
        #     hx2 = cx + bw - hbw - int(2*s) + dp; hy2 = cy - dp - hbh
        #     pygame.draw.rect(self.screen, metal_hi, (hx2, hy2, hbw, hbh), border_radius=2)
        #     pygame.draw.rect(self.screen, metal_mid, (hx2 + hbw - int(4*s), cy - dp, int(4*s), int(14*s)), border_radius=1)
        #     pygame.draw.rect(self.screen, metal_shd, (cx - int(3*s), cy + int(5*s), int(4*s), int(15*s)), border_radius=1)
        #     axle_y = cy + bh + int(2*s)
        #     pygame.draw.line(self.screen, metal_mid, (cx + int(3*s), axle_y), (cx + int(3*s), axle_y + int(8*s)), 2)
        #     pygame.draw.line(self.screen, metal_mid, (cx + bw - int(5*s), axle_y), (cx + bw - int(5*s), axle_y + int(8*s)), 2)
        #     wr = max(2, int(4 * s))
        #     wy2 = axle_y + int(8*s)
        #     for wxp in [cx + int(2*s), cx + int(7*s), cx + bw - int(8*s), cx + bw - int(3*s)]:
        #         pygame.draw.circle(self.screen, wheel_col, (wxp, wy2), wr)
        #         pygame.draw.circle(self.screen, wheel_hi,  (wxp, wy2), max(1, wr - 1))
        #         pygame.draw.circle(self.screen, metal_hi,  (wxp, wy2), max(1, wr - 2))

        # for si in range(3):
        #     draw_single_cart(STACK_X + si * 6, STACK_Y - si * 3, small=True)
        # cl = font_sec.render("CARTS", True, (140, 148, 158))
        # self.screen.blit(cl, (STACK_X + 2, STACK_Y + 28))

        # ── interactive zone overlays (zones with glow, label, and "Press E") ──
        zone_colors = {
            "stock":    (214, 236, 244),
            "checkout": (214, 222, 248),
            "manager":  (229, 220, 255),
            "prices":   (223, 242, 220),
            "break":    (251, 234, 209),
        }
        for name, rect in self.zone_rects.items():
            pygame.draw.rect(self.screen, zone_colors[name], rect, border_radius=20)
            pygame.draw.rect(self.screen, (255, 255, 255), rect, 2, border_radius=20)
            glow = pygame.Surface((rect.width + 30, rect.height + 30), pygame.SRCALPHA)
            pygame.draw.rect(glow, (*ZONE_GLOW, 28), glow.get_rect(), border_radius=26)
            self.screen.blit(glow, (rect.x - 15, rect.y - 15))
            draw_text(self.screen, name.title(), rect.center, size=BODY_SIZE, color=TEXT_DARK, bold=True, center=True)
            draw_text(self.screen, "Press E", (rect.centerx, rect.bottom - 18), size=SMALL_SIZE, color=(78, 88, 118), center=True)

        # ── gameplay shelves (hitboxes with real stock levels) ─────────────
        labels = list(SHELF_LAYOUT.keys())
        for i, rect in enumerate(self.shelf_hitboxes()):
            # shelf unit body (rich style matching preview)
            pygame.draw.rect(self.screen, WOOD, rect, border_radius=14)
            pygame.draw.rect(self.screen, tuple(max(0, v - 25) for v in WOOD),
                             (rect.right - 8, rect.y, 8, rect.height), border_radius=14)
            for level in range(3):
                py = rect.y + 18 + level * 30
                pygame.draw.rect(self.screen, SHELF, (rect.x + 8, py, rect.width - 16, 8), border_radius=4)
                pygame.draw.rect(self.screen, tuple(max(0, v - 20) for v in SHELF),
                                 (rect.x + 8, py + 7, rect.width - 16, 2))

            category    = labels[i]
            product_key = SHELF_LAYOUT[category]
            capacity    = SHELF_CAPACITY + (8 if self.state.upgrades.get("shelves") else 0)
            qty         = self.state.shelves[category]
            fill_ratio  = min(1.0, qty / max(1, capacity))
            fill_color  = PRODUCT_CATALOG[product_key]["color"]

            # product items with shimmer matching preview
            for item_index in range(min(qty, 9)):
                row = item_index // 3
                col = item_index % 3
                shimmer = int(math.sin(t * 2.0 + i + col + row) * 8)
                ic = tuple(min(255, v + shimmer) for v in fill_color)
                pygame.draw.rect(self.screen, ic,
                                 (rect.x + 22 + col * 44, rect.y + 6 + row * 30, 26, 22),
                                 border_radius=6)
                # price-tag strip on each item
                pygame.draw.rect(self.screen, (255, 250, 180),
                                 (rect.x + 22 + col * 44, rect.y + 6 + row * 30 + 18, 26, 4))

            # stock level bar
            bar = pygame.Rect(rect.x + 14, rect.bottom + 8, rect.width - 28, 10)
            pygame.draw.rect(self.screen, PANEL_ALT, bar, border_radius=5)
            bar_col = ACCENT if fill_ratio > 0.35 else WARNING if fill_ratio > 0.15 else DANGER
            pygame.draw.rect(self.screen, bar_col, (bar.x, bar.y, int(bar.width * fill_ratio), bar.height), border_radius=5)

            draw_text(self.screen, category.title(), (rect.x + 8, rect.bottom + 22), size=SMALL_SIZE, color=TEXT_DARK, bold=True)
            draw_text(self.screen, f"${self.state.prices[product_key]:.2f}", (rect.right - 56, rect.bottom + 20), size=SMALL_SIZE, color=TEXT_DARK)

        # ── animated walk characters (reuse preview chars if on game scene) ─
        def draw_person_walk_game(px_pos, py_pos, body_color, hat_color, label,
                                  carrying, walk_phase, facing_down, paused,
                                  skin_tone=(224, 190, 155), hair_color=(60, 40, 25),
                                  pant_color=(45, 50, 75), shoe_color=(32, 22, 16)):
            ...
            # px_pos, py_pos = int(px_pos), int(py_pos)
            # bob   = 0 if paused else int(math.sin(walk_phase * 2) * 2.2)
            # swing = 0.0 if paused else math.sin(walk_phase)

        #     # ground shadow
        #     shadow_surf = pygame.Surface((34, 10), pygame.SRCALPHA)
        #     for sx in range(17):
        #         alpha = int(90 * (1 - (sx / 17) ** 1.6))
        #         pygame.draw.line(shadow_surf, (0, 0, 0, alpha), (17 - sx, 5), (17 + sx, 5), 1)
        #     self.screen.blit(shadow_surf, (px_pos - 17, py_pos + 22))

        #     # legs
        #     for li, (lx, lsw) in enumerate([(-4, swing), (3, -swing)]):
        #         depth = li == 0
        #         ly_extra = int(lsw * 8)
        #         leg_shade = tuple(max(0, v - (18 if depth else 0)) for v in pant_color)
        #         pygame.draw.rect(self.screen, leg_shade, (px_pos + lx - 1, py_pos + 8 + bob, 6, 7), border_radius=3)
        #         pygame.draw.rect(self.screen, leg_shade, (px_pos + lx, py_pos + 14 + bob + ly_extra, 5, 6), border_radius=2)
        #         shoe_x = px_pos + lx - (1 if facing_down else 0)
        #         shoe_y = py_pos + 19 + bob + ly_extra
        #         pygame.draw.rect(self.screen, shoe_color, (shoe_x, shoe_y, 8, 4), border_radius=2)

        #     # torso
        #     torso_x, torso_y = px_pos - 8, py_pos - 8 + bob
        #     pygame.draw.rect(self.screen, body_color, (torso_x, torso_y, 16, 17), border_radius=4)
        #     shadow_col = tuple(max(0, v - 38) for v in body_color)
        #     pygame.draw.rect(self.screen, shadow_col, (torso_x + 11, torso_y + 2, 4, 13), border_radius=2)

        #     # head
        #     pygame.draw.circle(self.screen, skin_tone, (px_pos, py_pos - 16 + bob), 7)
        #     # hat
        #     if hat_color:
        #         pygame.draw.rect(self.screen, hat_color, (px_pos - 7, py_pos - 27 + bob, 14, 8), border_radius=3)
        #         pygame.draw.rect(self.screen, hat_color, (px_pos - 9, py_pos - 21 + bob, 18, 3), border_radius=2)

        #     # role badge
        #     if label:
        #         lsurf = font_sec.render(label, True, (220, 230, 245))
        #         lw = lsurf.get_width()
        #         pill = pygame.Surface((lw + 8, 13), pygame.SRCALPHA)
        #         pygame.draw.rect(pill, (20, 22, 38, 180), pill.get_rect(), border_radius=6)
        #         self.screen.blit(pill, (px_pos - lw // 2 - 4, py_pos + 24))
        #         self.screen.blit(lsurf, (px_pos - lw // 2, py_pos + 26))

        # Map preview char corridors to actual game floor coordinates.
        # Corridors sit between the 4 sections (at ~20/42/62/90% of floor width).
        corridor_x_fracs = [0.20, 0.42, 0.62, 0.90]
        game_char_xs = [floor.x + int(iw * f) for f in corridor_x_fracs]
        CHAR_DETAILS = [
            ((220, 185, 145), (55,  35, 22), (45, 50, 80),  (28, 20, 16)),
            ((175, 125,  85), (20,  15, 10), (55, 40, 35),  (22, 14, 10)),
            ((235, 200, 165), (140, 80, 30), (35, 55, 45),  (26, 18, 14)),
            ((160,  95,  60), (18,  12,  8), (40, 48, 70),  (24, 16, 12)),
            ((210, 170, 130), (90,  55, 20), (50, 44, 35),  (30, 22, 18)),
            ((225, 190, 155), (60,  45, 30), (35, 38, 65),  (25, 18, 14)),
        ]
        for idx, ch in enumerate(self._preview_chars):
            # Remap char x from preview inset to game floor
            ch_x = game_char_xs[idx % len(game_char_xs)]
            ch_y = ch["y"]
            # Clamp y to game floor bounds
            ch_y = max(floor_y + 40, min(floor.bottom - 50, ch_y))
            paused = ch["pause_t"] > 0
            facing_down = ch["vy"] >= 0
            sk, hr, pt, sh = CHAR_DETAILS[idx % len(CHAR_DETAILS)]
            draw_person_walk_game(
                ch_x, ch_y,
                ch["body_col"], ch["hat_col"], ch["label"],
                ch["carrying"], ch["walk_phase"], facing_down, paused,
                skin_tone=sk, hair_color=hr, pant_color=pt, shoe_color=sh,
            )

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
            print("responses: " + self.current_customer["posResponse"],self.current_customer["negResponse"])
            draw_text(self.screen, "Complaint", (right.x + 24, right.y + 24), size=TITLE_SIZE, bold=True)
            draw_text(self.screen, self.current_customer["complaint"], (right.x + 24, right.y + 76), size=BODY_SIZE, color=TEXT_MUTED)
            draw_text(self.screen, "1: " + self.current_customer["posResponse"], (right.x + 24, right.y + 142), size=BODY_SIZE, color=SUCCESS)
            draw_text(self.screen, "2: " + self.current_customer["negResponse"], (right.x + 24, right.y + 178), size=BODY_SIZE, color=DANGER)

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