# RaspTank Docker

Docker-контейнер для управления танком Adeept RaspTank ADR013-V4 на Raspberry Pi 5.

## Быстрый старт

```bash
cd /home/opencode/docker_my/rasptank

# Собрать образ (первый раз, 10-20 минут)
docker compose build

# Запустить
docker compose up -d

# Проверить
docker ps --filter name=rasptank
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:5000/
# Должно быть: 200
```

## Доступ

- Веб-интерфейс: `http://192.168.50.177:5000`
- Видеопоток: `http://192.168.50.177:5000/video_feed`
- Зуммер писк: `http://192.168.50.177:5000/api/buzzer/beep`
- Зуммер песня: `http://192.168.50.177:5000/api/buzzer/song`
- Зуммер стоп: `http://192.168.50.177:5000/api/buzzer/stop`

## Управление контейнером

```bash
# Остановить
docker compose down

# Перезапустить (после правки кода)
docker compose restart

# Пересоздать (после изменения docker-compose.yml)
docker compose up -d --force-recreate

# Пересобрать (после изменения Dockerfile)
docker compose build

# Логи
docker logs -f rasptank_web

# Войти внутрь
docker exec -it rasptank_web bash
```

Если пользователь не в группе `docker`, добавлять `sudo` перед каждой командой.

## Структура

```
rasptank/
├── Dockerfile              # Сборка образа (debian:trixie + RPi-репо)
├── docker-compose.yml      # privileged, host network, lgpio factory
├── README.md               # Этот файл
└── adeept_rasptank2/       # Код робота (volume mount)
    └── web/
        ├── WebServer.py    # Точка входа, WebSocket 8888
        ├── app.py          # Flask, порт 5000, зуммер-эндпоинты
        ├── robotLight.py   # Пропатчен (try/except для rpi_ws281x)
        └── ...
```

## Что внутри контейнера

- Debian 13 trixie (aarch64)
- Python 3.13
- Все зависимости: adafruit-blinka, gpiozero, opencv, picamera2, flask, websockets
- lgpio из системного пакета RPi-репо (не pip)
- Камера, I2C, SPI доступны через privileged + host network

## Перед запуском на новой системе

1. Установить Docker: `curl -fsSL https://get.docker.com | sudo sh`
2. Включить I2C и SPI: `sudo raspi-config` -> Interface Options
3. Настроить камеру в `/boot/firmware/config.txt`:

```ini
[pi5]
dtoverlay=ov5647
dtoverlay=nospi10
dtoverlay=dwc2,dr_mode=peripheral
```

4. Скопировать папку `rasptank/` на Pi
5. Собрать и запустить (см. Быстрый старт)

## Автозапуск

Создать `/etc/systemd/system/rasptank-docker.service`:

```ini
[Unit]
Description=RaspTank Docker Container
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=opencode
WorkingDirectory=/home/opencode/docker_my/rasptank
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
```

Включить:

```bash
sudo systemctl daemon-reload
sudo systemctl enable rasptank-docker.service
```

## Обновление кода

Код смонтирован как volume. Правки на хосте видны сразу, но нужен перезапуск:

```bash
nano /home/opencode/docker_my/rasptank/adeept_rasptank2/web/app.py
docker compose restart
```

## Проблемы

**Контейнер рестартует в цикле** - смотреть логи:
```bash
docker logs rasptank_web
```

**GPIO busy** - другой процесс держит пины. Проверить, не запущен ли WebServer.py на хосте.

**Камера не видна** - проверить оверлей:
```bash
grep ov5647 /boot/firmware/config.txt
```

**Робот выключается при запуске** - батарея разряжена. Зарядить до 8.4 В.

## Не делать

- Не запускать WebServer.py на хосте параллельно с контейнером
- Не запускать серво/моторы с разряженной батареей
- Не удалять патч robotLight.py
- Не ставить pip-пакеты на хосте
