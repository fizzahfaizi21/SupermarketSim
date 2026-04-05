"""
Feature 10: Player Health Management UI
Tracks stress and fatigue during a shift. Allows scheduling breaks.
Displays performance modifiers and burnout warnings.
"""

import pygame
import math

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
WHITE          = (255, 255, 255)


def lerp_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def bar_color(pct):
    if pct < 0.4:  return ACCENT_GREEN
    if pct < 0.7:  return ACCENT_YELLOW
    return ACCENT_RED


class GaugeWidget:
    """Circular gauge for stress or fatigue."""

    def __init__(self, cx, cy, r, value, label, color):
        self.cx, self.cy, self.r = cx, cy, r
        self.value = value   # 0-100
        self.label = label
        self.color = color

    def draw(self, surface, font_md, font_sm, font_xs):
        # Background arc (full circle)
        pygame.draw.circle(surface, PANEL_BORDER, (self.cx, self.cy), self.r, 8)

        # Colored arc
        if self.value > 0:
            start_angle = -math.pi / 2
            end_angle   = start_angle + (2 * math.pi * self.value / 100)
            steps = max(int(self.value * 2), 4)
            for i in range(steps):
                a = start_angle + (end_angle - start_angle) * i / steps
                a2= start_angle + (end_angle - start_angle) * (i + 1) / steps
                x1 = self.cx + (self.r - 4) * math.cos(a)
                y1 = self.cy + (self.r - 4) * math.sin(a)
                x2 = self.cx + (self.r - 4) * math.cos(a2)
                y2 = self.cy + (self.r - 4) * math.sin(a2)
                pygame.draw.line(surface, self.color, (int(x1), int(y1)), (int(x2), int(y2)), 8)

        # Inner fill
        pygame.draw.circle(surface, BG_DARK, (self.cx, self.cy), self.r - 12)

        # Value text
        val_s = font_md.render(f"{self.value}%", True, self.color)
        surface.blit(val_s, (self.cx - val_s.get_width() // 2, self.cy - 14))

        lbl_s = font_xs.render(self.label, True, TEXT_SECONDARY)
        surface.blit(lbl_s, (self.cx - lbl_s.get_width() // 2, self.cy + 12))


class PlayerHealthScreen:
    """
    Feature 10 — Player Health Management
    Tracks stress and fatigue with visual indicators.
    Shows break button, performance modifiers, and burnout alerts.
    """

    def __init__(self, width=1100, height=720):
        pygame.init()
        self.width, self.height = width, height
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("SupermarketSim — Player Health")

        self.font_lg  = pygame.font.SysFont("Segoe UI", 28, bold=True)
        self.font_md  = pygame.font.SysFont("Segoe UI", 20, bold=True)
        self.font_sm  = pygame.font.SysFont("Segoe UI", 14)
        self.font_xs  = pygame.font.SysFont("Segoe UI", 12)

        # Simulated state
        self.stress    = 72
        self.fatigue   = 58
        self.stamina   = 65
        self.on_break  = False
        self.burnout   = self.stress >= 80 and self.fatigue >= 80
        self.perf_mod  = self._calc_perf_mod()
        self.break_btn = pygame.Rect(self.width - 250, self.height - 80, 200, 44)
        self.clock = pygame.time.Clock()
        self.running = True
        self.flash_timer = 0

    def _calc_perf_mod(self):
        combined = (self.stress + self.fatigue) / 2
        if combined < 40:  return +10
        if combined < 60:  return 0
        if combined < 75:  return -10
        return -25

    def _draw_main_gauges(self):
        cx_base = 320
        cy = 310

        stress_color = bar_color(self.stress / 100)
        fatigue_color = bar_color(self.fatigue / 100)

        g1 = GaugeWidget(cx_base, cy, 90, self.stress, "STRESS", stress_color)
        g2 = GaugeWidget(cx_base + 220, cy, 90, self.fatigue, "FATIGUE", fatigue_color)
        g1.draw(self.screen, self.font_md, self.font_sm, self.font_xs)
        g2.draw(self.screen, self.font_md, self.font_sm, self.font_xs)

        # Labels
        s_lbl = self.font_sm.render("Current Stress Level", True, TEXT_SECONDARY)
        self.screen.blit(s_lbl, (cx_base - s_lbl.get_width() // 2, cy + 100))
        f_lbl = self.font_sm.render("Current Fatigue Level", True, TEXT_SECONDARY)
        self.screen.blit(f_lbl, (cx_base + 220 - f_lbl.get_width() // 2, cy + 100))

    def _draw_stamina_bar(self):
        x, y = 230, 440
        w, h = 400, 22
        label = self.font_sm.render("Player Stamina", True, TEXT_SECONDARY)
        self.screen.blit(label, (x, y - 20))
        pygame.draw.rect(self.screen, PANEL_BORDER, (x, y, w, h), border_radius=10)
        fill = int(w * self.stamina / 100)
        sc = ACCENT_GREEN if self.stamina > 60 else (ACCENT_YELLOW if self.stamina > 30 else ACCENT_RED)
        pygame.draw.rect(self.screen, sc, (x, y, fill, h), border_radius=10)
        pct = self.font_sm.render(f"{self.stamina}%", True, WHITE)
        self.screen.blit(pct, (x + w + 10, y + 2))

    def _draw_perf_modifier(self):
        x, y = 230, 510
        label = self.font_sm.render("Performance Modifier", True, TEXT_SECONDARY)
        self.screen.blit(label, (x, y))
        mod = self.perf_mod
        color = ACCENT_GREEN if mod > 0 else (TEXT_SECONDARY if mod == 0 else ACCENT_RED)
        sign = "+" if mod >= 0 else ""
        mod_txt = self.font_md.render(f"{sign}{mod}%", True, color)
        self.screen.blit(mod_txt, (x, y + 22))

        desc = {
            10:  "Energized — boosted efficiency!",
            0:   "Neutral — performing normally.",
            -10: "Tired — slight performance drop.",
            -25: "Exhausted — take a break now!",
        }
        desc_txt = self.font_xs.render(desc.get(mod, ""), True, TEXT_DIM)
        self.screen.blit(desc_txt, (x, y + 52))

    def _draw_burnout_warning(self):
        if not self.burnout:
            return
        self.flash_timer += 1
        alpha = int(128 + 127 * math.sin(self.flash_timer * 0.1))
        overlay = pygame.Surface((self.width, 60), pygame.SRCALPHA)
        overlay.fill((255, 50, 50, alpha // 3))
        self.screen.blit(overlay, (0, 0))

        warn = self.font_md.render("⚠  BURNOUT WARNING — Performance severely reduced!", True, ACCENT_RED)
        self.screen.blit(warn, (self.width // 2 - warn.get_width() // 2, 20))

    def _draw_break_button(self):
        mouse = pygame.mouse.get_pos()
        hover = self.break_btn.collidepoint(mouse)
        color = ACCENT_GREEN if not self.on_break else ACCENT_YELLOW
        bg = (30, 80, 50) if not hover else (40, 110, 65)
        pygame.draw.rect(self.screen, bg, self.break_btn, border_radius=10)
        pygame.draw.rect(self.screen, color, self.break_btn, 2, border_radius=10)
        label = "Take a Break" if not self.on_break else "Break Active ✓"
        btn_txt = self.font_sm.render(label, True, color)
        self.screen.blit(btn_txt, (
            self.break_btn.centerx - btn_txt.get_width() // 2,
            self.break_btn.centery - btn_txt.get_height() // 2
        ))

    def _draw_history_bars(self):
        """Show a simple shift-hour timeline of stress."""
        x, y = 660, 210
        w_total = 380
        self.screen.blit(self.font_sm.render("Stress Over Shift", True, TEXT_SECONDARY), (x, y - 22))
        hours = [20, 35, 50, 68, 72, 65, 72, 80]
        bar_w = w_total // len(hours) - 6
        for i, val in enumerate(hours):
            bx = x + i * (bar_w + 6)
            bh = int(140 * val / 100)
            by = y + 140 - bh
            pygame.draw.rect(self.screen, bar_color(val / 100), (bx, by, bar_w, bh), border_radius=3)
            hr_lbl = self.font_xs.render(f"H{i+1}", True, TEXT_DIM)
            self.screen.blit(hr_lbl, (bx + bar_w // 2 - hr_lbl.get_width() // 2, y + 144))

    def _draw_sidebar(self):
        panel = pygame.Rect(0, 0, 210, self.height)
        pygame.draw.rect(self.screen, PANEL_BG, panel)
        pygame.draw.line(self.screen, PANEL_BORDER, (210, 0), (210, self.height), 1)

        y = 24
        t1 = self.font_lg.render("Health", True, ACCENT_GREEN)
        self.screen.blit(t1, (16, y)); y += 32
        t2 = self.font_lg.render("Monitor", True, TEXT_PRIMARY)
        self.screen.blit(t2, (16, y)); y += 54

        items = [
            ("Stress",         f"{self.stress}%",   bar_color(self.stress / 100)),
            ("Fatigue",        f"{self.fatigue}%",  bar_color(self.fatigue / 100)),
            ("Stamina",        f"{self.stamina}%",  ACCENT_BLUE),
            ("Break Status",   "Active" if self.on_break else "Not taken", ACCENT_GREEN if self.on_break else ACCENT_RED),
            ("Burnout Risk",   "HIGH" if self.burnout else "LOW",          ACCENT_RED if self.burnout else ACCENT_GREEN),
        ]
        for label, val, color in items:
            ll = self.font_xs.render(label.upper(), True, TEXT_DIM)
            vl = self.font_md.render(val, True, color)
            self.screen.blit(ll, (16, y)); y += 16
            self.screen.blit(vl, (16, y)); y += 34

        # Tips
        y = self.height - 130
        pygame.draw.line(self.screen, PANEL_BORDER, (12, y), (198, y), 1); y += 12
        tips = ["Take breaks regularly.", "Minimize errors.", "Serve customers fast."]
        tip_lbl = self.font_xs.render("TIPS", True, TEXT_DIM)
        self.screen.blit(tip_lbl, (16, y)); y += 16
        for tip in tips:
            ts = self.font_xs.render(f"• {tip}", True, TEXT_SECONDARY)
            self.screen.blit(ts, (16, y)); y += 16

    def _draw_header(self):
        header = pygame.Rect(210, 0, self.width - 210, 95)
        pygame.draw.rect(self.screen, PANEL_BG, header)
        pygame.draw.line(self.screen, PANEL_BORDER, (210, 95), (self.width, 95), 1)
        title = self.font_lg.render("Player Health & Wellbeing", True, TEXT_PRIMARY)
        self.screen.blit(title, (228, 18))
        sub = self.font_xs.render("Monitor stress, fatigue, and stamina — take breaks to restore performance", True, TEXT_SECONDARY)
        self.screen.blit(sub, (228, 50))

    def run(self):
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self.running = False
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if self.break_btn.collidepoint(event.pos):
                        self.on_break = not self.on_break
                        if self.on_break:
                            self.stress  = max(0, self.stress - 20)
                            self.fatigue = max(0, self.fatigue - 20)
                            self.stamina = min(100, self.stamina + 15)
                            self.burnout = False
                            self.perf_mod = self._calc_perf_mod()

            self.screen.fill(BG_DARK)
            self._draw_sidebar()
            self._draw_header()
            self._draw_main_gauges()
            self._draw_stamina_bar()
            self._draw_perf_modifier()
            self._draw_history_bars()
            self._draw_burnout_warning()
            self._draw_break_button()
            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()


if __name__ == "__main__":
    PlayerHealthScreen().run()