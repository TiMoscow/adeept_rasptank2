# Общие источники для экранов OLED: события, активность, дальномер, кадр камеры.
# Фоновые наблюдатели (препятствие, лицо, радар) дергают чужие модули, поэтому
# поднимаются только тогда, когда нужны активному экрану, а не крутятся всегда.

import threading
import time
import warnings

# Дальномер часто отвечает "no echo" (нечего эхоить), и gpiozero сыпет этим
# в лог каждые полсекунды. Нам важен замер, а не шум.
warnings.filterwarnings('ignore', message='no echo received')

# --- события и активность ---

_events = []
_activity = time.time()
_ev_lock = threading.Lock()


def push_event(kind):
    # kind: command | obstacle | person
    global _activity
    with _ev_lock:
        _events.append(kind)
        _activity = time.time()
        if len(_events) > 20:
            del _events[:-20]


def pop_event():
    with _ev_lock:
        return _events.pop(0) if _events else None


def clear_events():
    with _ev_lock:
        _events.clear()


def last_activity():
    with _ev_lock:
        return _activity


# --- покой робота и серва камеры ---
# WebServer отдает сюда серву камеры (канал 2) и проверку, что робот не занят
# своей функцией. Радар крутит серву только когда робот стоит.

_pan_servo = None
_idle_probe = None
IDLE_SEC = 1.5


def set_pan_servo(servo):
    global _pan_servo
    _pan_servo = servo


def set_idle_probe(fn):
    global _idle_probe
    _idle_probe = fn


def _robot_idle():
    if _idle_probe is not None:
        try:
            if not _idle_probe():
                return False
        except Exception:
            pass
    # команды из веба тоже считаем движением
    return (time.time() - last_activity()) > IDLE_SEC


# --- дальномер ---

def read_distance():
    # ultra.checkdist держит свой лок, тут только мягкая обработка ошибок
    try:
        import ultra
        return ultra.checkdist()
    except Exception:
        return None


# --- радар ---

_radar_points = []
_radar_updated = 0.0
_radar_lock = threading.Lock()


def radar_snapshot():
    # список пар (угол, см) и время последнего прохода
    with _radar_lock:
        return list(_radar_points), _radar_updated


# --- кадр камеры ---

def read_frame():
    try:
        import camera_opencv
        return camera_opencv.get_clean_frame()
    except Exception:
        return None


# --- фоновые наблюдатели ---

CASCADE_FACE = '/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml'


class _Worker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()
        self.join(timeout=1.0)


class ObstacleWatcher(_Worker):
    # Раз в 0.5 сек смотрит дальномер и сообщает о препятствии
    def __init__(self, threshold_cm):
        super().__init__()
        self.threshold_cm = threshold_cm
        self._last_hit = 0.0

    def run(self):
        while not self._stop.is_set():
            dist = read_distance()
            now = time.time()
            if dist is not None and 0 < dist < self.threshold_cm and now - self._last_hit > 3.0:
                self._last_hit = now
                push_event('obstacle')
            self._stop.wait(0.5)


class FaceWatcher(_Worker):
    # Раз в 1.5 сек ищет лицо в последнем кадре камеры
    def __init__(self):
        super().__init__()
        self._last_hit = 0.0

    def run(self):
        try:
            import cv2
            cascade = cv2.CascadeClassifier(CASCADE_FACE)
        except Exception:
            return
        if cascade.empty():
            return
        while not self._stop.is_set():
            frame = read_frame()
            now = time.time()
            if frame is not None:
                try:
                    import cv2
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    faces = cascade.detectMultiScale(gray, 1.2, 5, minSize=(40, 40))
                    if len(faces) and now - self._last_hit > 4.0:
                        self._last_hit = now
                        push_event('person')
                except Exception:
                    pass
            self._stop.wait(1.5)


class RadarScanner(_Worker):
    # Крутит серву камеры (канал 2), пока робот стоит, и мерит по углам.
    # В движении серву не трогаем, показываем последний замер вперед.
    ANGLES = [-60, -45, -30, -15, 0, 15, 30, 45, 60]

    def stop(self):
        super().stop()
        # вернуть серву в центр, чтобы камера не осталась повернутой
        if _pan_servo is not None:
            try:
                _pan_servo.moveAngle(2, 0)
            except Exception:
                pass

    def run(self):
        global _radar_points, _radar_updated
        while not self._stop.is_set():
            if _pan_servo is None or not _robot_idle():
                # робот занят: сервой не крутим, только замер вперед
                with _radar_lock:
                    _radar_points = [(0, read_distance())]
                    _radar_updated = time.time()
                self._stop.wait(0.5)
                continue
            pts = []
            for a in self.ANGLES:
                if self._stop.is_set():
                    break
                try:
                    _pan_servo.moveAngle(2, a)
                except Exception:
                    pass
                self._stop.wait(0.22)
                pts.append((a, read_distance()))
            try:
                _pan_servo.moveAngle(2, 0)
            except Exception:
                pass
            self._stop.wait(0.15)
            with _radar_lock:
                _radar_points = pts
                _radar_updated = time.time()
            self._stop.wait(0.5)


# --- менеджер наблюдателей: держит поднятыми только нужные ---

_watchers = {}
_w_lock = threading.Lock()


def ensure_watchers(mode, options):
    want = {}
    if mode == 'eyes':
        if options.get('react_obstacle'):
            want['obstacle'] = True
        if options.get('react_person'):
            want['person'] = True
    if mode == 'radar':
        want['radar'] = True

    with _w_lock:
        # гасим то, что больше не нужно
        for name in list(_watchers):
            if name not in want:
                _watchers.pop(name).stop()
        if 'obstacle' in want and 'obstacle' not in _watchers:
            w = ObstacleWatcher(options.get('obstacle_cm', 30))
            w.start()
            _watchers['obstacle'] = w
        if 'person' in want and 'person' not in _watchers:
            w = FaceWatcher()
            w.start()
            _watchers['person'] = w
        if 'radar' in want and 'radar' not in _watchers:
            w = RadarScanner()
            w.start()
            _watchers['radar'] = w
        # порог препятствия меняется на лету
        ob = _watchers.get('obstacle')
        if ob is not None:
            ob.threshold_cm = options.get('obstacle_cm', 30)


def stop_watchers():
    with _w_lock:
        for w in list(_watchers.values()):
            w.stop()
        _watchers.clear()
