"""Фото по кнопке и съемка по расписанию (timelapse) для RaspTank.

Модуль не зависит от камеры: источник кадров передается в PhotoService
как функция get_frame(), которая возвращает numpy-массив (BGR) или None.
"""
import json
import os
import re
import shutil
import threading
import time
from datetime import datetime

import cv2

# Базовая папка для всех фото. В Docker это смонтированный том.
BASE_DIR = os.path.realpath(os.environ.get('PHOTOS_DIR', '/photos'))
# Ниже этого порога свободного места съемка не выполняется.
MIN_FREE_MB = int(os.environ.get('PHOTOS_MIN_FREE_MB', '200'))
JPEG_QUALITY = int(os.environ.get('PHOTOS_JPEG_QUALITY', '95'))
# Владелец создаваемых файлов на хосте (необязательно).
_UID = os.environ.get('PHOTOS_UID')
_GID = os.environ.get('PHOTOS_GID')
# Подряд столько ошибок снимка останавливают съемку по расписанию.
MAX_CONSECUTIVE_ERRORS = 5

_SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.timelapse.json')
_SEGMENT_RE = re.compile(r'^[^\x00/\\:*?"<>|]{1,64}$')
_save_lock = threading.Lock()
_settings_lock = threading.Lock()


class PhotoError(Exception):
    """Ошибка с понятным пользователю текстом и HTTP-кодом."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _chown(path):
    if _UID is None:
        return
    try:
        os.chown(path, int(_UID), int(_GID if _GID is not None else _UID))
    except (OSError, ValueError):
        pass


def _makedirs(path):
    """Создает папку внутри BASE_DIR, выставляя владельца новым папкам."""
    if not os.path.isdir(BASE_DIR):
        os.makedirs(BASE_DIR, exist_ok=True)
        _chown(BASE_DIR)
    rel = os.path.relpath(path, BASE_DIR)
    if rel == '.':
        return
    cur = BASE_DIR
    for part in rel.split(os.sep):
        cur = os.path.join(cur, part)
        if not os.path.isdir(cur):
            os.mkdir(cur)
            _chown(cur)


def resolve_dir(sub, create=False):
    """Превращает имя подпапки в безопасный путь внутри BASE_DIR.

    Возвращает (абсолютный_путь, нормализованное_относительное_имя).
    Пустое имя означает сам BASE_DIR.
    """
    sub = (sub or '').strip().replace('\\', '/').strip('/')
    parts = [p for p in sub.split('/') if p] if sub else []
    if len(parts) > 3:
        raise PhotoError('Слишком глубокая вложенность папок (максимум 3 уровня)')
    for p in parts:
        if p != p.strip() or p.startswith('.') or not _SEGMENT_RE.match(p):
            raise PhotoError('Недопустимое имя папки: %r' % p)
    path = os.path.realpath(os.path.join(BASE_DIR, *parts))
    if os.path.commonpath([path, BASE_DIR]) != BASE_DIR:
        raise PhotoError('Папка вне разрешенного каталога')
    if create:
        _makedirs(path)
    return path, '/'.join(parts)


def make_dir(sub):
    """Создает подпапку внутри BASE_DIR. Возвращает нормализованное имя ('' это корень)."""
    _path, rel = resolve_dir(sub, create=True)
    return rel


def list_subdirs(sub=''):
    """Дочерние подпапки папки sub (только один уровень)."""
    directory, rel = resolve_dir(sub)
    if not os.path.isdir(directory):
        return []
    result = []
    with os.scandir(directory) as it:
        for e in it:
            if e.is_dir() and not e.name.startswith('.'):
                result.append(_join(rel, e.name))
    result.sort()
    return result


def free_mb():
    return shutil.disk_usage(BASE_DIR).free // (1024 * 1024)


def _check_disk():
    left = free_mb()
    if left < MIN_FREE_MB:
        raise PhotoError('Мало места на диске: %d МБ (порог %d МБ)' % (left, MIN_FREE_MB), 507)


def encode_jpeg(frame):
    ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise PhotoError('Не удалось закодировать кадр', 500)
    return buf.tobytes()


def save_jpeg(data, directory):
    """Атомарно сохраняет JPEG, имя YYYYmmdd_HHMMSS.jpg (при совпадении _1, _2...)."""
    with _save_lock:
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        name = stamp + '.jpg'
        n = 0
        while os.path.exists(os.path.join(directory, name)):
            n += 1
            name = '%s_%d.jpg' % (stamp, n)
        final = os.path.join(directory, name)
        tmp = os.path.join(directory, '.' + name + '.tmp')
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, final)
        _chown(final)
        return name


def _join(rel, name):
    return '/'.join(p for p in (rel, name) if p)


def _num(value, name, lo, hi):
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise PhotoError('Поле %s должно быть числом' % name)
    if v != v or v < lo or v > hi:
        raise PhotoError('Поле %s должно быть от %g до %g' % (name, lo, hi))
    return v


def list_folders(max_depth=2):
    """Подпапки BASE_DIR (до max_depth уровней) в виде 'a', 'a/b'."""
    result = []
    if not os.path.isdir(BASE_DIR):
        return result
    for root, dirs, _files in os.walk(BASE_DIR):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
        rel = os.path.relpath(root, BASE_DIR)
        depth = 0 if rel == '.' else rel.count(os.sep) + 1
        if depth >= max_depth:
            dirs[:] = []
        if rel != '.':
            result.append(rel.replace(os.sep, '/'))
    return result


def list_photos(sub='', limit=200):
    """Последние JPEG в папке, новые первыми."""
    directory, rel = resolve_dir(sub)
    if not os.path.isdir(directory):
        return []
    items = []
    with os.scandir(directory) as it:
        for e in it:
            if e.is_file() and e.name.lower().endswith('.jpg') and not e.name.startswith('.'):
                st = e.stat()
                items.append({'name': e.name, 'file': _join(rel, e.name),
                              'size': st.st_size, 'mtime': int(st.st_mtime)})
    items.sort(key=lambda x: (x['mtime'], x['name']), reverse=True)
    return items[:limit]


class PhotoService:
    def __init__(self, get_frame):
        self._get_frame = get_frame
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._state = {
            'running': False, 'dir': '', 'interval': 0, 'max_count': 0,
            'duration': 0, 'taken': 0, 'last_file': '', 'last_error': '',
            'stop_reason': '', 'started_at': '',
        }

    # ---- настройки (последние значения для формы и автовозобновление) ----

    def settings(self):
        try:
            with open(_SETTINGS_FILE, encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_settings(self, **upd):
        # Замок нужен: кнопка фото и поток съемки могут писать настройки одновременно.
        with _settings_lock:
            data = self.settings()
            data.update(upd)
            tmp = _SETTINGS_FILE + '.tmp'
            try:
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False)
                os.replace(tmp, _SETTINGS_FILE)
            except OSError:
                pass

    # ---- снимок по кнопке ----

    def snapshot(self, sub=''):
        directory, rel = resolve_dir(sub, create=True)
        _check_disk()
        frame = self._get_frame()
        if frame is None:
            raise PhotoError('Камера еще не отдала кадр', 503)
        data = encode_jpeg(frame)
        name = save_jpeg(data, directory)
        self._save_settings(dir=rel)
        return {'file': _join(rel, name), 'dir': rel, 'size': len(data)}

    # ---- съемка по расписанию ----

    def start(self, sub, interval, max_count=0, duration=0):
        interval = _num(interval, 'interval', 1, 86400)
        max_count = int(_num(max_count or 0, 'max_count', 0, 1000000))
        duration = _num(duration or 0, 'duration', 0, 30 * 86400)
        directory, rel = resolve_dir(sub, create=True)
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise PhotoError('Съемка уже идет', 409)
            self._stop = threading.Event()
            self._state.update({
                'running': True, 'dir': rel, 'interval': interval,
                'max_count': max_count, 'duration': duration, 'taken': 0,
                'last_file': '', 'last_error': '', 'stop_reason': '',
                'started_at': datetime.now().isoformat(timespec='seconds'),
            })
            self._thread = threading.Thread(
                target=self._run, daemon=True,
                args=(self._stop, directory, rel, interval, max_count, duration))
            self._thread.start()
        self._save_settings(dir=rel, interval=interval, max_count=max_count,
                            duration=duration, running=True)
        return self.status()

    def stop(self):
        with self._lock:
            thread, event = self._thread, self._stop
        event.set()
        if thread is not None:
            thread.join(timeout=5)
        return self.status()

    def status(self):
        with self._lock:
            s = dict(self._state)
        try:
            s['free_mb'] = free_mb()
        except OSError:
            s['free_mb'] = None
        return s

    def resume_if_needed(self):
        """Продолжает съемку после перезапуска, если она шла и включено TIMELAPSE_RESUME=1."""
        if os.environ.get('TIMELAPSE_RESUME') != '1':
            return
        s = self.settings()
        if not s.get('running'):
            return
        try:
            self.start(s.get('dir', ''), s.get('interval', 60),
                       s.get('max_count', 0), s.get('duration', 0))
        except PhotoError as e:
            print('timelapse resume failed:', e)

    def _run(self, stop, directory, rel, interval, max_count, duration):
        deadline = time.monotonic() + duration if duration else None
        next_t = time.monotonic()
        errors = 0
        reason = 'stopped'
        try:
            while not stop.is_set():
                if deadline is not None and time.monotonic() >= deadline:
                    reason = 'duration'
                    break
                try:
                    _check_disk()
                except PhotoError as e:
                    with self._lock:
                        self._state['last_error'] = str(e)
                    reason = 'disk'
                    break
                try:
                    frame = self._get_frame()
                    if frame is None:
                        raise PhotoError('Камера не отдала кадр', 503)
                    name = save_jpeg(encode_jpeg(frame), directory)
                    errors = 0
                    with self._lock:
                        self._state['taken'] += 1
                        self._state['last_file'] = _join(rel, name)
                        self._state['last_error'] = ''
                except Exception as e:  # любая ошибка снимка не должна убивать поток
                    errors += 1
                    with self._lock:
                        self._state['last_error'] = str(e)
                    if errors >= MAX_CONSECUTIVE_ERRORS:
                        reason = 'errors'
                        break
                with self._lock:
                    taken = self._state['taken']
                if max_count and taken >= max_count:
                    reason = 'count'
                    break
                next_t += interval
                now = time.monotonic()
                wait = next_t - now
                if wait < 0:  # отстали от графика: пропускаем пропущенные кадры
                    next_t = now
                    wait = 0
                if deadline is not None:
                    wait = min(wait, max(deadline - now, 0))
                if stop.wait(wait):
                    break
        finally:
            # Сначала файл, потом статус: когда status() покажет running=False,
            # настройки на диске уже согласованы.
            self._save_settings(running=False)
            with self._lock:
                self._state['running'] = False
                self._state['stop_reason'] = reason
