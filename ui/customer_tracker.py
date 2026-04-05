"""
Feature 8: Customer Tracker UI
Displays AI customer behavior assignments, interaction tracking,
satisfaction levels, and special scenario triggers.
"""

import pygame
import random

# ── Colors ──────────────────────────────────────────────────────────────────
BG_DARK       = (15, 20, 30)
PANEL_BG      = (22, 30, 45)
PANEL_BORDER  = (40, 55, 80)
ACCENT_BLUE   = (60, 140, 255)
ACCENT_GREEN  = (50, 220, 120)
ACCENT_RED    = (255, 75, 75)
ACCENT_YELLOW = (255, 210, 60)
TEXT_PRIMARY  = (230, 240, 255)
TEXT_SECONDARY= (130, 150, 185)
TEXT_DIM      = (70, 90, 120)
WHITE         = (255, 255, 255)

MOOD_COLORS = {
    "happy":   ACCENT_GREEN,
    "neutral": ACCENT_YELLOW,
    "angry":   ACCENT_RED,
    "confused":(180, 100, 255),
    "impatient":ACCENT_RED,
    "satisfied":ACCENT_GREEN,
}

MOOD_ICONS = {
    "happy":    "😊",
    "neutral":  "😐",
    "angry":    "😠",
    "confused": "😕",
    "impatient":"😤",
    "satisfied":"😄",
}


class CustomerCard:
    """Renders a single customer info card."""

    def __init__(self, customer: dict, x: int, y: int, w: int, h: int):
        self.customer = customer
        self.rect = pygame.Rect(x, y, w, h)
        self.hover = False

    def draw(self, surface: pygame.Surface, font_sm, font_md):
        c = self.customer
        color = MOOD_COLORS.get(c["mood"], TEXT_SECONDARY)

        # Card background
        alpha_surf = pygame.Surface((self.rect.w, self.rect.h), pygame.SRCALPHA)
        bg_color = (30, 42, 65, 220) if self.hover else (22, 30, 45, 200)
        alpha_surf.fill(bg_color)
        surface.blit(alpha_surf, self.rect.topleft)

        # Border — colored by mood
        pygame.draw.rect(surface, color, self.rect, 2, border_radius=8)

        # Mood indicator strip on left
        strip = pygame.Rect(self.rect.x, self.rect.y, 4, self.rect.h)
        pygame.draw.rect(surface, color, strip, border_radius=2)

        x0 = self.rect.x + 14
        y0 = self.rect.y + 10

        # Customer ID + mood
        id_surf = font_md.render(f"Customer #{c['customer_id']}", True, TEXT_PRIMARY)
        surface.blit(id_surf, (x0, y0))

        mood_surf = font_sm.render(f"{c['mood'].upper()}", True, color)
        surface.blit(mood_surf, (self.rect.right - mood_surf.get_width() - 12, y0 + 3))

        y0 += 28
        # Patience bar
        bar_label = font_sm.render("Patience", True, TEXT_SECONDARY)
        surface.blit(bar_label, (x0, y0))
        bar_x = x0 + 75
        bar_w = self.rect.w - 100
        bar_h = 8
        pygame.draw.rect(surface, PANEL_BORDER, (bar_x, y0 + 3, bar_w, bar_h), border_radius=4)
        fill = int(bar_w * c["patience_lvl"] / 100)
        bar_color = ACCENT_GREEN if c["patience_lvl"] > 60 else (ACCENT_YELLOW if c["patience_lvl"] > 30 else ACCENT_RED)
        pygame.draw.rect(surface, bar_color, (bar_x, y0 + 3, fill, bar_h), border_radius=4)
        pct_surf = font_sm.render(f"{c['patience_lvl']}%", True, TEXT_DIM)
        surface.blit(pct_surf, (bar_x + bar_w + 4, y0))

        y0 += 22
        # Satisfaction
        sat_label = font_sm.render("Satisfaction", True, TEXT_SECONDARY)
        surface.blit(sat_label, (x0, y0))
        bar_x2 = x0 + 85
        bar_w2 = self.rect.w - 110
        pygame.draw.rect(surface, PANEL_BORDER, (bar_x2, y0 + 3, bar_w2, bar_h), border_radius=4)
        fill2 = int(bar_w2 * c["satisfaction"] / 100)
        sat_color = ACCENT_GREEN if c["satisfaction"] > 60 else (ACCENT_YELLOW if c["satisfaction"] > 30 else ACCENT_RED)
        pygame.draw.rect(surface, sat_color, (bar_x2, y0 + 3, fill2, bar_h), border_radius=4)
        sat_pct = font_sm.render(f"{c['satisfaction']}%", True, TEXT_DIM)
        surface.blit(sat_pct, (bar_x2 + bar_w2 + 4, y0))

        y0 += 22
        # Status tag
        status = c.get("status", "browsing")
        status_color = ACCENT_BLUE if status == "browsing" else (ACCENT_YELLOW if status == "waiting" else ACCENT_GREEN)
        tag_surf = font_sm.render(f"● {status.upper()}", True, status_color)
        surface.blit(tag_surf, (x0, y0))

        # Special scenario badge
        if c.get("special_scenario"):
            badge = font_sm.render(f"⚠ {c['special_scenario']}", True, ACCENT_YELLOW)
            surface.blit(badge, (self.rect.right - badge.get_width() - 12, y0))

    def update_hover(self, mouse_pos):
        self.hover = self.rect.collidepoint(mouse_pos)


