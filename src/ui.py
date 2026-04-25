# src/ui.py

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import pygame

from config.settings import (
    ACCENT,
    ACCENT_2,
    BIG_TITLE,
    BODY_SIZE,
    BUTTON_CLICK_SCALE,
    BUTTON_HOVER_SCALE,
    BUTTON_TEXT_SIZE,
    CARD,
    DANGER,
    FONT_STACK,
    INFO,
    NUMBER_LERP_SPEED,
    OUTLINE,
    PANEL,
    PANEL_ALT,
    SHADOW,
    SMALL_SIZE,
    SOFT_GLOW,
    SUCCESS,
    TEXT,
    TEXT_DARK,
    TEXT_MUTED,
    TITLE_SIZE,
    TOAST_LIFETIME,
    TOAST_SLIDE_SPEED,
    UI_ANIM_SPEED,
    WARNING,
)


pygame.font.init()


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * clamp(t, 0.0, 1.0)


def ease_out_quad(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    return 1 - (1 - t) * (1 - t)


def ease_out_back(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


_FONT_CACHE: dict[tuple[int, bool], pygame.font.Font] = {}


def get_font(size: int, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    for name in FONT_STACK:
        match = pygame.font.match_font(name, bold=bold)
        if match:
            font = pygame.font.Font(match, size)
            font.set_bold(bold)
            _FONT_CACHE[key] = font
            return font

    font = pygame.font.SysFont("arial", size, bold=bold)
    _FONT_CACHE[key] = font
    return font


def draw_text(
    surface: pygame.Surface,
    text: str,
    pos: Tuple[int, int] | Tuple[float, float],
    size: int = BODY_SIZE,
    color: Tuple[int, int, int] = TEXT,
    bold: bool = False,
    center: bool = False,
    alpha: int = 255,
):
    font = get_font(size, bold)
    rendered = font.render(str(text), True, color)
    if alpha != 255:
        rendered.set_alpha(alpha)
    rect = rendered.get_rect(center=pos) if center else rendered.get_rect(topleft=pos)
    surface.blit(rendered, rect)
    return rect


def draw_vertical_gradient(surface: pygame.Surface, top_color, bottom_color):
    width, height = surface.get_size()
    for y in range(height):
        t = y / max(1, height - 1)
        color = (
            int(lerp(top_color[0], bottom_color[0], t)),
            int(lerp(top_color[1], bottom_color[1], t)),
            int(lerp(top_color[2], bottom_color[2], t)),
        )
        pygame.draw.line(surface, color, (0, y), (width, y))


def rounded_rect_surface(size, color, radius=20, border_color=None, border_width=0):
    surf = pygame.Surface(size, pygame.SRCALPHA)
    pygame.draw.rect(surf, color, surf.get_rect(), border_radius=radius)
    if border_color and border_width > 0:
        pygame.draw.rect(
            surf,
            border_color,
            surf.get_rect(),
            width=border_width,
            border_radius=radius,
        )
    return surf


def draw_shadowed_card(
    surface: pygame.Surface,
    rect: pygame.Rect,
    color=PANEL,
    radius: int = 24,
    shadow_offset: int = 7,
    border_color=OUTLINE,
    border_width: int = 1,
):
    shadow = pygame.Surface((rect.width + 16, rect.height + 16), pygame.SRCALPHA)
    pygame.draw.rect(
        shadow,
        SHADOW,
        shadow.get_rect(),
        border_radius=radius + 6,
    )
    surface.blit(shadow, (rect.x - 8, rect.y - 2 + shadow_offset))
    card = rounded_rect_surface(rect.size, color, radius, border_color, border_width)
    surface.blit(card, rect.topleft)


def draw_badge(surface, text, x, y, color=ACCENT):
    font = get_font(SMALL_SIZE, True)
    label = font.render(text, True, TEXT_DARK if color != DANGER else TEXT)
    pad_x, pad_y = 14, 8
    rect = label.get_rect()
    box = pygame.Rect(x, y, rect.width + pad_x * 2, rect.height + pad_y * 2)
    draw_shadowed_card(surface, box, color=color, radius=14, shadow_offset=3, border_width=0)
    surface.blit(label, (box.x + pad_x, box.y + pad_y))


@dataclass
class Toast:
    text: str
    color: Tuple[int, int, int]
    duration: float
    created_at: float
    y_offset: float = -40.0


class ToastManager:
    def __init__(self):
        self.toasts: List[Toast] = []

    def show(self, text: str, color=INFO, duration: float = TOAST_LIFETIME):
        self.toasts.append(Toast(text=text, color=color, duration=duration, created_at=time.time()))

    def update(self, dt: float):
        now = time.time()
        remaining: List[Toast] = []
        for toast in self.toasts:
            age = now - toast.created_at
            if age < toast.duration:
                target_y = 0.0
                toast.y_offset = lerp(toast.y_offset, target_y, dt * TOAST_SLIDE_SPEED)
                remaining.append(toast)
        self.toasts = remaining

    def draw(self, surface: pygame.Surface):
        if not self.toasts:
            return

        width = surface.get_width()
        now = time.time()
        stack_y = 28

        for idx, toast in enumerate(self.toasts[-4:]):
            age = now - toast.created_at
            fade_tail = 0.55
            alpha = 255
            if age > toast.duration - fade_tail:
                alpha = int(255 * max(0.0, (toast.duration - age) / fade_tail))

            box = pygame.Rect(width - 390, stack_y + idx * 68 + int(toast.y_offset), 340, 52)
            panel = pygame.Surface(box.size, pygame.SRCALPHA)
            pygame.draw.rect(panel, (*toast.color, alpha), panel.get_rect(), border_radius=18)
            pygame.draw.rect(panel, (255, 255, 255, min(70, alpha)), panel.get_rect(), 1, border_radius=18)
            shadow = pygame.Surface((box.width + 12, box.height + 12), pygame.SRCALPHA)
            pygame.draw.rect(shadow, (0, 0, 0, min(72, alpha // 3)), shadow.get_rect(), border_radius=22)
            surface.blit(shadow, (box.x - 6, box.y + 4))
            surface.blit(panel, box.topleft)
            draw_text(surface, toast.text, (box.x + 16, box.y + 15), size=BODY_SIZE, alpha=alpha)


class AnimatedValue:
    def __init__(self, value: float = 0.0):
        self.value = float(value)
        self.target = float(value)

    def set(self, value: float):
        self.target = float(value)

    def update(self, dt: float):
        self.value = lerp(self.value, self.target, dt * NUMBER_LERP_SPEED)

    def as_int(self) -> int:
        return int(round(self.value))


class Button:
    def __init__(
        self,
        rect,
        text: str,
        on_click: Callable[[], None],
        accent=ACCENT,
        variant: str = "primary",
        icon: Optional[str] = None,
    ):
        self.base_rect = pygame.Rect(rect)
        self.text = text
        self.on_click = on_click
        self.accent = accent
        self.variant = variant
        self.icon = icon

        self.hovered = False
        self.pressed = False
        self.hover_t = 0.0
        self.press_t = 0.0
        self.enabled = True

    def current_rect(self) -> pygame.Rect:
        hover_scale = lerp(1.0, BUTTON_HOVER_SCALE, self.hover_t)
        press_scale = lerp(1.0, BUTTON_CLICK_SCALE, self.press_t)
        scale = hover_scale * press_scale
        w = int(self.base_rect.width * scale)
        h = int(self.base_rect.height * scale)
        rect = pygame.Rect(0, 0, w, h)
        rect.center = self.base_rect.center
        return rect

    def handle_event(self, event):
        if not self.enabled:
            return

        rect = self.current_rect()

        if event.type == pygame.MOUSEMOTION:
            self.hovered = rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if rect.collidepoint(event.pos):
                self.pressed = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.pressed and rect.collidepoint(event.pos):
                self.on_click()
            self.pressed = False

    def update(self, dt: float):
        self.hover_t = lerp(self.hover_t, 1.0 if self.hovered else 0.0, dt * UI_ANIM_SPEED)
        self.press_t = lerp(self.press_t, 1.0 if self.pressed else 0.0, dt * (UI_ANIM_SPEED * 1.5))

    def _colors(self):
        if self.variant == "danger":
            base = DANGER
            text = TEXT
        elif self.variant == "secondary":
            base = ACCENT_2
            text = TEXT_DARK
        elif self.variant == "menu":
            base = self.accent
            text = TEXT_DARK if self.accent == ACCENT_2 else TEXT
        else:
            base = self.accent
            text = TEXT_DARK if self.accent == ACCENT_2 else TEXT

        lift = int(24 * self.hover_t)
        color = (
            clamp(base[0] + lift, 0, 255),
            clamp(base[1] + lift, 0, 255),
            clamp(base[2] + lift, 0, 255),
        )
        return color, text

    def draw(self, surface: pygame.Surface):
        rect = self.current_rect()
        color, text_color = self._colors()

        glow_alpha = int(55 * self.hover_t)
        if glow_alpha > 0:
            glow = pygame.Surface((rect.width + 28, rect.height + 28), pygame.SRCALPHA)
            pygame.draw.rect(glow, (*color, glow_alpha), glow.get_rect(), border_radius=24)
            surface.blit(glow, (rect.x - 14, rect.y - 10))

        shadow = pygame.Surface((rect.width + 12, rect.height + 12), pygame.SRCALPHA)
        pygame.draw.rect(shadow, (0, 0, 0, 70), shadow.get_rect(), border_radius=24)
        surface.blit(shadow, (rect.x - 6, rect.y + 5))

        btn = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(btn, color, btn.get_rect(), border_radius=20)
        pygame.draw.rect(btn, (255, 255, 255, 40), btn.get_rect(), 1, border_radius=20)

        highlight = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(highlight, SOFT_GLOW, (2, 2, rect.width - 4, rect.height // 2), border_radius=18)
        btn.blit(highlight, (0, 0))

        surface.blit(btn, rect.topleft)

        label = f"{self.icon}  {self.text}" if self.icon else self.text
        draw_text(surface, label, rect.center, size=BUTTON_TEXT_SIZE, color=text_color, bold=True, center=True)


class TextInput:
    def __init__(self, rect, placeholder: str, password: bool = False):
        self.rect = pygame.Rect(rect)
        self.placeholder = placeholder
        self.password = password
        self.text = ""
        self.active = False
        self.caret_timer = 0.0
        self.focus_t = 0.0

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.active = self.rect.collidepoint(event.pos)
        elif event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key == pygame.K_TAB:
                pass
            elif event.key == pygame.K_RETURN:
                pass
            elif event.unicode and event.unicode.isprintable():
                self.text += event.unicode

    def update(self, dt: float):
        self.caret_timer += dt
        self.focus_t = lerp(self.focus_t, 1.0 if self.active else 0.0, dt * UI_ANIM_SPEED)

    def draw(self, surface: pygame.Surface):
        glow_alpha = int(40 * self.focus_t)
        if glow_alpha > 0:
            glow = pygame.Surface((self.rect.width + 22, self.rect.height + 22), pygame.SRCALPHA)
            pygame.draw.rect(glow, (76, 175, 80, glow_alpha), glow.get_rect(), border_radius=24)
            surface.blit(glow, (self.rect.x - 11, self.rect.y - 11))

        draw_shadowed_card(
            surface,
            self.rect,
            color=PANEL_ALT if self.active else CARD,
            radius=18,
            shadow_offset=4,
            border_color=ACCENT if self.active else OUTLINE,
        )

        visible = "*" * len(self.text) if self.password else self.text
        shown = visible if visible else self.placeholder
        color = TEXT if self.text else TEXT_MUTED
        draw_text(surface, shown, (self.rect.x + 18, self.rect.y + 17), size=BODY_SIZE, color=color)

        if self.active and int(self.caret_timer * 1.7) % 2 == 0:
            font = get_font(BODY_SIZE)
            text_width = font.size(visible)[0]
            x = self.rect.x + 18 + text_width + 2
            pygame.draw.line(surface, TEXT, (x, self.rect.y + 14), (x, self.rect.bottom - 14), 2)


class SceneFader:
    def __init__(self):
        self.alpha = 0
        self.target = 0

    def fade_in(self):
        self.alpha = 255
        self.target = 0

    def fade_out(self):
        self.target = 255

    def update(self, dt: float):
        speed = 8.5
        self.alpha = lerp(self.alpha, self.target, dt * speed)

    def draw(self, surface: pygame.Surface):
        alpha = int(clamp(self.alpha, 0, 255))
        if alpha <= 1:
            return
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((8, 10, 20, alpha))
        surface.blit(overlay, (0, 0))