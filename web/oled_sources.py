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
    # Мерит дальномер, который смотрит вперед вместе с камерой. Серву не
    # крутим: скан ей только мешает и ломает вид с камеры. Точка одна,
    # по центру экрана.
    PERIOD = 0.5

    def stop(self):
        super().stop()

    def run(self):
        global _radar_points, _radar_updated
        while not self._stop.is_set():
            with _radar_lock:
                _radar_points = [(0, read_distance())]
                _radar_updated = time.time()
            self._stop.wait(self.PERIOD)


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
