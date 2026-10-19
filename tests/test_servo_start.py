"""Проверка плавного старта сервоприводов без железа (симуляция PCA9685).

Запуск из корня репозитория:
    python3 -m unittest discover -s tests -p "test_servo_start.py" -v
"""
import importlib
import json
import os
import sys
import tempfile
import types
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(REPO, 'web')


def angle_to_duty(angle, freq=50, min_pulse=500, max_pulse=2400, rng=180):
    # Та же формула, что в adafruit_motor.servo.
    min_duty = int((min_pulse * freq) / 1000000 * 0xFFFF)
    max_duty = (max_pulse * freq) / 1000000 * 0xFFFF
    duty_range = int(max_duty - min_duty)
    return int(min_duty + (angle / float(rng)) * duty_range)


def angle_to_ticks(angle):
    # adafruit_pca9685 пишет в регистр duty >> 4.
    return angle_to_duty(angle) >> 4


class FakeTime(object):
    def __init__(self):
        self.now = 0.0

    def sleep(self, seconds):
        self.now += seconds


class FakeChip(object):
    # Один PCA9685. off_ticks[i] is None: канал выключен (чип только что получил питание).
    def __init__(self):
        self.clock = FakeTime()
        self.off_ticks = [None] * 16
        self.writes = []

    def reset(self, warm_angles=None):
        self.off_ticks = [None] * 16
        self.writes = []
        for ch, angle in (warm_angles or {}).items():
            self.off_ticks[ch] = angle_to_ticks(angle)

    def channel_writes(self, ch):
        return [(t, a) for t, c, a in self.writes if c == ch]

    def first_write(self, ch):
        writes = self.channel_writes(ch)
        return writes[0][1] if writes else None


CHIP = FakeChip()


class FakeChannel(object):
    frequency = 50

    def __init__(self, index):
        self.index = index

    @property
    def duty_cycle(self):
        return 0

    @duty_cycle.setter
    def duty_cycle(self, value):
        CHIP.off_ticks[self.index] = value >> 4


class FakePCA9685(object):
    def __init__(self, i2c, address=0x40):
        self.channels = [FakeChannel(i) for i in range(16)]
        self.frequency = 50


class FakeI2C(object):
    def __init__(self, *args, **kwargs):
        pass

    def writeto_then_readfrom(self, address, buffer_out, buffer_in):
        ch = (buffer_out[0] - 0x06) // 4
        ticks = CHIP.off_ticks[ch]
        off = 0x1000 if ticks is None else ticks  # после подачи питания: бит FULL OFF
        buffer_in[0] = off & 0xFF
        buffer_in[1] = (off >> 8) & 0xFF


class FakeServo(object):
    def __init__(self, channel, min_pulse=750, max_pulse=2250, actuation_range=180):
        self.channel = channel
        self.rng = actuation_range

    @property
    def angle(self):
        return None

    @angle.setter
    def angle(self, value):
        if not 0 <= value <= self.rng:
            raise ValueError('angle out of range')
        CHIP.writes.append((CHIP.clock.now, self.channel.index, float(value)))
        self.channel.duty_cycle = angle_to_duty(value)


def install_fakes():
    board = types.ModuleType('board')
    board.SCL = 3
    board.SDA = 2
    busio = types.ModuleType('busio')
    busio.I2C = FakeI2C
    pca = types.ModuleType('adafruit_pca9685')
    pca.PCA9685 = FakePCA9685
    servo_mod = types.ModuleType('adafruit_motor.servo')
    servo_mod.Servo = FakeServo
    motor_pkg = types.ModuleType('adafruit_motor')
    motor_pkg.servo = servo_mod
    sys.modules.update({
        'board': board, 'busio': busio, 'adafruit_pca9685': pca,
        'adafruit_motor': motor_pkg, 'adafruit_motor.servo': servo_mod,
    })


class ServoTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmp, '.servo_state.json')
        self.modules = []
        install_fakes()
        if WEB not in sys.path:
            sys.path.insert(0, WEB)

    def tearDown(self):
        for m in self.modules:
            m._state_stop.set()

    def load(self, saved=None, warm=None, raw=None):
        # Импортирует RPIservo заново, как при старте процесса.
        # Чип после этого холодный, кроме каналов из warm.
        if raw is not None:
            with open(self.state_path, 'w') as f:
                f.write(raw)
        elif saved is not None:
            with open(self.state_path, 'w') as f:
                json.dump({'angles': saved}, f)
        os.environ['SERVO_STATE_FILE'] = self.state_path
        CHIP.reset(warm)
        sys.modules.pop('RPIservo', None)
        mod = importlib.import_module('RPIservo')
        mod.time = CHIP.clock
        CHIP.clock.now = 0.0
        self.modules.append(mod)
        return mod

    def test_cold_start_ramps_from_saved_angles(self):
        mod = self.load()
        init = mod.ServoCtrl().initPos
        saved = [min(180.0, init[0] + 45.0), float(init[1]), max(0.0, init[2] - 45.0)]
        saved += [None] + [float(x) for x in init[4:]]
        mod = self.load(saved=saved)
        sc = mod.ServoCtrl()
        sc.moveInit()
        # Первый импульс равен сохраненному углу (серва остается на месте).
        self.assertEqual(CHIP.first_write(0), saved[0])
        self.assertEqual(CHIP.first_write(2), saved[2])
        # Угол неизвестен: берется целевой.
        self.assertEqual(CHIP.first_write(3), float(init[3]))
        # Движение монотонно к цели и заканчивается точно в цели.
        for ch in (0, 2):
            angles = [a for t, a in CHIP.channel_writes(ch)]
            sign = 1 if init[ch] > saved[ch] else -1
            self.assertTrue(all(sign * (b - a) >= -1e-9 for a, b in zip(angles, angles[1:])))
            self.assertAlmostEqual(angles[-1], float(init[ch]))
            # Скорость не выше предела.
            writes = CHIP.channel_writes(ch)
            for (t1, a1), (t2, a2) in zip(writes, writes[1:]):
                if t2 > t1:
                    self.assertLessEqual(abs(a2 - a1) / (t2 - t1), mod.START_MAX_SPEED * 1.05)
        far = max(abs(saved[i] - init[i]) for i in (0, 2))
        expected = mod.START_HOLD_TIME + max(sc.scTime, 1.5 * far / mod.START_MAX_SPEED)
        self.assertGreaterEqual(CHIP.clock.now, expected - 1e-6)

    def test_cold_start_without_file_jumps_to_target(self):
        # Положение неизвестно: рывок неизбежен, но нет ни рампы, ни падений.
        mod = self.load()
        sc = mod.ServoCtrl()
        sc.moveInit()
        for ch in range(8):
            self.assertEqual(CHIP.first_write(ch), float(sc.initPos[ch]))
            self.assertTrue(all(a == float(sc.initPos[ch]) for t, a in CHIP.channel_writes(ch)))
        mod.flush_state()
        with open(self.state_path) as f:
            self.assertEqual(json.load(f)['angles'], [float(x) for x in sc.initPos])

    def test_warm_start_prefers_chip_registers_over_file(self):
        saved = [90.0, 120.0, 90.0, 90.0, 90.0, 90.0, 90.0, 90.0]
        mod = self.load(saved=saved, warm={1: 60.0})
        sc = mod.ServoCtrl()
        self.assertIsNone(sc.readAngle(0))
        self.assertAlmostEqual(sc.readAngle(1), 60.0, delta=1.0)
        sc.moveInit()
        self.assertAlmostEqual(CHIP.first_write(1), 60.0, delta=1.0)

    def test_saved_angles_survive_power_cycle(self):
        mod = self.load()
        sc = mod.ServoCtrl()
        sc.moveInit()
        sc.set_angle(0, 33.0)
        mod.flush_state()
        self.assertFalse(os.path.exists(self.state_path + '.tmp'))
        mod2 = self.load()  # новый процесс, чип без питания
        self.assertEqual(mod2._last_cmd[0], 33.0)
        mod2.ServoCtrl().moveInit()
        self.assertEqual(CHIP.first_write(0), 33.0)

    def test_broken_state_file_is_ignored(self):
        for raw in ['{"angles": [1,2', '[]', '{"angles": [1,2,3]}', 'not json', '{"angles": "x"}']:
            mod = self.load(raw=raw)
            self.assertEqual(mod._last_cmd, [None] * 8, raw)
        mod = self.load(raw=json.dumps({'angles': [500, -5, 'a', None, True, 90, 90.5, 0]}))
        self.assertEqual(mod._last_cmd, [None, None, None, None, None, 90.0, 90.5, 0.0])

    def test_file_is_written_only_when_angles_change(self):
        mod = self.load()
        mod._state_stop.set()  # без фонового потока, чтобы счет был точным
        calls = []
        real = mod._write_state_file

        def counting(angles):
            calls.append(list(angles))
            real(angles)

        mod._write_state_file = counting
        sc = mod.ServoCtrl()
        sc.set_angle(0, 50.0)
        mod.flush_state()
        self.assertEqual(len(calls), 1)
        mod.flush_state()
        self.assertEqual(len(calls), 1)
        sc.set_angle(0, 50.0)
        mod.flush_state()
        self.assertEqual(len(calls), 1)
        sc.set_angle(0, 50.01)
        mod.flush_state()
        self.assertEqual(len(calls), 1)
        sc.set_angle(0, 51.0)
        mod.flush_state()
        self.assertEqual(len(calls), 2)

    def test_second_moveinit_does_not_move_servos(self):
        # В проекте moveInit вызывается дважды (camera_opencv.py и WebServer.py).
        mod = self.load()
        init = mod.ServoCtrl().initPos
        saved = [min(180.0, init[0] + 45.0)] + [float(x) for x in init[1:]]
        mod = self.load(saved=saved)
        mod.ServoCtrl().moveInit()
        CHIP.writes[:] = []
        start = CHIP.clock.now
        sc = mod.ServoCtrl()
        sc.moveInit()
        for t, ch, a in CHIP.writes:
            self.assertAlmostEqual(a, float(init[ch]), delta=1.0)
        self.assertLess(CHIP.clock.now - start, 1.0)

    def test_moveToAngle_starts_from_known_angle(self):
        mod = self.load(saved=[135.0, 90.0, 90.0, 90.0, 90.0, 90.0, 90.0, 90.0])
        sc = mod.ServoCtrl()
        sc.moveToAngle(0, 90)
        first = CHIP.first_write(0)
        self.assertGreater(first, 130.0)
        self.assertLess(first, 135.0)


if __name__ == '__main__':
    unittest.main()
