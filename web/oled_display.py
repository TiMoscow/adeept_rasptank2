# Индикатор на OLED 0.96 (SSD1306, I2C 0x3C).
# Показывает время, температуру CPU, загрузку памяти и CPU.
# Крутится в фоновом потоке, не мешает основному серверу.

import threading
import time

import board
import busio
import psutil
from adafruit_ssd1306 import SSD1306_I2C
from PIL import Image, ImageDraw, ImageFont

OLED_ADDR = 0x3C
REFRESH_SEC = 2


def cpu_temp_c():
    # thermal_zone0 отдает миллиградусы
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f:
            raw = int(f.read().strip())
        return raw / 1000.0
    except (OSError, ValueError):
        return None


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
            # Нет дисплея или шины - не валим сервер, просто молчим
            print('OLED недоступен:', e)
            return

        img = Image.new('1', (128, 64))
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()

        # прогрев cpu_percent, первый вызов всегда 0.0
        psutil.cpu_percent(None)

        while not self._stop.is_set():
            draw.rectangle((0, 0, 127, 63), outline=0, fill=0)

            draw.text((4, 4), time.strftime('%d.%m %H:%M:%S'), font=font, fill=255)

            temp = cpu_temp_c()
            temp_str = f'{temp:.0f}C' if temp is not None else 'CPU --'
            draw.text((4, 24), 'CPU TEMP ' + temp_str, font=font, fill=255)

            mem = psutil.virtual_memory().percent
            cpu = psutil.cpu_percent(None)
            draw.text((4, 44), f'MEM {mem:.0f}%  CPU {cpu:.0f}%', font=font, fill=255)

            oled.image(img)
            oled.show()

            self._stop.wait(REFRESH_SEC)

        try:
            oled.fill(0)
            oled.show()
        except Exception:
            pass