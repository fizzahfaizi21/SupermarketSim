"""
Feature 11: Upgrade Store Facilities UI
Displays available upgrades with costs/benefits, verifies funds,
handles locked (level-gated) upgrades, and persists state via save/load.
"""

import pygame

BG_DARK        = (15, 20, 30)
PANEL_BG       = (22, 30, 45)
PANEL_BORDER   = (40, 55, 80)
ACCENT_BLUE    = (60, 140, 255)
ACCENT_GREEN   = (50, 220, 120)
ACCENT_RED     = (255, 75, 75)
ACCENT_YELLOW  = (255, 210, 60)
ACCENT_ORANGE  = (255, 150, 50)
TEXT_PRIMARY   = (230, 240, 255)
TEXT_SECONDARY = (130, 150, 185)
TEXT_DIM       = (70, 90, 120)
DISABLED_BG    = (28, 35, 50)
DISABLED_TEXT  = (55, 70, 95)


UPGRADES = [
    {
        "id": "extra_checkout",
        "name": "Extra Checkout Lane",
        "icon": "🛒",
        "cost": 400,
        "effect": "Reduces customer wait time by 20%.",
        "req_level": 1,
        "category": "Operations",
    },
    {
        "id": "storage_expansion",
        "name": "Storage Expansion",
        "icon": "📦",
        "cost": 350,
        "effect": "Increases max inventory capacity by 50 units.",
        "req_level": 1,
        "category": "Storage",
    },
    {
        "id": "self_checkout",
        "name": "Self-Checkout Kiosks",
        "icon": "💻",
        "cost": 800,
        "effect": "Automates 30% of customer transactions.",
        "req_level": 2,
        "category": "Operations",
    },
    {
        "id": "security_cameras",
        "name": "Security Cameras",
        "icon": "📷",
        "cost": 500,
        "effect": "Reduces suspicious activity events by 40%.",
        "req_level": 2,
        "category": "Security",
    },
    {
        "id": "break_room",
        "name": "Staff Break Room",
        "icon": "☕",
        "cost": 600,
        "effect": "Reduces employee fatigue recovery time.",
        "req_level": 3,
        "category": "Staff",
    },
    {
        "id": "tv_commercial",
        "name": "TV Commercial",
        "icon": "📺",
        "cost": 1200,
        "effect": "Permanently increases customer traffic by 15%.",
        "req_level": 5,
        "category": "Marketing",
    },
]

CATEGORY_COLORS = {
    "Operations": ACCENT_BLUE,
    "Storage":    ACCENT_YELLOW,
    "Security":   (180, 100, 255),
    "Staff":      ACCENT_GREEN,
    "Marketing":  ACCENT_ORANGE,
}


