# RaspTank Docker

Docker-контейнер для управления танком Adeept RaspTank ADR013-V4 на Raspberry Pi 5.

Проект без привязки к путям: везде ниже используются плейсхолдеры.
При установке подставляйте свои значения:

- `<путь_к_клону_репозитория>` - где склонирован этот репозиторий
- `<IP_хоста>` - IP-адрес Pi в локальной сети
- `<URL_репозитория>` - адрес твоего репозитория на GitHub
- `<пользователь>` - системный пользователь, от которого работает Docker

## Быстрый старт

```bash
cd <путь_к_клону_репозитория>

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

- Веб-интерфейс: `http://<IP_хоста>:5000`
- Видеопоток: `http://<IP_хоста>:5000/video_feed`
- Зуммер писк: `http://<IP_хоста>:5000/api/buzzer/beep`
- Зуммер песня: `http://<IP_хоста>:5000/api/buzzer/song`
- Зуммер стоп: `http://<IP_хоста>:5000/api/buzzer/stop`
- Переворот камеры на 180°: `POST http://<IP_хоста>:5000/api/camera/flip` (GET - текущее состояние)
- WebSocket управления: `ws://<IP_хоста>:8888`

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

## Структура репозитория

```
<путь_к_клону_репозитория>/
├── Dockerfile              # Сборка образа (debian:trixie + RPi-репо)
├── docker-compose.yml      # privileged, host network, LG_WD=/tmp
├── .dockerignore           # .git и мусор не попадают в образ
├── README.md               # Оригинальный README с GitHub. НЕ ТРОГАТЬ
├── README-custom.md        # Этот файл
├── examples/               # Примеры с роботом (оригинал)
├── Client/                 # GUI-клиент (оригинал)
└── web/                    # Код веб-интерфейса
    ├── WebServer.py        # Точка входа, WebSocket 8888
    ├── app.py              # Flask, порт 5000, зуммер-эндпоинты
    ├── robotLight.py       # Пропатчен (try/except для rpi_ws281x)
    ├── switch.py           # Урезан под робота
    └── dist/               # Фронтенд (Vue)
```

## Что внутри контейнера

- Debian 13 trixie (aarch64)
- Python 3.13
- Все зависимости: adafruit-blinka, gpiozero, opencv, picamera2, flask, websockets
- lgpio из системного пакета RPi-репо (не pip)
- Камера, I2C, SPI доступны через privileged + host network

## Кастомные правки

Все свое живет только в ветке `custom`:

- `web/app.py` - эндпоинты зуммера `/api/buzzer/beep`, `/api/buzzer/song`, `/api/buzzer/stop`. Стоп мелодии через `threading.Event`
- `web/robotLight.py` - `try/except` вокруг `from rpi_ws281x import *`, чтобы код запускался там, где библиотеки нет
- `web/switch.py` - урезан под робота
- `web/camera_opencv.py` - переворот кадра на 180° через `cv2.flip` (флаг `flip180`, состояние в файле `.camera_flip`, переживает рестарт). Для камеры, закрепленной шлейфом вверх ногами
- `web/dist/index.html` - кнопка переворота камеры в карточке Video (логика и стили в `web/dist/js/lang.js`)
- `web/dist/js/lang.js` + `web/dist/lang.json` - перевод интерфейса на русский и кнопка EN|RU в шапке. Исходников фронта нет (только собранный Vue), английский зашит в бандл, русский подменяется поверх DOM, выбор языка помнится в localStorage
- `web/dist/index.html` - сетка перебалансирована под длинные русские подписи: 5+4+3 вместо 6+4+2, правый столбик с карточкой «Действия» шире. Плюс перенос текста в кнопках как страховка
- `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `README-custom.md` - Docker-обвязка, в оригинале таких файлов нет

## Git

- `origin` = `<URL_репозитория>` (приватный, твой)
- `upstream` = <https://github.com/adeept/adeept_rasptank2> (оригинал)
- Рабочая ветка: `custom`
- `master` - зеркало оригинала, обновляется из `upstream`

Обновление из оригинала:

```bash
git fetch upstream
git merge upstream/master
```

Конфликты возможны максимум на четырех кастомных файлах (`app.py`, `robotLight.py`, `switch.py`, `camera_opencv.py`), остальное сливается само.

Свой код коммитить и пушить только в `custom`:

```bash
git add <файлы>
git commit -m "описание"
git push origin custom
```

## Перед запуском на новой системе

1. Установить Docker: `curl -fsSL https://get.docker.com | sudo sh`
2. Добавить пользователя в группу docker: `sudo usermod -aG docker <пользователь>` (после этого перелогиниться)
3. Включить I2C и SPI: `sudo raspi-config` -> Interface Options
4. Настроить камеру в `/boot/firmware/config.txt`:

```text
[pi5]
dtoverlay=ov5647
dtoverlay=nospi10
dtoverlay=dwc2,dr_mode=peripheral
```

1. Склонировать репозиторий в `<путь_к_клону_репозитория>`
2. Собрать и запустить (см. Быстрый старт)

## Автозапуск

Двух уровней хватает:

```bash
# 1. Docker сам стартует после перезагрузки
sudo systemctl enable docker

# 2. Контейнер сам поднимается после старта Docker
#    Это уже прописано в docker-compose.yml:
#    restart: unless-stopped
```

Дополнительный systemd-сервис для контейнера не нужен.

## Обновление кода

Код смонтирован как volume. Правки на хосте видны сразу, но нужен перезапуск:

```bash
nano <путь_к_клону_репозитория>/web/app.py
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

- Не трогать `README.md`, это оригинальный файл с GitHub
- Не выносить кастомные правки за пределы ветки `custom`
- Не запускать WebServer.py на хосте параллельно с контейнером
- Не запускать серво/моторы с разряженной батареей
- Не удалять патч robotLight.py
- Не ставить pip-пакеты на хосте
