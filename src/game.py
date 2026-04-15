# src/game.py

from __future__ import annotations

import math
import os
import random
import sys
import threading
import time
import urllib.request
import json
from typing import Dict, List, Optional

import pygame

from config.settings import *
from src.firebase_service import FirebaseService
from src.models import (
    PRODUCT_CATALOG,
    SHELF_LAYOUT,
    SECTION_PRODUCTS,
    STAFF_POOL,
    UPGRADES,
    AI_DIALOGUE_SYSTEM,
    CUSTOMER_ARCHETYPES,
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
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.running = True
        self._fullscreen = False

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
        self.selected_section = 0   # which section hitbox index was hit
        self.stock_section    = "all"  # "grocery"|"frozen"|"tech"|"deli"|"all" (zone Stock = all)
        self.overlay_anim = 0.0
        self.zone_rects = self._build_zones()

        # AI dialogue system
        self.dialogue_customer: Optional[Dict] = None   # customer being spoken to
        self.dialogue_line: str = ""                    # fetched line from AI
        self.dialogue_loading: bool = False             # spinner while fetching
        self.dialogue_response_pending: bool = False    # awaiting 1/2 key press
        self._dialogue_thread: Optional[threading.Thread] = None

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
        # All zones are positioned BELOW the shelf sections and away from each other.
        # Store floor: y=74..HEIGHT-36. Shelf content: y=156..~580.
        # Zones sit in the bottom strip (y ~610-730) or top-right corners clear of shelves.
        #
        # Break:    bottom-left  — clear of grocery (grocery cx ≈ 166)
        # Stock:    left side, mid-bottom
        # Prices:   top centre   — above deli section, narrow band
        # Checkout: bottom-right
        # Manager:  top-right    — above tech section
        return {
            "break":    pygame.Rect(40,  620, 160, 90),          # bottom-left, below grocery
            "stock":    pygame.Rect(40,  490, 160, 110),         # mid-left
            "prices":   pygame.Rect(580, 126, 140, 68),          # Frozen↔Deli corridor, centred at x=602
            "checkout": pygame.Rect(WIDTH - 260, 590, 220, 110), # bottom-right
            "manager":  pygame.Rect(WIDTH - 220, 80,  190, 90),  # top-right, above tech
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
        self.dialogue_customer = None
        self.dialogue_line = ""
        self.dialogue_loading = False
        self.dialogue_response_pending = False
        self.stock_section = "all"

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

            # F11 — toggle fullscreen on any scene
            if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                self._fullscreen = not self._fullscreen
                if self._fullscreen:
                    self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                else:
                    self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
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
            # ── dialogue response ───────────────────────────────────────────
            if self.dialogue_response_pending and self.dialogue_customer:
                if event.key == pygame.K_1:
                    self._resolve_dialogue(good=True)
                    return
                elif event.key == pygame.K_2:
                    self._resolve_dialogue(good=False)
                    return

            if event.key == pygame.K_ESCAPE:
                if self.dialogue_customer:
                    self.dialogue_customer = None
                    self.dialogue_line = ""
                    self.dialogue_response_pending = False
                elif self.overlay:
                    self.close_overlay()
                else:
                    self.save_current_game()
                    self.set_scene("menu")

            elif event.key == pygame.K_e and not self.overlay and not self.dialogue_customer:
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
                    self.hire_candidate(event.key - pygame.K_1)
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
                all_keys = list(PRODUCT_CATALOG.keys())
                num = len(all_keys)
                # Keys 1-9 apply suggestion for that product index
                for ki in range(min(9, num)):
                    if event.key == pygame.K_1 + ki:
                        self.apply_price_suggestion(ki)
                        break
                if event.key == pygame.K_a:
                    for idx in range(num):
                        self.apply_price_suggestion(idx, silent=True)
                    self.toasts.show("Applied all suggested prices.", SUCCESS)

            elif self.overlay == "stock":
                # Which categories are stockable in this section
                active_cats   = self._get_active_cats_for_section()
                all_keys_list = list(PRODUCT_CATALOG.keys())
                for ki in range(min(9, len(all_keys_list))):
                    if event.key == pygame.K_1 + ki:
                        product_key = all_keys_list[ki]
                        prod_cat    = PRODUCT_CATALOG[product_key]["category"]
                        # Match by category (handles secondary products like cake/frz_veg/laptop)
                        shelf_cat   = next(
                            (c for c in SHELF_LAYOUT if c == prod_cat),
                            None
                        )
                        if shelf_cat and (self.stock_section == "all" or shelf_cat in active_cats):
                            cat_idx = list(SHELF_LAYOUT.keys()).index(shelf_cat)
                            self.stock_shelf(cat_idx)
                        else:
                            section_name = PRODUCT_CATALOG[product_key].get("section", "its section").title()
                            self.toasts.show(f"Go to {section_name} section to stock this item.", WARNING)
                        break

    def try_interact(self):
        if not self.state:
            return
        player_rect = pygame.Rect(self.player.x - 16, self.player.y - 16, 32, 32)

        # ── zone interactions ─────────────────────────────────────────────
        for name, rect in self.zone_rects.items():
            if player_rect.colliderect(rect.inflate(46, 46)):
                if name == "break":
                    self.take_break()
                    return
                if name == "stock":
                    self.stock_section = "all"   # Stock zone = manage all storage
                self.open_overlay(name)
                return

        # ── shelf / section interactions ──────────────────────────────────
        # Maps hitbox index → which section products can be stocked here
        HITBOX_SECTION = {
            0: "grocery",   # snack
            1: "grocery",   # dairy
            2: "deli",      # bakery
            3: "grocery",   # produce
            4: "deli",      # deli
            5: "frozen",    # frozen
            6: "tech",      # tech
        }
        for i, rect in enumerate(self.shelf_hitboxes()):
            if player_rect.colliderect(rect.inflate(40, 40)):
                self.selected_section = i
                self.stock_section    = HITBOX_SECTION.get(i, "all")
                self.open_overlay("stock")
                return

        # ── customer dialogue ─────────────────────────────────────────────
        for customer in self.customers:
            if customer.get("phase") == "queued":
                cx = customer.get("draw_x", customer["x"])
                cy = customer.get("draw_y", customer["y"])
                cust_rect = pygame.Rect(cx - 20, cy - 30, 40, 60)
                if player_rect.colliderect(cust_rect.inflate(60, 60)):
                    self._start_dialogue(customer)
                    return

    def _start_dialogue(self, customer: Dict):
        """Initiate AI dialogue with a queued customer."""
        if self.dialogue_loading:
            return
        self.dialogue_customer = customer
        self.dialogue_line = ""
        self.dialogue_loading = True
        self.dialogue_response_pending = False

        mood    = customer.get("mood", "neutral")
        section = customer.get("section", "grocery")
        items   = customer.get("items", {})
        item_names = ", ".join(
            f"{PRODUCT_CATALOG.get(k, {}).get('name', k)} x{v}" for k, v in items.items()
        )

        system_prompt = (
            f"You are a {mood} customer shopping in the {section} section. "
            f"Your cart contains: {item_names}. "
            "Respond with ONE short sentence of natural in-character dialogue (max 18 words). "
            "No quotation marks, no stage directions, no emojis."
        )

        def fetch():
            try:
                # Load API key from environment (same .env as Firebase)
                from pathlib import Path
                from dotenv import load_dotenv
                load_dotenv(Path(__file__).resolve().parent.parent / ".env")
                api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()

                payload = json.dumps({
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 80,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": "Say something to the store manager."}],
                }).encode()
                req = urllib.request.Request(
                    "https://api.anthropic.com/v1/messages",
                    data=payload,
                    headers={
                        "Content-Type":    "application/json",
                        "x-api-key":       api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read())
                    line = data["content"][0]["text"].strip().strip('"')
                    self.dialogue_line = line
            except Exception:
                moods = {
                    "happy":   "Hi there! Lovely store you have here.",
                    "neutral": "Excuse me, can I get some help?",
                    "angry":   "Finally, someone! Where's the manager?",
                }
                self.dialogue_line = moods.get(mood, "Hello there.")
            finally:
                self.dialogue_loading = False
                self.dialogue_response_pending = True

        self._dialogue_thread = threading.Thread(target=fetch, daemon=True)
        self._dialogue_thread.start()

    def _resolve_dialogue(self, good: bool):
        """Apply effects of the player's dialogue response."""
        if not self.state or not self.dialogue_customer:
            return
        if good:
            self.state.satisfaction = min(100, self.state.satisfaction + 5)
            self.state.score += 20
            self.toasts.show("Great response! Reputation up.", SUCCESS)
        else:
            self.state.satisfaction = max(0, self.state.satisfaction - 6)
            self.state.score = max(0, self.state.score - 8)
            self.toasts.show("Poor response. Reputation dipped.", DANGER)
        self.dialogue_customer = None
        self.dialogue_line = ""
        self.dialogue_response_pending = False

    def update(self, dt: float):
        self.fader.update(dt)
        self.toasts.update(dt)
        self.update_animated_values(dt)

        if self.scene in ("auth", "menu"):
            self.auth_time += dt
            # drift particles upward and respawn
            for p in self.pixel_particles:
                p[1] -= p[4] * dt
                p[5] += dt
                if p[1] < -8 or p[5] > p[6]:
                    self._respawn_particle(p)

        # auth_time also drives game-scene animations (staff walk cycles, shimmer, etc.)
        if self.scene == "game":
            self.auth_time += dt

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
            self._update_staff_chars(dt)

            if not self.overlay:
                self.day_timer -= dt
                self.spawn_timer -= dt

                self.state.stress = min(100, int(self.state.stress + STRESS_TICK * dt))
                self.state.fatigue = min(100, int(self.state.fatigue + FATIGUE_TICK * dt))

                if self.state.stress > 80:
                    self.state.satisfaction = max(0, self.state.satisfaction - 1)

                self.update_customers(dt)

                # Dynamic customer cap — fewer customers allowed near closing time
                day_frac_cap = 1.0 - max(0.0, min(1.0,
                    self.day_timer / max(1, DAY_LENGTH_SECONDS)))
                import math as _math2
                effective_max = max(2, int(MAX_CUSTOMERS * (
                    0.40 + 0.60 * _math2.sin(_math2.pi * day_frac_cap))))

                if self.spawn_timer <= 0 and len(self.customers) < effective_max:
                    self.spawn_customer()

                    # ── day/night traffic curve ───────────────────────────
                    # day_frac: 0.0=dawn, 0.5=midday peak, 1.0=closing night
                    day_frac = 1.0 - max(0.0, min(1.0,
                        self.day_timer / max(1, DAY_LENGTH_SECONDS)))

                    # Bell curve peaks at midday (frac=0.5), quiet at dawn/dusk.
                    # traffic_mul: 0.4 (night/dawn) → 1.0 (midday peak)
                    # Uses a sine arch: sin(frac * π) gives 0 at 0&1, 1 at 0.5
                    import math as _math
                    traffic_mul = 0.40 + 0.60 * _math.sin(_math.pi * day_frac)

                    # Base interval: shorter = more frequent spawns
                    base = random.uniform(CUSTOMER_SPAWN_MIN, CUSTOMER_SPAWN_MAX)

                    # Divide base interval by traffic_mul:
                    #   midday (mul=1.0) → normal rate
                    #   dawn/night (mul=0.4) → interval 2.5× longer = fewer customers
                    interval = base / max(0.1, traffic_mul)

                    # Promo boost halves the interval on top of traffic curve
                    if time.time() < self.state.popularity_boost_until:
                        interval *= 0.65

                    # Hard floor so customers never spam faster than 3s even at peak
                    self.spawn_timer = max(3.0, interval)

                if self.day_timer <= 0:
                    self.end_day()

            self.sync_display_values()

    def _update_staff_chars(self, dt: float):
        """Animate hired staff on the game floor — patrol aisles, idle sway, task pauses."""
        if not self.state:
            return

        # Game floor bounds (must match draw_store_map geometry)
        floor_y_top    = 74 + 52 + 40    # CONTENT_Y + a little padding
        floor_y_bottom = HEIGHT - 110 - 50  # floor.bottom - margin

        # Per-staff patrol config: (y_min, y_max, patrol_speed, idle_sway_amp)
        # EMP patrols grocery/frozen corridor; TRN patrols deli/frozen; CSH stays near register
        patrol_cfg = [
            (floor_y_top, floor_y_bottom,       62,  3.0),   # EMP — full aisle patrol
            (floor_y_top, floor_y_bottom - 80,  48,  2.5),   # TRN — slightly shorter range
            (floor_y_bottom - 90, floor_y_bottom, 8,  5.0),  # CSH — register idle sway only
        ]

        staff_hired = len(self.state.staff)

        for idx, ch in enumerate(self._preview_chars):
            if staff_hired < (idx + 1):
                continue   # not hired yet, skip

            cfg = patrol_cfg[idx % len(patrol_cfg)]
            y_min, y_max, speed, sway_amp = cfg

            # Always tick walk_phase for animation even while paused/idle
            ch["walk_phase"] += dt * 8.0

            # Initialise y position on first game frame
            if ch["y"] == 0.0:
                ch["y"] = float(y_min + (y_max - y_min) * ch["y_frac"])
                ch["vy"] = 1.0 if idx % 2 == 0 else -1.0

            if ch["pause_t"] > 0:
                # ── IDLE / TASK pause ─────────────────────────────────────
                # Gentle idle bob: tiny y oscillation so they never look frozen
                ch["y"] += math.sin(ch["walk_phase"] * 0.4) * sway_amp * dt
                ch["y"]  = max(y_min, min(y_max, ch["y"]))
                ch["pause_t"] -= dt
            else:
                # ── PATROL ────────────────────────────────────────────────
                if ch["vy"] == 0.0:
                    ch["vy"] = 1.0

                ch["y"] += ch["vy"] * speed * dt

                # Bounce at patrol bounds with a randomised pause (simulates stopping to work)
                if ch["y"] >= y_max:
                    ch["y"]       = float(y_max)
                    ch["vy"]      = -abs(ch["vy"])
                    ch["pause_t"] = random.uniform(0.8, 2.2)   # longer pause = "doing a task"
                elif ch["y"] <= y_min:
                    ch["y"]       = float(y_min)
                    ch["vy"]      = abs(ch["vy"])
                    ch["pause_t"] = random.uniform(0.6, 1.8)

                # Occasional spontaneous direction flip (looks like noticing something)
                if random.random() < 0.004:
                    ch["vy"]     *= -1
                    ch["pause_t"] = random.uniform(0.3, 0.9)

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
        WALK_SPEED = 90.0  # px/s

        for customer in self.customers:
            # Patience only counts down while waiting at the checkout counter
            if customer.get("phase") == "queued":
                customer["patience"] -= 10 * dt
            customer["alpha"] = min(255, customer.get("alpha", 0) + int(255 * dt * CUSTOMER_FADE_SPEED))
            customer["walk_phase"] = customer.get("walk_phase", 0.0) + dt * 8.0

            if customer["patience"] <= 0:
                self.state.satisfaction = max(0, self.state.satisfaction - 7)
                continue

            phase = customer.get("phase", "queued")
            dx_pos = customer.get("draw_x", customer["x"])
            dy_pos = customer.get("draw_y", customer["y"])

            if phase == "enter":
                # Walk from entrance upward to aisle corridor x
                ax = customer["aisle_x"]
                # first move x toward aisle, then walk up
                if abs(dx_pos - ax) > 8:
                    dx_pos += math.copysign(WALK_SPEED * dt, ax - dx_pos)
                    customer["vy"] = 0
                else:
                    dx_pos = ax
                    dy_pos -= WALK_SPEED * dt
                    customer["vy"] = -1
                customer["draw_x"] = dx_pos
                customer["draw_y"] = dy_pos
                if dy_pos <= customer["aisle_top_y"]:
                    customer["phase"] = "browse"
                    customer["browse_timer"] = random.uniform(1.5, 3.5)

            elif phase == "browse":
                # Wander slightly in the aisle for browse_timer seconds
                customer["browse_timer"] = customer.get("browse_timer", 1.0) - dt
                # gentle side sway
                dx_pos += math.sin(customer["walk_phase"] * 0.5) * 12 * dt
                customer["draw_x"] = dx_pos
                if customer["browse_timer"] <= 0:
                    customer["phase"] = "head_to_checkout"
                    customer["vy"] = 1

            elif phase == "head_to_checkout":
                # Move toward checkout queue position at constant speed
                tx = customer["queue_x"]
                ty = customer["queue_y"]
                dist_x = tx - dx_pos
                dist_y = ty - dy_pos
                dist = math.sqrt(dist_x ** 2 + dist_y ** 2)
                if dist > 8:
                    step = WALK_SPEED * dt
                    dx_pos += dist_x / dist * step
                    dy_pos += dist_y / dist * step
                    customer["vy"] = 1 if dist_y > 0 else -1
                else:
                    dx_pos = tx
                    dy_pos = ty
                    customer["phase"] = "queued"
                customer["draw_x"] = dx_pos
                customer["draw_y"] = dy_pos

            else:  # queued — stay in queue position
                customer["draw_x"] = customer["queue_x"]
                customer["draw_y"] = customer["queue_y"]
                customer["vy"] = 0

            updated.append(customer)

        self.customers = updated

        if self.customers and self.current_customer is None:
            self.current_customer = self.customers[0]
        if self.current_customer and self.current_customer not in self.customers:
            self.current_customer = self.customers[0] if self.customers else None

    def spawn_customer(self):
        customer_obj = random_customer(self.next_customer_id, self.state.prices, self.state.demand)
        self.next_customer_id += 1

        # Queue position at checkout (right side)
        row = len(self.customers)
        queue_x = WIDTH - 210 + (row % 2) * 52
        queue_y = HEIGHT - 180 - row * 58

        # Customer enters from bottom-center (entrance mat) and walks to an aisle, then checkout
        floor = pygame.Rect(28, 74, WIDTH - 56, HEIGHT - 110)
        floor_y = floor.y + 52
        entrance_x = floor.centerx + random.randint(-60, 60)
        entrance_y = floor.bottom - 30

        # Pick a random aisle corridor x (between sections)
        corridor_fracs = [0.20, 0.42, 0.62]
        chosen_frac = random.choice(corridor_fracs)
        aisle_x = floor.x + int(floor.width * chosen_frac)
        aisle_top_y = floor_y + 50

        payload = {
            "id": customer_obj.id,
            "mood": customer_obj.mood,
            "patience": customer_obj.patience,
            "items": customer_obj.items,
            "section": customer_obj.section,
            "complaint": customer_obj.complaint,
            "expected_total": customer_obj.expected_total,
            "pay_with": customer_obj.pay_with,
            "cash_given": customer_obj.cash_given,
            "alpha": 0,
            # walk path state
            "phase": "enter",
            "draw_x": float(entrance_x),
            "draw_y": float(entrance_y),
            "aisle_x": float(aisle_x),
            "aisle_top_y": float(aisle_top_y),
            "queue_x": float(queue_x),
            "queue_y": float(queue_y),
            "walk_phase": random.uniform(0, 6.28),
            "vy": 1.0,
            "x": queue_x,
            "y": queue_y,
            "target_x": queue_x,
        }
        self.customers.append(payload)

    def shelf_hitboxes(self):
        """
        Returns 7 interaction rects — one per SHELF_LAYOUT category.
        Positions match draw_store_map geometry:
          floor = Rect(28, 74, WIDTH-56, HEIGHT-110)
          floor_y = 74 + 52 = 126  (below windows)
          CONTENT_Y = 126 + 30 = 156

        Sections:
          [0] snack/chips   → SEC_GROCERY_CX  = floor.x + floor.w*0.10
          [1] dairy/milk    → SEC_GROCERY_CX  (same unit, second column implicit)
          [2] bakery/bread  → SEC_DELI_CX     = floor.x + floor.w*0.53
          [3] produce/apple → SEC_GROCERY_CX  (grocery shelf, right side)
          [4] deli          → SEC_DELI_CX
          [5] frozen        → SEC_FROZEN_CX   = floor.x + floor.w*0.30
          [6] tech          → SEC_TECH_CX     = floor.x + floor.w*0.74
        """
        fx  = 28
        fw  = WIDTH - 56
        fy  = 74 + 52 + 30   # CONTENT_Y

        grocery_cx = fx + int(fw * 0.10)
        frozen_cx  = fx + int(fw * 0.30)
        deli_cx    = fx + int(fw * 0.53)
        tech_cx    = fx + int(fw * 0.74)

        hw = 100   # hitbox width
        hh = 120   # hitbox height

        return [
            pygame.Rect(grocery_cx - hw//2,      fy, hw, hh),   # 0 snack
            pygame.Rect(grocery_cx - hw//2 + 60, fy, hw, hh),   # 1 dairy
            pygame.Rect(deli_cx - hw//2,         fy, hw, hh),   # 2 bakery
            pygame.Rect(grocery_cx + hw//2 - 20, fy, hw, hh),   # 3 produce
            pygame.Rect(deli_cx - hw//2 + 10,    fy + 80, hw, hh),  # 4 deli
            pygame.Rect(frozen_cx - 85,          fy, 170, hh),  # 5 frozen (3 fridges)
            pygame.Rect(tech_cx - 120,           fy, 240, hh),  # 6 tech (3 aisles)
        ]

    # ---------- gameplay actions ----------
    def _get_active_cats_for_section(self) -> set:
        """Return the shelf categories the player can stock in the current section."""
        mapping = {
            "grocery": {"snack", "dairy", "produce"},
            "deli":    {"bakery", "deli"},
            "frozen":  {"frozen"},
            "tech":    {"tech"},
            "all":     set(SHELF_LAYOUT.keys()),
        }
        return mapping.get(self.stock_section, set(SHELF_LAYOUT.keys()))

    def stock_shelf(self, idx: int):
        if not self.state:
            return

        categories = list(SHELF_LAYOUT.keys())
        if idx >= len(categories):
            return
        category = categories[idx]
        capacity = SHELF_CAPACITY + (8 if self.state.upgrades.get("shelves") else 0)

        if self.state.shelves.get(category, 0) >= capacity:
            self.toasts.show(f"{category.title()} shelf is already full.", WARNING)
            return

        # All products that share this shelf category (e.g. frz_fruit/frz_veg/frz_protein all → frozen)
        section_products = [k for k, v in PRODUCT_CATALOG.items() if v["category"] == category]
        if not section_products:
            section_products = [SHELF_LAYOUT[category]]

        # Stock from whichever product in this category has storage available
        for product_key in section_products:
            available = self.state.storage.get(product_key, 0)
            if available <= 0:
                continue
            space = capacity - self.state.shelves.get(category, 0)
            moved = min(4, available, space)
            if moved <= 0:
                continue
            self.state.storage[product_key]             -= moved
            self.state.shelves[category]                 = self.state.shelves.get(category, 0) + moved
            self.state.score                            += moved * 2
            self.state.satisfaction                      = min(100, self.state.satisfaction + 1)
            self.toasts.show(f"+ Restocked: {moved}× {PRODUCT_CATALOG[product_key]['name']}", SUCCESS)
            return

        names = ", ".join(PRODUCT_CATALOG[k]["name"] for k in section_products)
        self.toasts.show(f"No {names} left in storage.", DANGER)

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

        # Verify shelf stock exists for every item
        for product_key, qty in self.current_customer["items"].items():
            cat = PRODUCT_CATALOG[product_key]["category"]
            # Find which SHELF_LAYOUT category covers this product
            shelf_cat = next((c for c, pk in SHELF_LAYOUT.items() if pk == product_key or
                              PRODUCT_CATALOG[product_key]["category"] == c), None)
            # Fallback: find any shelf category that holds this product type
            if shelf_cat is None:
                shelf_cat = cat
            if self.state.shelves.get(shelf_cat, 0) < qty:
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
            cat = PRODUCT_CATALOG[product_key]["category"]
            shelf_cat = next((c for c, pk in SHELF_LAYOUT.items()
                              if PRODUCT_CATALOG[product_key]["category"] == c), cat)
            if shelf_cat in self.state.shelves:
                self.state.shelves[shelf_cat] = max(0, self.state.shelves[shelf_cat] - qty)
            self.state.demand[product_key] = min(2.2, self.state.demand.get(product_key, 1.0) + 0.06 * qty)

        self.state.money        += total
        self.state.sales_today  += total
        self.state.customers_served += 1
        self.state.score        += int(total * 4)
        self.state.satisfaction  = min(100, self.state.satisfaction + 2)

        transaction = {
            "total_amount":     round(total, 2),
            "transaction_time": time.time(),
            "items":            self.current_customer["items"],
            "pay_with":         self.current_customer["pay_with"],
        }
        try:
            self.firebase.add_transaction(self.state.uid, self.session.id_token, transaction)
        except Exception:
            pass

        self.customers = [c for c in self.customers if c["id"] != self.current_customer["id"]]
        self.current_customer = self.customers[0] if self.customers else None
        self.checkout_change_input = ""
        self.toasts.show(f"+ ${total:.2f} Sale complete!", SUCCESS)
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
        all_keys = list(PRODUCT_CATALOG.keys())
        if idx >= len(all_keys):
            return
        product_key = all_keys[idx]
        current     = self.state.prices[product_key]
        cat         = PRODUCT_CATALOG[product_key]["category"]
        # Use the category's shelf stock if it maps to one; else use storage only
        shelf_stock = self.state.shelves.get(cat, 0)
        stock       = self.state.storage.get(product_key, 0) + shelf_stock
        suggested   = price_suggestion(current, stock, self.state.demand.get(product_key, 1.0))
        self.state.prices[product_key] = suggested
        if suggested > PRODUCT_CATALOG[product_key]["base_price"] * 1.7:
            self.state.satisfaction = max(0, self.state.satisfaction - 5)
        if not silent:
            self.toasts.show(
                f"Price updated: {PRODUCT_CATALOG[product_key]['name']} → ${suggested:.2f}", SUCCESS
            )

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
        """Staff-only ambient characters. Customers 0-2 are removed — live customers
        are spawned dynamically. Only EMP/TRN/CSH appear, gated on hire count."""
        def make_char(x_frac, y_frac, vy, body_col, hat_col=None, label="", carrying=False):
            vy = vy if vy != 0.0 else 1.0
            return {
                "x_frac": float(x_frac), "x": 0.0, "y": 0.0, "vy": float(vy),
                "walk_phase": random.uniform(0, math.pi * 2),
                "body_col": body_col, "hat_col": hat_col, "label": label,
                "carrying": carrying, "pause_t": random.uniform(0.0, 0.6),
                "y_frac": float(y_frac), "moving": True,
            }

        # Staff chars only — rendered in preview AND in game (gated on hire count)
        self._preview_chars = [
            make_char(0.19, 0.80, -1.0, (60, 160, 80),  hat_col=(30, 100, 50),  label="EMP", carrying=True),
            make_char(0.41, 0.30,  1.0, (220, 200, 60), hat_col=(180, 160, 20), label="TRN"),
            make_char(0.91, 0.82,  0.3, (80, 100, 210), hat_col=(40,  60, 160), label="CSH"),
        ]
        self._char_cfg = [
            (0.20, 0.86, 58),   # EMP
            (0.20, 0.86, 50),   # TRN
            (0.78, 0.88,  9),   # CSH — tiny sway near register
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
        self.draw_dialogue_bubble()

        if self.overlay:
            self.draw_overlay()

    def draw_dialogue_bubble(self):
        """Render the AI speech bubble above the active customer."""
        if not self.dialogue_customer:
            return

        cx = int(self.dialogue_customer.get("draw_x", self.dialogue_customer["x"]))
        cy = int(self.dialogue_customer.get("draw_y", self.dialogue_customer["y"]))

        bubble_w = 340
        bubble_h = 110
        bx = max(10, min(WIDTH - bubble_w - 10, cx - bubble_w // 2))
        by = cy - bubble_h - 50

        # Shadow
        sh = pygame.Surface((bubble_w + 12, bubble_h + 12), pygame.SRCALPHA)
        pygame.draw.rect(sh, (0, 0, 0, 60), sh.get_rect(), border_radius=20)
        self.screen.blit(sh, (bx - 6, by + 6))

        # Bubble body
        bubble = pygame.Surface((bubble_w, bubble_h), pygame.SRCALPHA)
        pygame.draw.rect(bubble, (240, 248, 255, 240), bubble.get_rect(), border_radius=18)
        pygame.draw.rect(bubble, (*ACCENT, 180), bubble.get_rect(), 2, border_radius=18)
        self.screen.blit(bubble, (bx, by))

        # Tail
        tail_pts = [(cx - 8, by + bubble_h), (cx + 8, by + bubble_h), (cx, by + bubble_h + 18)]
        pygame.draw.polygon(self.screen, (240, 248, 255), tail_pts)
        pygame.draw.lines(self.screen, ACCENT, False, tail_pts[:2], 2)

        # Mood badge
        mood_col = SUCCESS if self.dialogue_customer.get("mood") == "happy" \
                   else DANGER if self.dialogue_customer.get("mood") == "angry" else WARNING
        mood_txt = self.dialogue_customer.get("mood", "neutral").upper()
        draw_badge(self.screen, mood_txt, bx + 10, by + 8, color=mood_col)

        if self.dialogue_loading:
            dots = "." * (1 + int(self.auth_time * 3) % 3)
            draw_text(self.screen, f"Thinking{dots}", (bx + 16, by + 44),
                      size=BODY_SIZE, color=TEXT_MUTED)
        elif self.dialogue_line:
            # Word-wrap the line
            words = self.dialogue_line.split()
            lines, cur = [], ""
            for w in words:
                test = (cur + " " + w).strip()
                if get_font(BODY_SIZE).size(test)[0] < bubble_w - 28:
                    cur = test
                else:
                    lines.append(cur); cur = w
            if cur:
                lines.append(cur)
            for li, line in enumerate(lines[:3]):
                draw_text(self.screen, line, (bx + 16, by + 44 + li * 22), size=BODY_SIZE, color=TEXT_DARK)

        if self.dialogue_response_pending:
            draw_text(self.screen, "1 = Great response   2 = Poor response",
                      (bx + 16, by + bubble_h - 22), size=SMALL_SIZE, color=TEXT_MUTED)

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

        def draw_overhead_sign(cx, sign_y, text, bg_col, fill_ratio=None, text_col=(255, 245, 200)):
            """Draw a hanging aisle sign. If fill_ratio is given, render a compact
            stock bar to the right of the sign text, flush inside the same pill."""
            lbl = font_sign.render(text, True, text_col)
            pad = 9
            # Base sign width = text only; if stock bar wanted, widen to fit it
            bar_w_px = 48 if fill_ratio is not None else 0
            bar_gap  = 6  if fill_ratio is not None else 0
            sw = lbl.get_width() + pad * 2 + bar_w_px + bar_gap
            sh = lbl.get_height() + 6
            sx = cx - sw // 2
            # hanging wire
            pygame.draw.line(self.screen, (120, 120, 130), (cx, sign_y - 10), (cx, sign_y), 1)
            # sign body
            pygame.draw.rect(self.screen, bg_col, (sx, sign_y, sw, sh), border_radius=4)
            pygame.draw.rect(self.screen, tuple(max(0, v - 40) for v in bg_col),
                             (sx, sign_y, sw, sh), 2, border_radius=4)
            self.screen.blit(lbl, (sx + pad, sign_y + 3))

            # stock bar embedded in the sign
            if fill_ratio is not None:
                bx = sx + pad + lbl.get_width() + bar_gap
                by = sign_y + sh // 2 - 4
                bh = 8
                # track
                pygame.draw.rect(self.screen, (0, 0, 0, 60),
                                 (bx, by, bar_w_px, bh), border_radius=4)
                # fill colour: green > yellow > red
                if fill_ratio > 0.5:
                    fc = (80, 210, 100)
                elif fill_ratio > 0.2:
                    fc = (255, 185, 40)
                else:
                    fc = (220, 60, 60)
                filled = max(2, int(bar_w_px * fill_ratio))
                pygame.draw.rect(self.screen, fc,
                                 (bx, by, filled, bh), border_radius=4)
                # track border
                pygame.draw.rect(self.screen, tuple(max(0, v - 50) for v in bg_col),
                                 (bx, by, bar_w_px, bh), 1, border_radius=4)

        def draw_shelf_unit(sx, sy, sw, sh, products, layers=3):
            pygame.draw.rect(self.screen, WOOD, (sx, sy, sw, sh), border_radius=5)
            pygame.draw.rect(self.screen, tuple(max(0, v - 25) for v in WOOD), (sx + sw - 6, sy, 6, sh), border_radius=5)
            layer_h = sh // (layers + 1)
            for li in range(layers):
                plank_y = sy + layer_h * (li + 1)
                pygame.draw.rect(self.screen, SHELF, (sx + 4, plank_y, sw - 10, 8), border_radius=2)
                pygame.draw.rect(self.screen, tuple(max(0, v - 20) for v in SHELF), (sx + 4, plank_y + 7, sw - 10, 2))
                slot_w = max(1, (sw - 12) // max(1, len(products)))
                for pi, (pcol, _) in enumerate(products):
                    shimmer = int(math.sin(t * 2.0 + sx * 0.02 + pi + li) * 8)
                    c = tuple(min(255, v + shimmer) for v in pcol)
                    pygame.draw.rect(self.screen, c, (sx + 6 + pi * slot_w, plank_y - 19, slot_w - 1, 19), border_radius=2)
                    pygame.draw.rect(self.screen, (255, 250, 180), (sx + 6 + pi * slot_w, plank_y - 3, slot_w - 1, 3))

        # ── section layout (4 sections across the store width) ────────────
        iw = floor.width
        ix = floor.x
        SIGN_Y       = floor_y + 4
        SHELF_STOP_Y = floor.bottom - 130
        CONTENT_Y    = floor_y + 30

        SEC_GROCERY_CX = ix + int(iw * 0.10)
        SEC_FROZEN_CX  = ix + int(iw * 0.30)
        SEC_DELI_CX    = ix + int(iw * 0.53)
        SEC_TECH_CX    = ix + int(iw * 0.74)
        capacity = SHELF_CAPACITY + (8 if self.state.upgrades.get("shelves") else 0)

        def _section_fill(categories):
            """Average fill ratio across a list of shelf categories."""
            vals = [min(1.0, self.state.shelves.get(c, 0) / max(1, capacity))
                    for c in categories]
            return sum(vals) / max(1, len(vals))

        grocery_fill = _section_fill(["snack", "dairy", "produce"])
        frozen_fill  = _section_fill(["frozen"])
        deli_fill    = _section_fill(["bakery", "deli"])
        tech_fill    = _section_fill(["tech"])

        draw_overhead_sign(SEC_GROCERY_CX, SIGN_Y, "GROCERY", (60, 120, 60),   fill_ratio=grocery_fill)
        draw_overhead_sign(SEC_FROZEN_CX,  SIGN_Y, "FROZEN",  (30, 90, 160),   fill_ratio=frozen_fill)
        draw_overhead_sign(SEC_DELI_CX,    SIGN_Y, "DELI",    (160, 80, 40),   fill_ratio=deli_fill)
        draw_overhead_sign(SEC_TECH_CX,    SIGN_Y, "TECH",    (40, 40, 100),   fill_ratio=tech_fill)

        # ── SECTION 1: Grocery shelves (live game state) ───────────────────
        grocery_products = [
            ((245, 180, 80), "chips"), ((195, 225, 255), "milk"),
            ((214, 169, 111), "bread"), ((232, 86, 86), "apple"),
        ]
        shelf_w  = 56
        grocery_h = SHELF_STOP_Y - CONTENT_Y
        draw_shelf_unit(SEC_GROCERY_CX - shelf_w // 2, CONTENT_Y, shelf_w, grocery_h, grocery_products, layers=4)

        # ── SECTION 2: Frozen refrigerators ───────────────────────────────
        frozen_defs = [
            ((160, 210, 255), "Frz.Fruit"),
            ((180, 240, 200), "Frz.Veg"),
            ((255, 200, 180), "Frz.Prot"),
        ]
        fridge_w, fridge_h = 50, SHELF_STOP_Y - CONTENT_Y
        fridge_gap = 6
        frozen_x0 = SEC_FROZEN_CX - (len(frozen_defs) * (fridge_w + fridge_gap)) // 2 + fridge_gap
        for fi, (fcol, fname) in enumerate(frozen_defs):
            fx = frozen_x0 + fi * (fridge_w + fridge_gap)
            fy = CONTENT_Y
            CASE_COL  = (44, 74, 108)
            CASE_DARK = (30, 52, 80)
            pygame.draw.rect(self.screen, CASE_COL, (fx, fy, fridge_w, fridge_h), border_radius=5)
            pygame.draw.rect(self.screen, CASE_DARK, (fx, fy, 5, fridge_h), border_radius=5)
            pygame.draw.rect(self.screen, CASE_DARK, (fx + fridge_w - 5, fy, 5, fridge_h), border_radius=5)
            pygame.draw.rect(self.screen, (60, 100, 145), (fx, fy, fridge_w, 8), border_radius=5)
            pygame.draw.rect(self.screen, (30, 50, 75), (fx, fy + fridge_h - 8, fridge_w, 8), border_radius=3)
            GLASS_MARGIN = 6
            gx2, gy2 = fx + GLASS_MARGIN, fy + 10
            gw2, gh2 = fridge_w - GLASS_MARGIN * 2, fridge_h - 22
            glass_surf = pygame.Surface((gw2, gh2), pygame.SRCALPHA)
            glass_surf.fill((200, 235, 255, 55))
            self.screen.blit(glass_surf, (gx2, gy2))
            pygame.draw.rect(self.screen, (55, 90, 130), (gx2, gy2, gw2, gh2), 2, border_radius=3)
            item_rows = 4
            row_h = (gh2 - 8) // item_rows
            for ri in range(item_rows):
                ry2 = gy2 + 4 + ri * row_h
                pygame.draw.rect(self.screen, (60, 100, 140), (gx2 + 2, ry2 + row_h - 4, gw2 - 4, 4))
                shimmer = int(math.sin(t * 1.8 + fi * 2 + ri) * 6)
                ic = tuple(min(255, v + shimmer) for v in fcol)
                pygame.draw.rect(self.screen, ic, (gx2 + 3, ry2 + 2, gw2 - 6, row_h - 8), border_radius=2)
                pygame.draw.rect(self.screen, tuple(max(0, v - 40) for v in ic), (gx2 + 3, ry2 + 2, gw2 - 6, row_h - 8), 1, border_radius=2)
                pygame.draw.rect(self.screen, (255, 250, 180), (gx2 + 3, ry2 + row_h - 9, gw2 - 6, 4))
                item_lbl = font_sec.render(fname[:4], True, (40, 40, 60))
                self.screen.blit(item_lbl, (gx2 + max(1, gw2 // 2 - item_lbl.get_width() // 2), ry2 + 3))
            hx = fx + fridge_w - GLASS_MARGIN - 4
            pygame.draw.rect(self.screen, (180, 190, 200), (hx, fy + fridge_h // 2 - 20, 5, 40), border_radius=3)
            led_x, led_y = fx + 8, fy + 1
            pygame.draw.rect(self.screen, (10, 20, 35), (led_x, led_y, fridge_w - 16, 7), border_radius=2)
            temp_glow = int((math.sin(t * 2.0 + fi) + 1) * 4)
            pygame.draw.rect(self.screen, (0, min(255, 180 + temp_glow), 80), (led_x + 2, led_y + 1, 18, 5), border_radius=1)

        # ── SECTION 3: Deli counter ────────────────────────────────────────
        deli_w  = 82
        deli_x0 = SEC_DELI_CX - deli_w // 2
        BACK_H  = SHELF_STOP_Y - CONTENT_Y
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
                pygame.draw.ellipse(self.screen, tc, (deli_x0 + 6 + tpi * 24, ty2 - 14, 22, 13))
        COUNTER_H = 58
        counter_y2 = CONTENT_Y + BACK_H - COUNTER_H - 2
        pygame.draw.rect(self.screen, (160, 130, 95), (deli_x0, counter_y2 + 20, deli_w, COUNTER_H), border_radius=5)
        pygame.draw.rect(self.screen, (170, 210, 245), (deli_x0 + 2, counter_y2, deli_w - 4, 24), border_radius=3)
        pygame.draw.rect(self.screen, (120, 175, 220), (deli_x0 + 2, counter_y2, deli_w - 4, 24), 2, border_radius=3)
        for di, (dcol, dname) in enumerate(deli_items):
            ddx = deli_x0 + 6 + di * 24
            pygame.draw.ellipse(self.screen, dcol, (ddx, counter_y2 + 5, 20, 13))
            dlbl = get_font(8).render(dname, True, (70, 50, 30))
            self.screen.blit(dlbl, (ddx + 10 - dlbl.get_width() // 2, counter_y2 + 20))
        pygame.draw.rect(self.screen, (200, 175, 130), (deli_x0, counter_y2 + 18, deli_w, 6), border_radius=2)

        # ── SECTION 4: Tech aisles ─────────────────────────────────────────
        TECH_STOP_Y  = SHELF_STOP_Y - 60
        tech_aisle_h = TECH_STOP_Y - CONTENT_Y
        tech_aisles = [(-72, "AISLE A"), (0, "AISLE B"), (72, "AISLE C")]
        tech_device_rows = [
            ((55,  55,  68), (90,  170, 255), "PHONE",  14, 22),
            ((38,  38,  48), (130, 215, 255), "LAPTOP", 38, 24),
            ((175, 175, 195), (70, 190, 255), "ROUTER", 28, 17),
        ]
        for ai, (ax_off, alabel) in enumerate(tech_aisles):
            shelf_ax = SEC_TECH_CX + ax_off
            shelf_aw = 54
            pygame.draw.rect(self.screen, WOOD, (shelf_ax - shelf_aw // 2, CONTENT_Y, shelf_aw, tech_aisle_h), border_radius=4)
            pygame.draw.rect(self.screen, tuple(max(0, v - 25) for v in WOOD), (shelf_ax + shelf_aw // 2 - 6, CONTENT_Y, 6, tech_aisle_h), border_radius=4)
            num_rows = len(tech_device_rows)
            row_zone_h = tech_aisle_h // (num_rows + 1)
            for ri, (bcol, scol, dname, dw, dh) in enumerate(tech_device_rows):
                plank_y = CONTENT_Y + row_zone_h * (ri + 1)
                pygame.draw.rect(self.screen, SHELF, (shelf_ax - shelf_aw // 2 + 3, plank_y, shelf_aw - 6, 7), border_radius=2)
                pygame.draw.rect(self.screen, tuple(max(0, v - 20) for v in SHELF), (shelf_ax - shelf_aw // 2 + 3, plank_y + 6, shelf_aw - 6, 2))
                tx2 = shelf_ax - dw // 2
                ty2 = plank_y - dh - 4
                sglow = int((math.sin(t * 2.8 + ai * 1.1 + ri * 0.9) + 1) * 12)
                halo_surf = pygame.Surface((dw + 10, dh + 10), pygame.SRCALPHA)
                pygame.draw.rect(halo_surf, (*scol, 35 + sglow), halo_surf.get_rect(), border_radius=5)
                self.screen.blit(halo_surf, (tx2 - 5, ty2 - 5))
                pygame.draw.rect(self.screen, bcol, (tx2, ty2, dw, dh), border_radius=3)
                pygame.draw.rect(self.screen, (20, 20, 30), (tx2 + 2, ty2 + 2, dw - 4, dh - 5), border_radius=2)
                sc2 = tuple(min(255, v + sglow) for v in scol)
                pygame.draw.rect(self.screen, sc2, (tx2 + 3, ty2 + 3, dw - 6, dh - 8), border_radius=2)
                for bar_i in range(2):
                    bar_y2 = ty2 + 5 + bar_i * 5
                    bar_col = (255, 255, 255) if (int(t * 2 + bar_i + ri) % 4 < 2) else (180, 220, 255)
                    pygame.draw.rect(self.screen, bar_col, (tx2 + 4, bar_y2, dw - 10, 2), border_radius=1)
                pygame.draw.rect(self.screen, tuple(max(0, v - 20) for v in bcol), (tx2, ty2, dw, dh), 1, border_radius=3)
                dlbl = font_sec.render(dname, True, (190, 200, 220))
                self.screen.blit(dlbl, (tx2 + dw // 2 - dlbl.get_width() // 2, plank_y + 8))
            pygame.draw.rect(self.screen, (255, 250, 180), (shelf_ax - shelf_aw // 2 + 3, TECH_STOP_Y - 10, shelf_aw - 6, 6), border_radius=2)

        # ── checkout register (bottom-right, matching preview) ─────────────
        counter_rect = pygame.Rect(floor.right - 175, floor.bottom - 108, 130, 72)
        pygame.draw.rect(self.screen, REGISTER, counter_rect, border_radius=7)
        pygame.draw.rect(self.screen, (55, 65, 75), counter_rect, 2, border_radius=7)
        scr_glow = int((math.sin(t * 3.0) + 1) * 18)
        pygame.draw.rect(self.screen, (0, min(255, 150 + scr_glow), min(255, 55 + scr_glow)),
                         (counter_rect.x + 7, counter_rect.y + 7, 44, 26), border_radius=3)
        laser_y = counter_rect.y + 40 + int(math.sin(t * 6) * 5)
        pygame.draw.line(self.screen, (255, 60, 60),
                         (counter_rect.x + 54, laser_y), (counter_rect.right - 7, laser_y), 2)
        belt_x = counter_rect.x + 54
        for stripe in range(5):
            sx2 = belt_x + stripe * 12 + int(t * 18) % 12
            pygame.draw.line(self.screen, (70, 75, 80),
                             (sx2, counter_rect.y + 34), (sx2, counter_rect.y + 56), 2)

        # ── cart corral (bottom-left corner, matching preview) ─────────────
        STACK_X = floor.x + 10
        STACK_Y = floor.bottom - 90

        def draw_single_cart(cx, cy, item_col=None, small=False):
            s  = 0.62 if small else 1.0
            bw = int(38 * s)
            bh = int(24 * s)
            dp = int(10 * s)
            cx, cy = int(cx), int(cy)
            metal_mid = (148, 158, 170)
            metal_hi  = (200, 210, 218)
            metal_shd = (90,  98, 108)
            wheel_col = (42,  44,  54)
            wheel_hi  = (75,  80,  92)
            back_poly = [(cx + dp, cy - dp), (cx + bw + dp, cy - dp), (cx + bw, cy), (cx, cy)]
            pygame.draw.polygon(self.screen, metal_shd, back_poly)
            pygame.draw.polygon(self.screen, metal_mid, back_poly, 1)
            pygame.draw.rect(self.screen, metal_mid, (cx, cy, bw, bh), border_radius=2)
            grid_col = tuple(max(0, v - 28) for v in metal_mid)
            for wx in range(cx + int(9*s), cx + bw, int(9*s)):
                pygame.draw.line(self.screen, grid_col, (wx, cy + 2), (wx, cy + bh - 2), 1)
            for wy in range(cy + int(8*s), cy + bh, int(8*s)):
                pygame.draw.line(self.screen, grid_col, (cx + 2, wy), (cx + bw - 2, wy), 1)
            pygame.draw.rect(self.screen, metal_hi, (cx, cy, bw, int(3*s)), border_radius=1)
            side_poly = [(cx+bw, cy), (cx+bw+dp, cy-dp), (cx+bw+dp, cy-dp+bh), (cx+bw, cy+bh)]
            pygame.draw.polygon(self.screen, metal_shd, side_poly)
            pygame.draw.polygon(self.screen, metal_mid, side_poly, 1)
            hbw = int(16 * s); hbh = int(5 * s)
            hx2 = cx + bw - hbw - int(2*s) + dp; hy2 = cy - dp - hbh
            pygame.draw.rect(self.screen, metal_hi, (hx2, hy2, hbw, hbh), border_radius=2)
            pygame.draw.rect(self.screen, metal_mid, (hx2 + hbw - int(4*s), cy - dp, int(4*s), int(14*s)), border_radius=1)
            pygame.draw.rect(self.screen, metal_shd, (cx - int(3*s), cy + int(5*s), int(4*s), int(15*s)), border_radius=1)
            axle_y = cy + bh + int(2*s)
            pygame.draw.line(self.screen, metal_mid, (cx + int(3*s), axle_y), (cx + int(3*s), axle_y + int(8*s)), 2)
            pygame.draw.line(self.screen, metal_mid, (cx + bw - int(5*s), axle_y), (cx + bw - int(5*s), axle_y + int(8*s)), 2)
            wr = max(2, int(4 * s))
            wy2 = axle_y + int(8*s)
            for wxp in [cx + int(2*s), cx + int(7*s), cx + bw - int(8*s), cx + bw - int(3*s)]:
                pygame.draw.circle(self.screen, wheel_col, (wxp, wy2), wr)
                pygame.draw.circle(self.screen, wheel_hi,  (wxp, wy2), max(1, wr - 1))
                pygame.draw.circle(self.screen, metal_hi,  (wxp, wy2), max(1, wr - 2))

        for si in range(3):
            draw_single_cart(STACK_X + si * 6, STACK_Y - si * 3, small=True)
        cl = font_sec.render("CARTS", True, (140, 148, 158))
        self.screen.blit(cl, (STACK_X + 2, STACK_Y + 28))

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

        # ── gameplay shelf interaction hints (critical-low flash only — bars now on signs) ──
        labels = list(SHELF_LAYOUT.keys())
        for i, rect in enumerate(self.shelf_hitboxes()):
            category   = labels[i]
            capacity   = SHELF_CAPACITY + (8 if self.state.upgrades.get("shelves") else 0)
            qty        = self.state.shelves.get(category, 0)
            fill_ratio = min(1.0, qty / max(1, capacity))

            # Critical-low flash only
            if fill_ratio < 0.15:
                pulse_a = int(abs(math.sin(t * 4)) * 60)
                warn_surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                pygame.draw.rect(warn_surf, (*DANGER, pulse_a), warn_surf.get_rect(), border_radius=8)
                self.screen.blit(warn_surf, rect.topleft)

        # ── animated walk characters: customers always walk; staff only if hired ─
        def draw_person_walk_game(px_pos, py_pos, body_color, hat_color, label,
                                  carrying, walk_phase, facing_down, paused,
                                  skin_tone=(224, 190, 155), hair_color=(60, 40, 25),
                                  pant_color=(45, 50, 75), shoe_color=(32, 22, 16)):
            px_pos, py_pos = int(px_pos), int(py_pos)
            bob   = 0 if paused else int(math.sin(walk_phase * 2) * 2.2)
            swing = 0.0 if paused else math.sin(walk_phase)

            # ground shadow
            shadow_surf = pygame.Surface((34, 10), pygame.SRCALPHA)
            for sx in range(17):
                alpha = int(90 * (1 - (sx / 17) ** 1.6))
                pygame.draw.line(shadow_surf, (0, 0, 0, alpha), (17 - sx, 5), (17 + sx, 5), 1)
            self.screen.blit(shadow_surf, (px_pos - 17, py_pos + 22))

            # legs
            for li, (lx, lsw) in enumerate([(-4, swing), (3, -swing)]):
                depth = li == 0
                ly_extra = int(lsw * 8)
                leg_shade = tuple(max(0, v - (18 if depth else 0)) for v in pant_color)
                pygame.draw.rect(self.screen, leg_shade, (px_pos + lx - 1, py_pos + 8 + bob, 6, 7), border_radius=3)
                pygame.draw.rect(self.screen, leg_shade, (px_pos + lx, py_pos + 14 + bob + ly_extra, 5, 6), border_radius=2)
                shoe_x = px_pos + lx - (1 if facing_down else 0)
                shoe_y = py_pos + 19 + bob + ly_extra
                pygame.draw.rect(self.screen, shoe_color, (shoe_x, shoe_y, 8, 4), border_radius=2)

            # torso
            torso_x, torso_y = px_pos - 8, py_pos - 8 + bob
            pygame.draw.rect(self.screen, body_color, (torso_x, torso_y, 16, 17), border_radius=4)
            shadow_col = tuple(max(0, v - 38) for v in body_color)
            pygame.draw.rect(self.screen, shadow_col, (torso_x + 11, torso_y + 2, 4, 13), border_radius=2)

            # head
            pygame.draw.circle(self.screen, skin_tone, (px_pos, py_pos - 16 + bob), 7)
            # hat
            if hat_color:
                pygame.draw.rect(self.screen, hat_color, (px_pos - 7, py_pos - 27 + bob, 14, 8), border_radius=3)
                pygame.draw.rect(self.screen, hat_color, (px_pos - 9, py_pos - 21 + bob, 18, 3), border_radius=2)

            # role badge
            if label:
                lsurf = font_sec.render(label, True, (220, 230, 245))
                lw = lsurf.get_width()
                pill = pygame.Surface((lw + 8, 13), pygame.SRCALPHA)
                pygame.draw.rect(pill, (20, 22, 38, 180), pill.get_rect(), border_radius=6)
                self.screen.blit(pill, (px_pos - lw // 2 - 4, py_pos + 24))
                self.screen.blit(lsurf, (px_pos - lw // 2, py_pos + 26))

        # ── staff ambient characters (only shown when hired) ──────────────
        corridor_x_fracs = [0.20, 0.42, 0.90]
        game_char_xs = [floor.x + int(iw * f) for f in corridor_x_fracs]
        CHAR_DETAILS = [
            ((160,  95,  60), (18, 12,  8), (40, 48, 70), (24, 16, 12)),  # EMP
            ((210, 170, 130), (90, 55, 20), (50, 44, 35), (30, 22, 18)),  # TRN
            ((225, 190, 155), (60, 45, 30), (35, 38, 65), (25, 18, 14)),  # CSH
        ]
        staff_hired = len(self.state.staff) if self.state else 0
        for idx, ch in enumerate(self._preview_chars):
            if staff_hired < (idx + 1):
                continue
            ch_x = game_char_xs[idx % len(game_char_xs)]
            # Use live y updated by _update_staff_chars; clamp to floor bounds
            ch_y = max(floor_y + 40, min(floor.bottom - 50, ch["y"]))
            # paused = idle task stop; facing_down driven by direction of travel
            paused      = ch["pause_t"] > 0
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
        """Draw the player as a detailed store manager character (matching preview art style)."""
        t = self.auth_time
        px_pos = int(self.player.x)
        py_pos = int(self.player.y)

        keys = pygame.key.get_pressed()
        moving = any([keys[pygame.K_w], keys[pygame.K_s], keys[pygame.K_a], keys[pygame.K_d],
                      keys[pygame.K_UP], keys[pygame.K_DOWN], keys[pygame.K_LEFT], keys[pygame.K_RIGHT]])
        facing_down = self.velocity.y >= 0

        walk_phase = t * 8.0 if moving else 0.0
        bob   = int(math.sin(walk_phase * 2) * 2.2) if moving else 0
        swing = math.sin(walk_phase) if moving else 0.0
        a_swing = math.sin(walk_phase + math.pi) if moving else 0.0

        font_sec = get_font(10, bold=True)

        # Manager colours — green apron over white shirt
        body_color  = (210, 230, 210)   # light green apron
        hat_color   = (60, 120, 70)     # dark green hat
        skin_tone   = (235, 195, 160)
        hair_color  = (55, 38, 22)
        pant_color  = (50, 55, 85)
        shoe_color  = (30, 22, 16)

        # ground shadow
        shadow_surf = pygame.Surface((34, 10), pygame.SRCALPHA)
        for sx in range(17):
            alpha = int(90 * (1 - (sx / 17) ** 1.6))
            pygame.draw.line(shadow_surf, (0, 0, 0, alpha), (17 - sx, 5), (17 + sx, 5), 1)
        self.screen.blit(shadow_surf, (px_pos - 17, py_pos + 22))

        # legs
        for li, (lx, lsw) in enumerate([(-4, swing), (3, -swing)]):
            depth = li == 0
            ly_extra = int(lsw * 8)
            leg_shade = tuple(max(0, v - (18 if depth else 0)) for v in pant_color)
            pygame.draw.rect(self.screen, leg_shade, (px_pos + lx - 1, py_pos + 8 + bob, 6, 7), border_radius=3)
            pygame.draw.rect(self.screen, leg_shade, (px_pos + lx, py_pos + 14 + bob + ly_extra, 5, 6), border_radius=2)
            shoe_x = px_pos + lx - (1 if facing_down else 0)
            shoe_y = py_pos + 19 + bob + ly_extra
            pygame.draw.rect(self.screen, shoe_color, (shoe_x, shoe_y, 8, 4), border_radius=2)
            pygame.draw.line(self.screen, tuple(min(255, v + 22) for v in shoe_color),
                             (shoe_x + 1, shoe_y + 1), (shoe_x + 6, shoe_y + 1), 1)

        # torso / apron
        torso_x, torso_y = px_pos - 8, py_pos - 8 + bob
        pygame.draw.rect(self.screen, (235, 235, 235), (torso_x, torso_y, 16, 17), border_radius=4)  # white shirt under
        pygame.draw.rect(self.screen, body_color, (torso_x + 2, torso_y, 12, 17), border_radius=3)    # green apron overlay
        shadow_col = tuple(max(0, v - 38) for v in body_color)
        pygame.draw.rect(self.screen, shadow_col, (torso_x + 11, torso_y + 2, 4, 13), border_radius=2)
        # apron pocket
        pygame.draw.rect(self.screen, tuple(max(0, v - 25) for v in body_color),
                         (torso_x + 3, torso_y + 9, 6, 5), border_radius=2)

        # arms
        arm_col  = tuple(max(0, v - 22) for v in body_color)
        arm_hi   = tuple(min(255, v + 18) for v in body_color)
        skin_arm = tuple(max(0, v - 15) for v in skin_tone)
        bax = px_pos - 14
        bay = py_pos - 5 + int(a_swing * 7) + bob
        pygame.draw.rect(self.screen, arm_col, (bax, bay, 6, 11), border_radius=3)
        pygame.draw.rect(self.screen, skin_arm, (bax + 1, bay + 8, 4, 4), border_radius=2)
        fax = px_pos + 8
        fay = py_pos - 5 + int(-a_swing * 7) + bob
        pygame.draw.rect(self.screen, arm_col, (fax, fay, 6, 11), border_radius=3)
        pygame.draw.rect(self.screen, skin_arm, (fax + 1, fay + 8, 4, 4), border_radius=2)

        # head
        hx, hy = px_pos, py_pos - 20 + bob
        head_r = 8
        pygame.draw.rect(self.screen, skin_tone, (hx - 3, hy + head_r - 2, 6, 5), border_radius=2)
        pygame.draw.circle(self.screen, skin_tone, (hx, hy), head_r)
        pygame.draw.circle(self.screen, (235, 170, 155), (hx - 4, hy + 2), 3)
        pygame.draw.circle(self.screen, (235, 170, 155), (hx + 4, hy + 2), 3)
        pygame.draw.ellipse(self.screen, hair_color, (hx - head_r, hy - head_r, head_r * 2, head_r + 2))
        pygame.draw.rect(self.screen, hair_color, (hx - head_r - 1, hy - 3, 3, 6), border_radius=1)
        pygame.draw.rect(self.screen, hair_color, (hx + head_r - 2, hy - 3, 3, 6), border_radius=1)

        # eyes
        eye_dir = 1 if facing_down else -1
        for ex_off in [-3, 3]:
            ex = hx + ex_off
            ey = hy - 2 + eye_dir
            pygame.draw.ellipse(self.screen, (245, 245, 250), (ex - 2, ey - 1, 4, 3))
            pygame.draw.circle(self.screen, (60, 90, 140), (ex, ey + 1), 1)
        pygame.draw.arc(self.screen, (180, 100, 90),
                        (hx - 3, hy + 3, 6, 4), math.pi + 0.4, 2 * math.pi - 0.4, 1)

        # manager hat (visor cap)
        hat_hi  = tuple(min(255, v + 35) for v in hat_color)
        hat_shd = tuple(max(0, v - 30) for v in hat_color)
        pygame.draw.rect(self.screen, hat_shd, (hx - head_r - 2, hy - head_r + 2, head_r * 2 + 4, 5), border_radius=2)
        pygame.draw.rect(self.screen, hat_color, (hx - 6, hy - head_r - 6, 12, 9), border_radius=3)
        pygame.draw.rect(self.screen, hat_hi, (hx - 4, hy - head_r - 5, 4, 4), border_radius=2)
        # star badge
        pygame.draw.circle(self.screen, (255, 215, 40), (hx + 2, hy - head_r - 2), 2)

        # "YOU" label
        lsurf = font_sec.render("YOU", True, (220, 240, 220))
        lw = lsurf.get_width()
        pill = pygame.Surface((lw + 8, 13), pygame.SRCALPHA)
        pygame.draw.rect(pill, (30, 80, 40, 200), pill.get_rect(), border_radius=6)
        self.screen.blit(pill, (px_pos - lw // 2 - 4, py_pos + 24))
        self.screen.blit(lsurf, (px_pos - lw // 2, py_pos + 26))

    def draw_customers(self):
        font_sec = get_font(10, bold=True)
        t = self.auth_time
        floor = pygame.Rect(28, 74, WIDTH - 56, HEIGHT - 110)
        floor_y = floor.y + 52  # below window row

        CUST_SKIN   = [(220, 185, 145), (175, 125, 85), (235, 200, 165), (200, 155, 110), (245, 210, 175)]
        CUST_HAIR   = [(55, 35, 22), (20, 15, 10), (140, 80, 30), (80, 50, 20), (180, 140, 80)]
        CUST_SHIRT  = [(80, 140, 200), (200, 100, 80), (140, 200, 100), (200, 160, 60), (120, 90, 180)]
        CUST_PANTS  = [(45, 50, 80), (55, 40, 35), (35, 55, 45), (50, 44, 35), (35, 38, 65)]

        for idx, customer in enumerate(self.customers[:6]):
            cx = int(customer.get("draw_x", customer["x"]))
            cy = int(customer.get("draw_y", customer["y"]))

            skin  = CUST_SKIN[idx % len(CUST_SKIN)]
            hair  = CUST_HAIR[idx % len(CUST_HAIR)]
            shirt = CUST_SHIRT[idx % len(CUST_SHIRT)]
            pants = CUST_PANTS[idx % len(CUST_PANTS)]

            walk_phase   = customer.get("walk_phase", 0.0)
            is_walking   = customer.get("phase", "walk") != "queued"
            facing_down  = customer.get("vy", 0) >= 0
            bob   = int(math.sin(walk_phase * 2) * 2.2) if is_walking else 0
            swing = math.sin(walk_phase) if is_walking else 0.0
            a_swing = math.sin(walk_phase + math.pi) if is_walking else 0.0
            shoe_color = (30, 22, 16)

            alpha = min(255, customer.get("alpha", 255))

            def tint(col, a=alpha):
                # darken slightly when fading in
                scale = a / 255.0
                return tuple(int(v * scale) for v in col)

            # shadow
            shadow_surf = pygame.Surface((34, 10), pygame.SRCALPHA)
            for sx in range(17):
                sa = int(alpha * 0.35 * (1 - (sx / 17) ** 1.6))
                pygame.draw.line(shadow_surf, (0, 0, 0, sa), (17 - sx, 5), (17 + sx, 5), 1)
            self.screen.blit(shadow_surf, (cx - 17, cy + 22))

            # legs
            for li, (lx, lsw) in enumerate([(-4, swing), (3, -swing)]):
                depth = li == 0
                ly_extra = int(lsw * 8)
                leg_shade = tuple(max(0, v - (18 if depth else 0)) for v in tint(pants))
                pygame.draw.rect(self.screen, leg_shade, (cx + lx - 1, cy + 8 + bob, 6, 7), border_radius=3)
                pygame.draw.rect(self.screen, leg_shade, (cx + lx, cy + 14 + bob + ly_extra, 5, 6), border_radius=2)
                sx2 = cx + lx - (1 if facing_down else 0)
                sy2 = cy + 19 + bob + ly_extra
                pygame.draw.rect(self.screen, tint(shoe_color), (sx2, sy2, 8, 4), border_radius=2)

            # torso
            tx, ty = cx - 8, cy - 8 + bob
            pygame.draw.rect(self.screen, tint(shirt), (tx, ty, 16, 17), border_radius=4)
            shadow_col = tuple(max(0, v - 38) for v in tint(shirt))
            pygame.draw.rect(self.screen, shadow_col, (tx + 11, ty + 2, 4, 13), border_radius=2)

            # arms
            arm_col = tuple(max(0, v - 22) for v in tint(shirt))
            skin_arm = tuple(max(0, v - 15) for v in tint(skin))
            pygame.draw.rect(self.screen, arm_col, (cx - 14, cy - 5 + int(a_swing * 7) + bob, 6, 11), border_radius=3)
            pygame.draw.rect(self.screen, skin_arm, (cx - 13, cy + 3 + int(a_swing * 7) + bob, 4, 4), border_radius=2)
            pygame.draw.rect(self.screen, arm_col, (cx + 8, cy - 5 + int(-a_swing * 7) + bob, 6, 11), border_radius=3)
            pygame.draw.rect(self.screen, skin_arm, (cx + 9, cy + 3 + int(-a_swing * 7) + bob, 4, 4), border_radius=2)

            # head
            hx2, hy2 = cx, cy - 20 + bob
            pygame.draw.circle(self.screen, tint(skin), (hx2, hy2), 8)
            pygame.draw.ellipse(self.screen, tint(hair), (hx2 - 8, hy2 - 8, 16, 10))
            pygame.draw.rect(self.screen, tint(hair), (hx2 - 9, hy2 - 3, 3, 6), border_radius=1)
            pygame.draw.rect(self.screen, tint(hair), (hx2 + 6, hy2 - 3, 3, 6), border_radius=1)
            eye_dir = 1 if facing_down else -1
            for ex_off in [-3, 3]:
                ex = hx2 + ex_off; ey = hy2 - 2 + eye_dir
                pygame.draw.ellipse(self.screen, tint((245, 245, 250)), (ex - 2, ey - 1, 4, 3))
                pygame.draw.circle(self.screen, tint((60, 90, 140)), (ex, ey + 1), 1)

            # patience bar above head
            patience_ratio = max(0.0, customer["patience"]) / 100.0
            bar_w = 28
            bar_x = cx - bar_w // 2
            bar_y = cy - 36 + bob
            pygame.draw.rect(self.screen, (40, 44, 60), (bar_x, bar_y, bar_w, 5), border_radius=2)
            bar_col2 = SUCCESS if patience_ratio > 0.6 else WARNING if patience_ratio > 0.3 else DANGER
            pygame.draw.rect(self.screen, bar_col2, (bar_x, bar_y, int(bar_w * patience_ratio), 5), border_radius=2)

            # "E" hint when player is nearby and customer is queued
            if customer.get("phase") == "queued":
                px_pos2  = int(self.player.x)
                py_pos2  = int(self.player.y)
                dist2    = math.sqrt((px_pos2 - cx)**2 + (py_pos2 - cy)**2)
                if dist2 < 100 and not self.dialogue_customer:
                    hint = get_font(SMALL_SIZE, bold=True).render("[E] Talk", True, (220, 240, 220))
                    hw2  = hint.get_width()
                    pill2= pygame.Surface((hw2 + 12, 16), pygame.SRCALPHA)
                    pygame.draw.rect(pill2, (30, 80, 40, 200), pill2.get_rect(), border_radius=8)
                    self.screen.blit(pill2, (cx - hw2 // 2 - 6, bar_y - 22))
                    self.screen.blit(hint,  (cx - hw2 // 2,     bar_y - 20))

    def draw_overlay(self):
        bg = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        bg.fill((5, 8, 18, int(140 * self.overlay_anim)))
        self.screen.blit(bg, (0, 0))

        slide = int((1.0 - self.overlay_anim) * PANEL_SLIDE_DISTANCE)
        panel = pygame.Rect(170, 92 + slide, 1100, 678)
        draw_shadowed_card(self.screen, panel, color=PANEL, radius=30)

        title_map = {
            "stock":       "Inventory & Stock Shelves",
            "checkout":    "Checkout Register",
            "manager":     "Employee Management & Upgrades",
            "prices":      "Smart Pricing — All Products",
            "leaderboard": "Leaderboard",
            "report":      "Daily Shift Report",
            "reviews":     "Customer Reviews",
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
        all_product_keys = list(PRODUCT_CATALOG.keys())
        active_cats      = self._get_active_cats_for_section()
        section_label    = self.stock_section.title() if self.stock_section != "all" else "All Sections"

        # ── instruction line — drawn just above the card grid ───────────
        CONTENT_TOP = panel.y + 80     # clears title (y≈126) + ESC hint + breathing room
        hint = (f"Section: {section_label}   •   Press key to restock   •   "
                f"Grey = go to that section first")
        draw_text(self.screen, hint,
                  (panel.x + 24, CONTENT_TOP - 22), size=SMALL_SIZE, color=TEXT_MUTED)

        # ── card grid — 6 per row × 2 rows for all 12 products ───────────
        per_row = 6
        gap     = 10
        x0      = panel.x + 16
        y0      = CONTENT_TOP

        avail_w = panel.width  - 32
        avail_h = (panel.y + panel.height) - CONTENT_TOP - 12

        card_w = (avail_w - gap * (per_row - 1)) // per_row
        card_h = (avail_h - gap) // 2

        for idx, product_key in enumerate(all_product_keys):
            col  = idx % per_row
            row  = idx // per_row
            rx   = x0 + col * (card_w + gap)
            ry   = y0 + row * (card_h + gap)
            rect = pygame.Rect(rx, ry, card_w, card_h)

            cat         = PRODUCT_CATALOG[product_key]["category"]
            shelf_cat   = next((c for c, pk in SHELF_LAYOUT.items() if pk == product_key), cat)
            can_stock   = self.stock_section == "all" or shelf_cat in active_cats
            capacity    = SHELF_CAPACITY + (8 if self.state.upgrades.get("shelves") else 0)
            qty         = self.state.shelves.get(shelf_cat, 0)
            storage     = self.state.storage.get(product_key, 0)
            fill_ratio  = min(1.0, qty / max(1, capacity))
            prod_color  = PRODUCT_CATALOG[product_key]["color"]
            bar_col     = ACCENT if fill_ratio > 0.35 else WARNING if fill_ratio > 0.15 else DANGER

            # Dim unavailable cards
            card_bg  = CARD if can_stock else tuple(max(0, v - 22) for v in CARD)
            bdr_col  = bar_col if can_stock else OUTLINE
            bdr_w    = 2 if can_stock else 1

            draw_shadowed_card(self.screen, rect, color=card_bg, radius=12,
                               border_color=bdr_col, border_width=bdr_w)

            self.screen.set_clip(rect.inflate(-2, -2))

            # Key label + product name
            key_lbl  = str(idx + 1) if idx < 9 else "–"
            txt_col  = TEXT if can_stock else TEXT_MUTED
            pygame.draw.circle(self.screen, prod_color if can_stock else OUTLINE,
                               (rect.x + 12, rect.y + 14), 5)
            draw_text(self.screen, f"{key_lbl}. {PRODUCT_CATALOG[product_key]['name']}",
                      (rect.x + 22, rect.y + 7), size=SMALL_SIZE, bold=True, color=txt_col)

            draw_text(self.screen, f"Storage: {storage}",
                      (rect.x + 9, rect.y + 30), size=SMALL_SIZE, color=txt_col)
            draw_text(self.screen, f"Shelf: {qty}/{capacity}",
                      (rect.x + 9, rect.y + 50), size=SMALL_SIZE, color=txt_col)

            if not can_stock:
                sec = PRODUCT_CATALOG[product_key].get("section", "section").title()
                draw_text(self.screen, f"→ {sec} area",
                          (rect.x + 9, rect.y + 70), size=SMALL_SIZE, color=TEXT_MUTED)

            # Stock bar
            bar = pygame.Rect(rect.x + 9, rect.bottom - 28, card_w - 18, 6)
            pygame.draw.rect(self.screen, PANEL_ALT, bar, border_radius=3)
            if can_stock:
                pygame.draw.rect(self.screen, bar_col,
                                 (bar.x, bar.y, int(bar.width * fill_ratio), bar.height),
                                 border_radius=3)

            # Colour swatch at bottom
            swatch_col = prod_color if can_stock else tuple(max(0, v - 40) for v in prod_color)
            pygame.draw.rect(self.screen, swatch_col,
                             (rect.x + 9, rect.bottom - 18, card_w - 18, 14),
                             border_radius=4)

            self.screen.set_clip(None)

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
        CONTENT_TOP = panel.y + 80
        draw_text(self.screen, "1-5 hire  •  H fire  •  P promote  •  U/I/O upgrades  •  M promo",
                  (panel.x + 24, CONTENT_TOP - 22), size=SMALL_SIZE, color=TEXT_MUTED)

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
        all_keys = list(PRODUCT_CATALOG.keys())

        # The overlay title "Smart Pricing — All Products" draws at y=126 (slide-adjusted).
        # Everything in this method must start below y≈168 to stay clear of that header row.
        CONTENT_TOP = panel.y + 80    # safe top edge — well below title + ESC hint

        # Instruction line pinned just above the cards
        draw_text(self.screen,
                  "Keys 1–9 apply suggested price   •   A = apply all",
                  (panel.x + 24, CONTENT_TOP - 22),
                  size=SMALL_SIZE, color=TEXT_MUTED)

        # Layout: 6 cards per row, 2 rows
        per_row = 6
        n_rows  = 2
        gap     = 10

        avail_w = panel.width  - 32
        avail_h = (panel.y + panel.height) - CONTENT_TOP - 12

        card_w = (avail_w - gap * (per_row - 1)) // per_row
        card_h = (avail_h - gap * (n_rows  - 1)) // n_rows

        x0 = panel.x + 16
        y0 = CONTENT_TOP

        for idx, product_key in enumerate(all_keys):
            col  = idx % per_row
            row  = idx // per_row
            rx   = x0 + col * (card_w + gap)
            ry   = y0 + row * (card_h + gap)
            rect = pygame.Rect(rx, ry, card_w, card_h)

            current   = self.state.prices.get(product_key, PRODUCT_CATALOG[product_key]["base_price"])
            cat       = PRODUCT_CATALOG[product_key]["category"]
            shelf_qty = self.state.shelves.get(cat, 0)
            stock     = self.state.storage.get(product_key, 0) + shelf_qty
            suggested = price_suggestion(current, stock, self.state.demand.get(product_key, 1.0))
            color     = PRODUCT_CATALOG[product_key]["color"]
            trend_up  = suggested >= current
            border    = SUCCESS if trend_up else WARNING

            draw_shadowed_card(self.screen, rect, color=CARD, radius=12,
                               border_color=border, border_width=2)

            self.screen.set_clip(rect.inflate(-2, -2))

            # Colour pip + key number + product name
            pygame.draw.circle(self.screen, color, (rect.x + 12, rect.y + 16), 5)
            key_label = str(idx + 1) if idx < 9 else "–"
            draw_text(self.screen, f"{key_label}. {PRODUCT_CATALOG[product_key]['name']}",
                      (rect.x + 22, rect.y + 9), size=SMALL_SIZE, bold=True)

            # Current price
            draw_text(self.screen, f"Now: ${current:.2f}",
                      (rect.x + 9, rect.y + 32), size=SMALL_SIZE, color=TEXT_MUTED)
            # Suggested price (prominent)
            draw_text(self.screen, f"→ ${suggested:.2f}",
                      (rect.x + 9, rect.y + 52), size=BODY_SIZE, bold=True,
                      color=SUCCESS if trend_up else WARNING)

            # Demand + stock
            draw_text(self.screen, f"Dmnd: {self.state.demand.get(product_key, 1.0):.2f}",
                      (rect.x + 9, rect.y + 84), size=SMALL_SIZE, color=TEXT_MUTED)
            draw_text(self.screen, f"Stk:  {stock}",
                      (rect.x + 9, rect.y + 102), size=SMALL_SIZE, color=TEXT_MUTED)

            # Trend bar pinned to card bottom
            bar = pygame.Rect(rect.x + 9, rect.bottom - 22, card_w - 18, 6)
            pygame.draw.rect(self.screen, PANEL_ALT, bar, border_radius=3)
            diff = max(-0.4, min(0.4, suggested - current))
            fill = int((diff + 0.4) / 0.8 * bar.width)
            pygame.draw.rect(self.screen, ACCENT if trend_up else WARNING,
                             (bar.x, bar.y, fill, bar.height), border_radius=3)

            self.screen.set_clip(None)

    def draw_leaderboard_overlay(self, panel: pygame.Rect):
        draw_text(self.screen, "Live  •  Firebase Realtime Database",
                  (panel.x + 340, panel.y + 34), size=SMALL_SIZE, color=TEXT_MUTED)

        rows = []
        try:
            raw = self.firebase.get_leaderboard(self.session.id_token) if self.session.id_token else {}
            for _, entry in (raw or {}).items():
                rows.append(entry)
            rows.sort(key=lambda r: r.get("score", 0), reverse=True)
        except Exception as e:
            draw_text(self.screen, str(e)[:80], (panel.centerx, panel.y + 80),
                      size=BODY_SIZE, color=DANGER, center=True)
            rows = []

        TABLE_Y  = panel.y + 70
        ROW_H    = 34
        HEADER_H = 30
        PAD      = 24          # left/right padding inside panel
        TW       = panel.width - PAD * 2   # usable table width

        # All positions as fractions of TW — they scale with whichever panel calls this
        # RANK(5%) | PLAYER(32%) | SCORE(20%) | MONEY(22%) | DAY(10%) | right pad
        X_RANK   = panel.x + PAD + int(TW * 0.025)   # centre
        X_PLAYER = panel.x + PAD + int(TW * 0.08)    # left anchor
        X_SCORE  = panel.x + PAD + int(TW * 0.52)    # centre
        X_MONEY  = panel.x + PAD + int(TW * 0.72)    # centre
        X_DAY    = panel.x + PAD + int(TW * 0.91)    # centre

        medal_colors = [(255, 215, 40), (192, 192, 192), (205, 127, 50)]

        # ── Header bar ────────────────────────────────────────────────────
        hdr = pygame.Rect(panel.x + PAD, TABLE_Y, TW, HEADER_H)
        pygame.draw.rect(self.screen, PANEL_ALT, hdr, border_radius=8)
        pygame.draw.rect(self.screen, OUTLINE, hdr, 1, border_radius=8)

        draw_text(self.screen, "PLAYER", (X_PLAYER, TABLE_Y + 8),
                  size=SMALL_SIZE, bold=True, color=TEXT_MUTED)
        draw_text(self.screen, "SCORE",  (X_SCORE,  TABLE_Y + 8),
                  size=SMALL_SIZE, bold=True, color=TEXT_MUTED, center=True)
        draw_text(self.screen, "MONEY",  (X_MONEY,  TABLE_Y + 8),
                  size=SMALL_SIZE, bold=True, color=TEXT_MUTED, center=True)
        draw_text(self.screen, "DAY",    (X_DAY,    TABLE_Y + 8),
                  size=SMALL_SIZE, bold=True, color=TEXT_MUTED, center=True)

        if not rows:
            draw_text(self.screen, "No entries yet — be the first!",
                      (panel.centerx, TABLE_Y + 100), size=BODY_SIZE, color=TEXT_MUTED, center=True)
            return

        # ── Rows ──────────────────────────────────────────────────────────
        for i, entry in enumerate(rows[:9], start=1):
            ry = TABLE_Y + HEADER_H + (i - 1) * ROW_H + 2

            if i == 1:
                bg = pygame.Surface((TW, ROW_H - 2), pygame.SRCALPHA)
                pygame.draw.rect(bg, (255, 213, 79, 22), bg.get_rect(), border_radius=6)
                self.screen.blit(bg, (panel.x + PAD, ry))
            elif i % 2 == 0:
                bg = pygame.Surface((TW, ROW_H - 2), pygame.SRCALPHA)
                pygame.draw.rect(bg, (*PANEL_ALT, 80), bg.get_rect(), border_radius=4)
                self.screen.blit(bg, (panel.x + PAD, ry))

            row_col = (255, 240, 180) if i == 1 else TEXT
            ty = ry + 9

            # Rank
            mc = medal_colors[i - 1] if i <= 3 else TEXT_MUTED
            draw_text(self.screen, str(i), (X_RANK, ty),
                      size=SMALL_SIZE, bold=(i <= 3), color=mc, center=True)

            # Truncate username to fit player column (max 18 chars)
            username = str(entry.get("username", "Player"))[:18]

            # Format numbers with compact notation if they'd overflow
            raw_score = entry.get("score", 0)
            raw_money = entry.get("money", 0)
            score_str = f"{raw_score:,}" if raw_score < 1_000_000 else f"{raw_score/1000:.1f}K"
            money_str = f"${raw_money:,.0f}" if raw_money < 100_000 else f"${raw_money/1000:.1f}K"
            day_str   = str(entry.get("day", 1))

            draw_text(self.screen, username,  (X_PLAYER, ty), size=SMALL_SIZE, color=row_col)
            draw_text(self.screen, score_str, (X_SCORE,  ty), size=SMALL_SIZE, color=row_col, center=True)
            draw_text(self.screen, money_str, (X_MONEY,  ty), size=SMALL_SIZE, color=row_col, center=True)
            draw_text(self.screen, day_str,   (X_DAY,    ty), size=SMALL_SIZE, color=row_col, center=True)

            # Column dividers
            for dx in [X_SCORE - int(TW * 0.10),
                       X_MONEY - int(TW * 0.10),
                       X_DAY   - int(TW * 0.09)]:
                pygame.draw.line(self.screen, OUTLINE, (dx, ry), (dx, ry + ROW_H - 3), 1)

            # Row separator
            pygame.draw.line(self.screen, OUTLINE,
                             (panel.x + PAD + 4,       ry + ROW_H - 3),
                             (panel.x + panel.width - PAD - 4, ry + ROW_H - 3), 1)

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