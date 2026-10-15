# Экран OLED 0.96 (SSD1306, I2C 0x3C) как движок с эксклюзивными режимами.
# Ровно один режим занимает весь дисплей: данные, глаза, радар.
# Настройки лежат в .oled_config (объект mode/items/options). Поток рендера
# тикает с частотой кадров, значения собираются реже. Веб читает состояние
# через get_status() и меняет его set_*().

import json
import os
import threading
import time

import board
import busio
import psutil
from adafruit_ssd1306 import SSD1306_I2C
from PIL import Image, ImageDraw, ImageFont

import oled_screens
import oled_sources

OLED_ADDR = 0x3C
FPS = 15
COLLECT_SEC = 1.0
CONFIG_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), '.oled_config')

# Эксклюзивные режимы: выбран ровно один, остальные недоступны
MODES = ['data', 'eyes', 'radar']
DEFAULT_MODE = 'eyes'

AVAILABLE = ['time', 'date', 'temp', 'mem', 'cpu', 'battery', 'uptime']
DEFAULT_ITEMS = ['time', 'temp', 'mem', 'cpu']
MAX_ITEMS = 8

LABELS = {
    'time': 'TIME',
    'date': 'DATE',
    'temp': 'CPU TEMP',
    'mem': 'MEM',
    'cpu': 'LOAD',
    'battery': 'BAT',
    'uptime': 'UP',
}

DEFAULT_OPTIONS = {
    'bat_low': 20,        # ниже этого заряда глаза грустят
    'sleep_after': 120,   # столько секунд без событий и глаза засыпают
    'react_command': True,
    'react_obstacle': True,
    'react_person': True,
    'obstacle_cm': 30,    # с какого расстояния считать препятствием
}

_lock = threading.Lock()
_mode = DEFAULT_MODE
_items = list(DEFAULT_ITEMS)
_options = dict(DEFAULT_OPTIONS)
_values = {}
_providers = {}


def register_provider(key, fn):
    # app.py отдает сюда чтение батареи, чтобы не плодить второй доступ к АЦП
    _providers[key] = fn


def notify_event(kind):
    # WebServer дергает при команде из веба; сюда же придут препятствие и человек
    oled_sources.push_event(kind)


def _clean_items(keys):
    out = []
    for k in keys or []:
        if k in AVAILABLE and k not in out:
            out.append(k)
    return out[:MAX_ITEMS]


def _clean_options(data):
    opts = dict(DEFAULT_OPTIONS)
    for k in DEFAULT_OPTIONS:
        if isinstance(data, dict) and k in data:
            opts[k] = data[k]
    return opts


def _load_config():
    global _mode, _items, _options
    try:
        with open(CONFIG_PATH) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return
    if isinstance(data, list):
        # старый формат: просто список строк, значит экран данных
        _items = _clean_items(data)
        _mode = 'data'
    elif isinstance(data, dict):
        if data.get('mode') in MODES:
            _mode = data['mode']
        _items = _clean_items(data.get('items', _items))
        _options = _clean_options(data.get('options'))


def _save_config():
    with _lock:
        payload = {'mode': _mode, 'items': list(_items), 'options': dict(_options)}
    try:
        with open(CONFIG_PATH, 'w') as f:
            json.dump(payload, f)
    except OSError:
        pass


def get_status():
    with _lock:
        return {
            'mode': _mode,
            'modes': list(MODES),
            'items': list(_items),
            'available': list(AVAILABLE),
            'values': dict(_values),
            'options': dict(_options),
        }


def set_mode(mode):
    global _mode
    with _lock:
        if mode in MODES:
            _mode = mode
        result = _mode
    _save_config()
    return result


def set_items(keys):
    global _items
    with _lock:
        _items = _clean_items(keys)
        result = list(_items)
    _save_config()
    return result


def set_options(data):
    global _options
    with _lock:
        merged = dict(_options)
        merged.update(data or {})
        _options = _clean_options(merged)
        result = dict(_options)
    _save_config()
    return result


def _cpu_temp_c():
    # thermal_zone0 отдает миллиградусы
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f:
            return int(f.read().strip()) / 1000.0
    except (OSError, ValueError):
        return None


def _uptime_str():
    try:
        sec = int(time.time() - psutil.boot_time())
    except Exception:
        return '--'
    d, rem = divmod(sec, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return '%dd %02d:%02d' % (d, h, m)
    return '%02d:%02d' % (h, m)


def _collect():
    # собираем значения для всех строк, веб показывает любые из них
    vals = {}
    vals['time'] = time.strftime('%H:%M:%S')
    vals['date'] = time.strftime('%d.%m')
    temp = _cpu_temp_c()
    vals['temp'] = ('%.0fC' % temp) if temp is not None else '--'
    vals['mem'] = '%.0f%%' % psutil.virtual_memory().percent
    vals['cpu'] = '%.0f%%' % psutil.cpu_percent(None)
    bat = _providers.get('battery')
    if bat is not None:
        try:
            vals['battery'] = bat()
        except Exception:
            vals['battery'] = '--'
    else:
        vals['battery'] = '--'
    vals['uptime'] = _uptime_str()
    return vals


class OledDisplay(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            oled = SSD1306_I2C(128, 64, i2c, addr=OLED_ADDR)
        except Exception as e:
            # Нет дисплея или шины: не валим сервер, просто молчим
            print('OLED недоступен:', e)
            return

        img = Image.new('1', (128, 64))
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        eyes = oled_screens.EyesScreen()

        psutil.cpu_percent(None)  # прогрев: первый вызов всегда 0.0
        last_collect = 0.0

        while not self._stop.is_set():
            now = time.time()
            with _lock:
                mode = _mode
                items = list(_items)
                options = dict(_options)

            if now - last_collect >= COLLECT_SEC:
                vals = _collect()
                with _lock:
                    _values.clear()
                    _values.update(vals)
                last_collect = now
            with _lock:
                values = dict(_values)

            # наблюдатели поднимаются и гаснут под текущий режим и настройки
            oled_sources.ensure_watchers(mode, options)

            draw.rectangle((0, 0, 127, 63), outline=0, fill=0)
            if mode == 'eyes':
                eyes.feed_events(now, options)
                eyes.draw(draw, font, now, options, values)
            elif mode == 'radar':
                oled_sources.clear_events()
                points, updated = oled_sources.radar_snapshot()
                oled_screens.draw_radar(draw, font, points, updated, now)
            else:
                oled_sources.clear_events()
                oled_screens.draw_data(draw, font, items, values, LABELS)

            oled.image(img)
            oled.show()

            self._stop.wait(1.0 / FPS)

        oled_sources.stop_watchers()
        try:
            oled.fill(0)
            oled.show()
        except Exception:
            pass


_load_config()