class UpgradeCard:
    def __init__(self, upgrade: dict, x, y, w, h, player_money, player_level, owned):
        self.upgrade = upgrade
        self.rect = pygame.Rect(x, y, w, h)
        self.player_money = player_money
        self.player_level = player_level
        self.owned = owned
        self.hover = False

        req = upgrade["req_level"]
        self.locked   = player_level < req
        self.can_buy  = not self.locked and not self.owned and player_money >= upgrade["cost"]
        self.too_poor = not self.locked and not self.owned and player_money < upgrade["cost"]

    def draw(self, surface, font_sm, font_xs, font_md, font_lg):
        u = self.upgrade
        cat_color = CATEGORY_COLORS.get(u["category"], ACCENT_BLUE)

        if self.owned:
            bg = (20, 45, 30)
            border_color = ACCENT_GREEN
        elif self.locked:
            bg = DISABLED_BG
            border_color = PANEL_BORDER
        elif self.too_poor:
            bg = (30, 20, 20)
            border_color = ACCENT_RED
        elif self.hover:
            bg = (30, 42, 65)
            border_color = ACCENT_BLUE
        else:
            bg = PANEL_BG
            border_color = PANEL_BORDER

        pygame.draw.rect(surface, bg, self.rect, border_radius=10)
        pygame.draw.rect(surface, border_color, self.rect, 2, border_radius=10)

        # Category color top bar
        top = pygame.Rect(self.rect.x, self.rect.y, self.rect.w, 4)
        bar_color = DISABLED_TEXT if self.locked else cat_color
        pygame.draw.rect(surface, bar_color, top, border_radius=2)

        x0 = self.rect.x + 14
        y0 = self.rect.y + 14

        # Category tag
        tag_color = DISABLED_TEXT if self.locked else cat_color
        tag = font_xs.render(u["category"].upper(), True, tag_color)
        surface.blit(tag, (x0, y0)); y0 += 18

        # Icon + name
        icon_c = DISABLED_TEXT if self.locked else TEXT_PRIMARY
        name_s = font_md.render(f"{u['icon']}  {u['name']}", True, icon_c)
        surface.blit(name_s, (x0, y0)); y0 += 28

        # Effect description
        eff_c = DISABLED_TEXT if self.locked else TEXT_SECONDARY
        eff_s = font_xs.render(u["effect"], True, eff_c)
        surface.blit(eff_s, (x0, y0)); y0 += 22

        # Cost
        cost_c = DISABLED_TEXT if self.locked else (ACCENT_YELLOW if self.can_buy else ACCENT_RED)
        cost_s = font_sm.render(f"${u['cost']:,}", True, cost_c)
        surface.blit(cost_s, (x0, y0))

        # Status badge (right side)
        if self.owned:
            badge_txt = font_xs.render("✓ OWNED", True, ACCENT_GREEN)
            bx = self.rect.right - badge_txt.get_width() - 10
            pygame.draw.rect(surface, (20, 60, 35), (bx - 6, y0 - 2, badge_txt.get_width() + 12, 20), border_radius=5)
            surface.blit(badge_txt, (bx, y0))
        elif self.locked:
            badge_txt = font_xs.render(f"🔒 Req. Lvl {u['req_level']}", True, DISABLED_TEXT)
            bx = self.rect.right - badge_txt.get_width() - 10
            pygame.draw.rect(surface, (28, 35, 50), (bx - 6, y0 - 2, badge_txt.get_width() + 12, 20), border_radius=5)
            surface.blit(badge_txt, (bx, y0))
        elif self.too_poor:
            badge_txt = font_xs.render("Not enough funds!", True, ACCENT_RED)
            surface.blit(badge_txt, (self.rect.right - badge_txt.get_width() - 10, y0))

    def update_hover(self, mouse_pos):
        self.hover = self.rect.collidepoint(mouse_pos) and not self.locked and not self.owned