class CustomerTrackerScreen:
    """
    Feature 8 — Customer Tracker
    Shows all active AI customers, their moods, patience, satisfaction,
    and any special scenario flags.
    """

    def __init__(self, width=1100, height=720):
        pygame.init()
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("SupermarketSim — Customer Tracker")

        self.font_lg  = pygame.font.SysFont("Segoe UI", 26, bold=True)
        self.font_md  = pygame.font.SysFont("Segoe UI", 17, bold=True)
        self.font_sm  = pygame.font.SysFont("Segoe UI", 13)
        self.font_xs  = pygame.font.SysFont("Segoe UI", 11)

        self.customers = self._mock_customers()
        self.cards = []
        self._build_cards()

        self.stats = self._compute_stats()
        self.clock = pygame.time.Clock()
        self.running = True

    def _mock_customers(self):
        moods = ["happy", "neutral", "angry", "confused", "impatient", "satisfied"]
        statuses = ["browsing", "waiting", "checkout"]
        scenarios = [None, None, None, "VIP Customer", "Suspicious Activity"]
        customers = []
        for i in range(1, 9):
            customers.append({
                "customer_id": 1000 + i,
                "mood": random.choice(moods),
                "patience_lvl": random.randint(10, 100),
                "satisfaction": random.randint(20, 100),
                "status": random.choice(statuses),
                "special_scenario": random.choice(scenarios),
            })
        return customers

    def _build_cards(self):
        self.cards.clear()
        cols, rows = 2, 4
        card_w = (self.width - 280) // cols - 16
        card_h = 130
        start_x, start_y = 220, 110
        gap_x, gap_y = 16, 14
        for i, cust in enumerate(self.customers):
            col = i % cols
            row = i // cols
            x = start_x + col * (card_w + gap_x)
            y = start_y + row * (card_h + gap_y)
            self.cards.append(CustomerCard(cust, x, y, card_w, card_h))

    def _compute_stats(self):
        if not self.customers:
            return {}
        avg_sat = sum(c["satisfaction"] for c in self.customers) / len(self.customers)
        avg_pat = sum(c["patience_lvl"] for c in self.customers) / len(self.customers)
        happy   = sum(1 for c in self.customers if c["mood"] in ("happy", "satisfied"))
        special = sum(1 for c in self.customers if c["special_scenario"])
        return {
            "total": len(self.customers),
            "avg_satisfaction": round(avg_sat, 1),
            "avg_patience": round(avg_pat, 1),
            "happy_count": happy,
            "special_count": special,
        }

    def _draw_sidebar(self):
        s = self.stats
        panel = pygame.Rect(0, 0, 210, self.height)
        pygame.draw.rect(self.screen, PANEL_BG, panel)
        pygame.draw.line(self.screen, PANEL_BORDER, (210, 0), (210, self.height), 1)

        y = 20
        title = self.font_lg.render("Customer", True, ACCENT_BLUE)
        self.screen.blit(title, (16, y)); y += 30
        title2 = self.font_lg.render("Tracker", True, TEXT_PRIMARY)
        self.screen.blit(title2, (16, y)); y += 50

        items = [
            ("Active Customers", str(s.get("total", 0)), ACCENT_BLUE),
            ("Avg Satisfaction", f"{s.get('avg_satisfaction', 0)}%", ACCENT_GREEN),
            ("Avg Patience",     f"{s.get('avg_patience', 0)}%",     ACCENT_YELLOW),
            ("Happy Customers",  str(s.get("happy_count", 0)),       ACCENT_GREEN),
            ("Special Events",   str(s.get("special_count", 0)),     ACCENT_RED),
        ]
        for label, value, color in items:
            lbl = self.font_xs.render(label.upper(), True, TEXT_DIM)
            val = self.font_lg.render(value, True, color)
            self.screen.blit(lbl, (16, y)); y += 16
            self.screen.blit(val, (16, y)); y += 36

        # Legend
        y = self.height - 160
        pygame.draw.line(self.screen, PANEL_BORDER, (12, y), (198, y), 1)
        y += 12
        leg = self.font_xs.render("MOOD LEGEND", True, TEXT_DIM)
        self.screen.blit(leg, (16, y)); y += 18
        for mood, color in list(MOOD_COLORS.items())[:5]:
            dot = pygame.Surface((8, 8), pygame.SRCALPHA)
            pygame.draw.circle(dot, color, (4, 4), 4)
            self.screen.blit(dot, (16, y + 3))
            ml = self.font_xs.render(mood.capitalize(), True, TEXT_SECONDARY)
            self.screen.blit(ml, (30, y)); y += 18

    def _draw_header(self):
        header = pygame.Rect(210, 0, self.width - 210, 95)
        pygame.draw.rect(self.screen, PANEL_BG, header)
        pygame.draw.line(self.screen, PANEL_BORDER, (210, 95), (self.width, 95), 1)

        title = self.font_lg.render("Live Customer Activity", True, TEXT_PRIMARY)
        self.screen.blit(title, (228, 18))
        sub = self.font_sm.render("Real-time tracking of all active customers in the store", True, TEXT_SECONDARY)
        self.screen.blit(sub, (228, 48))

        # Day badge
        badge_txt = self.font_sm.render("Day 4 | 2:30 PM", True, ACCENT_BLUE)
        bw = badge_txt.get_width() + 20
        pygame.draw.rect(self.screen, (20, 50, 100), (self.width - bw - 20, 30, bw, 28), border_radius=6)
        self.screen.blit(badge_txt, (self.width - badge_txt.get_width() - 30, 37))

    def run(self):
        while self.running:
            mouse = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self.running = False

            for card in self.cards:
                card.update_hover(mouse)

            self.screen.fill(BG_DARK)
            self._draw_sidebar()
            self._draw_header()
            for card in self.cards:
                card.draw(self.screen, self.font_sm, self.font_md)

            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()


if __name__ == "__main__":
    CustomerTrackerScreen().run()