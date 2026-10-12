# Отрисовка экранов OLED. Каждый экран рисует в готовый ImageDraw.
# Данные это список строк, глаза это персонаж с эмоциями, радар это полукруг
# с дальномером.

import math
import random

import oled_sources

# Радар: центр внизу по центру, полукруг вверх
RADAR_CX = 64
RADAR_CY = 62
RADAR_R = 56
RADAR_MAX_CM = 200.0


def draw_data(draw, font, items, values, labels):
    n = len(items)
    step = max(8, min(16, 60 // n)) if n else 8
    for i, key in enumerate(items):
        text = (labels.get(key, key) + ' ' + values.get(key, '--'))[:21]
        draw.text((4, 2 + i * step), text, font=font, fill=255)


def draw_radar(draw, font, points, updated, now):
    # сетка полукруга
    for frac in (0.33, 0.66, 1.0):
        r = int(RADAR_R * frac)
        draw.arc([RADAR_CX - r, RADAR_CY - r, RADAR_CX + r, RADAR_CY + r], 180, 360, fill=255)
    # луч вперед и бока
    draw.line([RADAR_CX, RADAR_CY, RADAR_CX, RADAR_CY - RADAR_R], fill=255)
    draw.line([RADAR_CX, RADAR_CY, RADAR_CX - RADAR_R, RADAR_CY], fill=255)
    draw.line([RADAR_CX, RADAR_CY, RADAR_CX + RADAR_R, RADAR_CY], fill=255)

    if not points or now - updated > 5:
        draw.text((34, 2), 'NO DATA', font=font, fill=255)
        return

    near = None
    for ang, dist in points:
        if dist is None or dist <= 0:
            continue
        if near is None or dist < near:
            near = dist
        d = min(RADAR_MAX_CM, dist)
        r = int(RADAR_R * d / RADAR_MAX_CM)
        rad = math.radians(ang)
        x = int(RADAR_CX + r * math.sin(rad))
        y = int(RADAR_CY - r * math.cos(rad))
        draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=255)

    if near is not None:
        draw.text((2, 2), '%.0fcm' % near, font=font, fill=255)


class EyesScreen:
    # Два глаза на весь экран. Эмоции: awake, surprised, sad, sleep.
    CX = (38, 90)
    CY = 32
    RX = 26
    RY = 22

    def __init__(self):
        self.blink_until = 0.0
        self.blink_next = 0.0
        self.look_x = 0.0
        self.look_next = 0.0
        self.surprise_until = 0.0

    def feed_events(self, now, options):
        # забрать все события и решить, на какие реагировать
        ev = oled_sources.pop_event()
        while ev is not None:
            want = ((ev == 'command' and options.get('react_command')) or
                    (ev == 'obstacle' and options.get('react_obstacle')) or
                    (ev == 'person' and options.get('react_person')))
            if want:
                self.surprise_until = now + (2.0 if ev == 'person' else 1.5)
            ev = oled_sources.pop_event()

    def _battery_pct(self, values):
        s = values.get('battery')
        if not s or not s.endswith('%'):
            return None
        try:
            return int(float(s[:-1]))
        except ValueError:
            return None

    def _emotion(self, now, options, values):
        if now < self.surprise_until:
            return 'surprised'
        if now - oled_sources.last_activity() > options.get('sleep_after', 120):
            return 'sleep'
        pct = self._battery_pct(values)
        if pct is not None and pct < options.get('bat_low', 20):
            return 'sad'
        return 'awake'

    def draw(self, draw, font, now, options, values):
        emo = self._emotion(now, options, values)

        # моргание и блуждание зрачков только в бодрствовании
        blink = False
        if emo in ('awake', 'sad'):
            if now > self.blink_next and now > self.blink_until:
                self.blink_until = now + 0.12
                self.blink_next = now + random.uniform(2.0, 5.0)
            blink = now < self.blink_until
            if now > self.look_next:
                self.look_x = random.choice([-1.0, -0.5, 0.0, 0.5, 1.0])
                self.look_next = now + random.uniform(1.0, 3.0)

        for cx in self.CX:
            if emo == 'sleep' or blink:
                # закрытый глаз: щель
                draw.line([cx - self.RX, self.CY, cx + self.RX, self.CY], fill=255, width=3)
                continue
            ry = self.RY
            if emo == 'surprised':
                ry = self.RY + 3
            elif emo == 'sad':
                ry = self.RY - 7
            draw.ellipse([cx - self.RX, self.CY - ry, cx + self.RX, self.CY + ry], fill=255)
            px = cx + int(self.look_x * 9)
            py = self.CY + (5 if emo == 'sad' else 0)
            pr = 8
            draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=0)