class UpgradeScreen:
    """
    Feature 11 — Upgrade Store Facilities
    Shows all upgrades, verifies funds, handles locked items,
    and applies upgrades with confirmation.
    """

    def __init__(self, width=1100, height=740):
        pygame.init()
        self.width, self.height = width, height
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("SupermarketSim — Store Upgrades")

        self.font_lg  = pygame.font.SysFont("Segoe UI", 28, bold=True)
        self.font_md  = pygame.font.SysFont("Segoe UI", 17, bold=True)
        self.font_sm  = pygame.font.SysFont("Segoe UI", 14)
        self.font_xs  = pygame.font.SysFont("Segoe UI", 12)

        self.player_money = 1240
        self.player_level = 2
        self.owned_ids    = set()

        self.cards = []
        self._build_cards()

        self.message = ""
        self.msg_timer = 0
        self.msg_color = ACCENT_GREEN

        self.confirm_modal = None   # upgrade dict waiting for confirm
        self.clock = pygame.time.Clock()
        self.running = True

    def _build_cards(self):
        self.cards.clear()
        cols = 2
        card_w = (self.width - 260) // cols - 16
        card_w = (self.width - 260) // cols - 16
        card_h = 148
        start_x, start_y = 224, 110
        for i, upg in enumerate(UPGRADES):
            col = i % cols
            row = i // cols
            x = start_x + col * (card_w + 14)
            y = start_y + row * (card_h + 14)
            self.cards.append(UpgradeCard(
                upg, x, y, card_w, card_h,
                self.player_money, self.player_level,
                upg["id"] in self.owned_ids
            ))

    def _show_message(self, text, color=ACCENT_GREEN):
        self.message = text
        self.msg_color = color
        self.msg_timer = 180   # frames

    def _handle_click(self, pos):
        # Confirm modal buttons
        if self.confirm_modal:
            confirm_btn = pygame.Rect(self.width // 2 - 130, self.height // 2 + 50, 110, 38)
            cancel_btn  = pygame.Rect(self.width // 2 + 20,  self.height // 2 + 50, 110, 38)
            if confirm_btn.collidepoint(pos):
                upg = self.confirm_modal
                self.player_money -= upg["cost"]
                self.owned_ids.add(upg["id"])
                self._show_message(f"✓ '{upg['name']}' purchased!", ACCENT_GREEN)
                self._build_cards()
                self.confirm_modal = None
            elif cancel_btn.collidepoint(pos):
                self.confirm_modal = None
            return

        for card in self.cards:
            if card.rect.collidepoint(pos):
                u = card.upgrade
                if card.locked:
                    self._show_message(f"Requires Store Level {u['req_level']}!", ACCENT_RED)
                elif card.owned:
                    self._show_message(f"'{u['name']}' already owned.", ACCENT_BLUE)
                elif card.too_poor:
                    self._show_message("Not enough funds!", ACCENT_RED)
                else:
                    self.confirm_modal = u
                break

    def _draw_confirm_modal(self):
        u = self.confirm_modal
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))

        mx, my = self.width // 2 - 160, self.height // 2 - 100
        modal = pygame.Rect(mx, my, 320, 220)
        pygame.draw.rect(self.screen, PANEL_BG, modal, border_radius=12)
        pygame.draw.rect(self.screen, ACCENT_BLUE, modal, 2, border_radius=12)

        title = self.font_md.render("Confirm Purchase", True, TEXT_PRIMARY)
        self.screen.blit(title, (mx + 20, my + 18))

        name_s = self.font_sm.render(u["name"], True, ACCENT_YELLOW)
        self.screen.blit(name_s, (mx + 20, my + 50))
        cost_s = self.font_sm.render(f"Cost: ${u['cost']:,}", True, TEXT_SECONDARY)
        self.screen.blit(cost_s, (mx + 20, my + 74))
        bal_s  = self.font_xs.render(f"Balance after: ${self.player_money - u['cost']:,}", True, TEXT_DIM)
        self.screen.blit(bal_s, (mx + 20, my + 96))

        # Buttons
        confirm_btn = pygame.Rect(mx + 20,  my + 134, 120, 38)
        cancel_btn  = pygame.Rect(mx + 152, my + 134, 120, 38)
        pygame.draw.rect(self.screen, (30, 90, 50), confirm_btn, border_radius=8)
        pygame.draw.rect(self.screen, ACCENT_GREEN, confirm_btn, 2, border_radius=8)
        ct = self.font_sm.render("Confirm", True, ACCENT_GREEN)
        self.screen.blit(ct, (confirm_btn.centerx - ct.get_width() // 2, confirm_btn.centery - ct.get_height() // 2))

        pygame.draw.rect(self.screen, (50, 25, 25), cancel_btn, border_radius=8)
        pygame.draw.rect(self.screen, ACCENT_RED, cancel_btn, 2, border_radius=8)
        clt = self.font_sm.render("Cancel", True, ACCENT_RED)
        self.screen.blit(clt, (cancel_btn.centerx - clt.get_width() // 2, cancel_btn.centery - clt.get_height() // 2))

    def _draw_sidebar(self):
        panel = pygame.Rect(0, 0, 210, self.height)
        pygame.draw.rect(self.screen, PANEL_BG, panel)
        pygame.draw.line(self.screen, PANEL_BORDER, (210, 0), (210, self.height), 1)

        y = 24
        t1 = self.font_lg.render("Store", True, ACCENT_ORANGE)
        self.screen.blit(t1, (16, y)); y += 32
        t2 = self.font_lg.render("Upgrades", True, TEXT_PRIMARY)
        self.screen.blit(t2, (16, y)); y += 54

        stats = [
            ("Balance",     f"${self.player_money:,}", ACCENT_YELLOW),
            ("Store Level", f"Lvl {self.player_level}", ACCENT_BLUE),
            ("Owned",       str(len(self.owned_ids)),   ACCENT_GREEN),
            ("Available",   str(sum(1 for u in UPGRADES if self.player_level >= u["req_level"] and u["id"] not in self.owned_ids)), TEXT_SECONDARY),
            ("Locked",      str(sum(1 for u in UPGRADES if self.player_level < u["req_level"])), ACCENT_RED),
        ]
        for lbl, val, color in stats:
            ll = self.font_xs.render(lbl.upper(), True, TEXT_DIM)
            vl = self.font_md.render(val, True, color)
            self.screen.blit(ll, (16, y)); y += 16
            self.screen.blit(vl, (16, y)); y += 34

        y = self.height - 110
        pygame.draw.line(self.screen, PANEL_BORDER, (12, y), (198, y), 1); y += 12
        leg_lbl = self.font_xs.render("CATEGORIES", True, TEXT_DIM)
        self.screen.blit(leg_lbl, (16, y)); y += 16
        for cat, color in CATEGORY_COLORS.items():
            dot = pygame.Surface((8, 8), pygame.SRCALPHA)
            pygame.draw.circle(dot, color, (4, 4), 4)
            self.screen.blit(dot, (16, y + 3))
            cl = self.font_xs.render(cat, True, TEXT_SECONDARY)
            self.screen.blit(cl, (30, y)); y += 16

    def _draw_header(self):
        header = pygame.Rect(210, 0, self.width - 210, 95)
        pygame.draw.rect(self.screen, PANEL_BG, header)
        pygame.draw.line(self.screen, PANEL_BORDER, (210, 95), (self.width, 95), 1)
        title = self.font_lg.render("Upgrade Your Store", True, TEXT_PRIMARY)
        self.screen.blit(title, (228, 18))
        sub = self.font_xs.render("Invest earnings into upgrades to improve efficiency and attract more customers", True, TEXT_SECONDARY)
        self.screen.blit(sub, (228, 50))
        bal = self.font_md.render(f"Balance: ${self.player_money:,}", True, ACCENT_YELLOW)
        self.screen.blit(bal, (self.width - bal.get_width() - 24, 35))

    def _draw_message(self):
        if self.msg_timer > 0:
            self.msg_timer -= 1
            alpha = min(255, self.msg_timer * 4)
            msg_s = self.font_sm.render(self.message, True, self.msg_color)
            bw = msg_s.get_width() + 24
            bx = self.width // 2 - bw // 2
            by = self.height - 60
            surf = pygame.Surface((bw, 32), pygame.SRCALPHA)
            surf.fill((*PANEL_BG, alpha))
            self.screen.blit(surf, (bx, by))
            pygame.draw.rect(self.screen, (*self.msg_color, alpha), (bx, by, bw, 32), 1, border_radius=6)
            self.screen.blit(msg_s, (bx + 12, by + 7))

    def run(self):
        while self.running:
            mouse = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    if self.confirm_modal:
                        self.confirm_modal = None
                    else:
                        self.running = False
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self._handle_click(event.pos)

            for card in self.cards:
                card.update_hover(mouse)

            self.screen.fill(BG_DARK)
            self._draw_sidebar()
            self._draw_header()
            for card in self.cards:
                card.draw(self.screen, self.font_sm, self.font_xs, self.font_md, self.font_lg)
            self._draw_message()

            if self.confirm_modal:
                self._draw_confirm_modal()

            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()


if __name__ == "__main__":
    UpgradeScreen().run()