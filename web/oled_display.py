# Индикатор на OLED 0.96 (SSD1306, I2C 0x3C).
# Какие строки показывать, задает веб-панель: список ключей лежит в .oled_config.
# Порядок ключей это порядок строк сверху вниз. Данные собираются в фоновом
# потоке, веб забирает их через get_status().

import json
import os
import threading
import time

import board
import busio
import psutil
from adafruit_ssd1306 import SSD1306_I2C
from PIL import Image, ImageDraw, ImageFont

OLED_ADDR = 0x3C
REFRESH_SEC = 2
CONFIG_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), '.oled_config')

# Доступные строки. Порядок здесь это порядок в списке интерфейса.
AVAILABLE = ['time', 'date', 'temp', 'mem', 'cpu', 'battery', 'uptime']

# Что показываем, пока файла настроек нет
DEFAULT_ITEMS = ['time', 'temp', 'mem', 'cpu']

# Высота экрана 64 пикселя, строка 8 пикселей
MAX_ITEMS = 8

# Подписи на самом экране, латиницей: ширины мало
LABELS = {
    'time': 'TIME',
    'date': 'DATE',
    'temp': 'CPU TEMP',
    'mem': 'MEM',
    'cpu': 'LOAD',
    'battery': 'BAT',
    'uptime': 'UP',
}

_lock = threading.Lock()
_items = list(DEFAULT_ITEMS)
_values = {}      # ключ -> готовое значение
_providers = {}   # ключ -> функция без аргументов, значения отдает app.py


def register_provider(key, fn):
    # app.py отдает сюда чтение батареи, чтобы не плодить второй доступ к АЦП
    _providers[key] = fn


def _clean_items(keys):
    # только известные ключи, без дублей, не больше лимита
    out = []
    for k in keys or []:
        if k in AVAILABLE and k not in out:
            out.append(k)
    return out[:MAX_ITEMS]


def _load_items():
    global _items
    try:
        with open(CONFIG_PATH) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return
    if isinstance(data, list):
        _items = _clean_items(data)


def _save_items():
    try:
        with open(CONFIG_PATH, 'w') as f:
            json.dump(_items, f)
    except OSError:
        pass


def get_status():
    with _lock:
        return {
            'items': list(_items),
            'available': list(AVAILABLE),
            'values': dict(_values),
        }


def set_items(keys):
    global _items
    with _lock:
        _items = _clean_items(keys)
        result = list(_items)
    _save_items()
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

        psutil.cpu_percent(None)  # прогрев: первый вызов всегда 0.0

        while not self._stop.is_set():
            vals = _collect()
            with _lock:
                _values.clear()
                _values.update(vals)
                keys = list(_items)

            draw.rectangle((0, 0, 127, 63), outline=0, fill=0)
            n = len(keys)
            step = max(8, min(16, 60 // n)) if n else 8
            for i, key in enumerate(keys):
                text = (LABELS.get(key, key) + ' ' + vals.get(key, '--'))[:21]
                draw.text((4, 2 + i * step), text, font=font, fill=255)
            oled.image(img)
            oled.show()

            self._stop.wait(REFRESH_SEC)

        try:
            oled.fill(0)
            oled.show()
        except Exception:
            pass


_load_items()
