#!/usr/bin/env python3
# File name   : RPiservo.py
# Description : Multi-threaded Control Servos
# Author	  : Adeept
from __future__ import division
import time
from board import SCL, SDA
import busio
from adafruit_motor import servo
from adafruit_pca9685 import PCA9685
import threading
import json
import os
import atexit




# When the motor occupies pins 9-15 on the PCA9685, 
# the servo can only use pins 0-8.
i2c = busio.I2C(SCL, SDA)
# Create a simple PCA9685 class instance.
pwm_servo = PCA9685(i2c, address=0x5f) #default 0x40
pwm_servo.frequency = 50


init_pwm0 = 90
init_pwm1 = 90
init_pwm2 = 90
init_pwm3 = 90

init_pwm4 = 90
init_pwm5 = 90
init_pwm6 = 90
init_pwm7 = 90

servo_num = 8
i2c = None
pwm_servo = None

# ---------------------------------------------------------------------------
# Память о положении серв для плавного старта.
# У серв нет обратной связи: после обесточивания чип PCA9685 забывает углы.
# Поэтому последний угол, отправленный каждому каналу, хранится в файле.
# ---------------------------------------------------------------------------
STATE_FILE = os.environ.get('SERVO_STATE_FILE') or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '.servo_state.json')
STATE_SAVE_INTERVAL = 0.2   # сек: как часто писать файл, если углы менялись
START_MAX_SPEED = 40.0      # град/сек: предел скорости серв при плавном старте
START_STEP_TIME = 0.02      # сек: один шаг рампы = один период PWM 50 Гц
START_HOLD_TIME = 0.3       # сек: пауза после первого импульса

_state_lock = threading.Lock()
_state_dirty = False
_state_stop = threading.Event()


def _load_state():
    # Возвращает список из servo_num значений: угол 0..180 или None (неизвестно).
    # Любая ошибка (нет файла, битый JSON, неверная длина) дает список из None.
    unknown = [None] * servo_num
    try:
        with open(STATE_FILE, 'r') as f:
            data = json.load(f)
        angles = data.get('angles')
        if not isinstance(angles, list) or len(angles) != servo_num:
            return unknown
        result = []
        for a in angles:
            if isinstance(a, (int, float)) and not isinstance(a, bool) and 0 <= a <= 180:
                result.append(float(a))
            else:
                result.append(None)
        return result
    except Exception:
        return unknown


_last_cmd = _load_state()


def _write_state_file(angles):
    # Атомарная запись: временный файл, fsync, переименование, fsync каталога.
    tmp = STATE_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump({'angles': angles}, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE_FILE)
    try:
        dir_fd = os.open(os.path.dirname(STATE_FILE) or '.', os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass


def flush_state():
    # Сохраняет углы в файл, если они менялись с прошлого сохранения.
    global _state_dirty
    with _state_lock:
        if not _state_dirty:
            return
        snapshot = list(_last_cmd)
        _state_dirty = False
    try:
        _write_state_file(snapshot)
    except Exception as e:
        print('servo state save error:', e)
        with _state_lock:
            _state_dirty = True


def _remember_angle(ID, angle):
    # Запоминает последний угол канала. Изменения меньше 0.05 градуса игнорируются.
    global _state_dirty
    with _state_lock:
        old = _last_cmd[ID]
        if old is None or abs(old - angle) >= 0.05:
            _last_cmd[ID] = float(angle)
            _state_dirty = True


def _state_writer():
    while not _state_stop.wait(STATE_SAVE_INTERVAL):
        flush_state()


threading.Thread(target=_state_writer, name='servo-state-writer', daemon=True).start()
atexit.register(flush_state)


class ServoCtrl(threading.Thread):

    def __init__(self, *args, **kwargs):


        
        # global i2c,pwm_servo
        self.i2c = busio.I2C(SCL, SDA)
        # Create a simple PCA9685 class instance.
        self.pwm_servo = PCA9685(self.i2c, address=0x5f) #default 0x40

        self.pwm_servo.frequency = 50

        
        self.sc_direction = [1,1,1,1, 1,1,1,1]
        # # If motors are not used, 16 servos need to be controlled at the same time.
        # self.sc_direction = [1,1,1,1, 1,1,1,1, 1,1,1,1, 1,1,1,1] 
        self.initPos = [init_pwm0,init_pwm1,init_pwm2,init_pwm3,
                        init_pwm4,init_pwm5,init_pwm6,init_pwm7]
        self.goalPos = [90,90,90,90, 90,90,90,90]
        self.nowPos  = [90,90,90,90, 90,90,90,90]
        self.bufferPos  = [90.0,90.0,90.0,90.0, 90.0,90.0,90.0,90.0]
        self.lastPos = [90,90,90,90, 90,90,90,90]
        self.ingGoal = [90,90,90,90, 90,90,90,90]
        self.maxPos  = [180,180,180,180, 180,180,180,180]
        self.minPos  = [0,0,0,0, 0,0,0,0]
        self.scSpeed = [0,0,0,0, 0,0,0,0]
        self.ctrlRangeMax = 180
        self.ctrlRangeMin = 0
        self.angleRange = 180

        '''
        scMode: 'init' 'auto' 'certain' 'quick' 'wiggle'
        '''
        self.scMode = 'auto'
        self.scTime = 2.0
        self.scSteps = 30

        self.scDelay = 0.09
        self.scMoveTime = 0.09
        

        self.goalUpdate = 0
        self.wiggleID = 0
        self.wiggleDirection = 1

        super(ServoCtrl, self).__init__(*args, **kwargs)
        self.__flag = threading.Event()
        self.__flag.clear()


    def set_angle(self,ID, angle):
        servo_angle = servo.Servo(self.pwm_servo.channels[ID], min_pulse=500, max_pulse=2400,actuation_range=180)
        servo_angle.angle = angle
        _remember_angle(ID, angle)

  
    def pause(self):
        print('......................pause..........................')
        self.__flag.clear()


    def resume(self):
        print('resume')
        self.__flag.set()


    def moveInit(self):
        self.scMode = 'init'
        # 1. Откуда стартует каждая серва. Приоритет сверху вниз:
        #    а) регистры чипа: если чип не обесточивался, он продолжает выдавать
        #       последний импульс, и это истинное положение;
        #    б) файл .servo_state.json: последний угол, отправленный до выключения;
        #    в) ничего не известно: берем целевой угол (первый импульс будет
        #       рывком, избежать этого нельзя).
        startPos = []
        for i in range(0, servo_num):
            cur = self.readAngle(i)
            if cur is None:
                with _state_lock:
                    cur = _last_cmd[i]
            if cur is None:
                cur = float(self.initPos[i])
            startPos.append(float(cur))

        # 2. Удержание: первый импульс на каждый канал равен стартовому углу.
        #    Если серва реально стоит там, она не двигается.
        for i in range(0, servo_num):
            self.set_angle(i, startPos[i])
            self.nowPos[i] = int(round(startPos[i]))
            self.lastPos[i] = int(round(startPos[i]))
            self.bufferPos[i] = float(startPos[i])
            self.goalPos[i] = self.initPos[i]
        time.sleep(START_HOLD_TIME)

        # 3. Плавный переход к целевому углу: мягкий старт и мягкая остановка.
        #    Пиковая скорость 1.5 * far / duration не превышает START_MAX_SPEED.
        far = max(abs(startPos[i] - self.initPos[i]) for i in range(0, servo_num))
        if far >= 1:
            duration = max(self.scTime, 1.5 * far / START_MAX_SPEED)
            steps = max(self.scSteps, int(duration / START_STEP_TIME))
            for s in range(1, steps + 1):
                t = float(s) / steps
                k = t * t * (3.0 - 2.0 * t)
                for i in range(0, servo_num):
                    pos = startPos[i] + (self.initPos[i] - startPos[i]) * k
                    self.nowPos[i] = int(round(pos))
                    self.set_angle(i, pos)
                time.sleep(duration / steps)

        # 4. Финиш: точный целевой угол и согласованное внутреннее состояние.
        for i in range(0, servo_num):
            self.set_angle(i, float(self.initPos[i]))
            self.lastPos[i] = self.initPos[i]
            self.nowPos[i] = self.initPos[i]
            self.bufferPos[i] = float(self.initPos[i])
            self.goalPos[i] = self.initPos[i]
        self.pause()


    def initConfig(self, ID, initInput, moveTo):
        if initInput > self.minPos[ID] and initInput < self.maxPos[ID]:
            self.initPos[ID] = initInput
            if moveTo:
                self.moveToAngle(ID, self.initPos[ID])
        else:
            print('initPos Value Error.')


    def knownAngle(self, ID):
        # Лучшая оценка текущего угла канала ID, по порядку:
        # последний импульс этого процесса или сохраненный в файле,
        # затем регистры чипа, затем nowPos.
        with _state_lock:
            cur = _last_cmd[ID]
        if cur is None:
            cur = self.readAngle(ID)
        if cur is None:
            cur = float(self.nowPos[ID])
        return cur


    def moveToAngle(self, ID, angle):
        # плавно ведем один канал к углу от его текущего положения
        cur = self.knownAngle(ID)
        if abs(cur - angle) >= 1:
            for s in range(1, self.scSteps + 1):
                pos = cur + (angle - cur) * s / self.scSteps
                self.nowPos[ID] = int(round(pos))
                self.set_angle(ID, self.nowPos[ID])
                time.sleep(self.scTime / self.scSteps)
        else:
            self.set_angle(ID, int(angle))
        self.lastPos[ID] = int(angle)
        self.nowPos[ID] = int(angle)
        self.bufferPos[ID] = float(angle)
        self.goalPos[ID] = int(angle)
        self.pause()


    def moveServoInit(self, ID):
        self.scMode = 'init'
        for i in range(0,len(ID)):
            self.set_angle(ID[i], self.initPos[ID[i]])
            self.lastPos[ID[i]] = self.initPos[ID[i]]
            self.nowPos[ID[i]] = self.initPos[ID[i]]
            self.bufferPos[ID[i]] = float(self.initPos[ID[i]])
            self.goalPos[ID[i]] = self.initPos[ID[i]]
        self.pause()


    def posUpdate(self):
        self.goalUpdate = 1
        for i in range(0,servo_num):
            self.lastPos[i] = self.nowPos[i]
        self.goalUpdate = 0

    def returnServoAngle(self, ID):
        return self.nowPos[ID]


    def speedUpdate(self, IDinput, speedInput):
        for i in range(0,len(IDinput)):
            self.scSpeed[IDinput[i]] = speedInput[i]


    def moveAuto(self):
        for i in range(0,servo_num):
            self.ingGoal[i] = self.goalPos[i]

        for i in range(0, self.scSteps):
            for dc in range(0,servo_num):
                if not self.goalUpdate:
                    self.nowPos[dc] = int(round((self.lastPos[dc] + (((self.goalPos[dc] - self.lastPos[dc])/self.scSteps)*(i+1))),0))
                    self.set_angle(dc, self.nowPos[dc])

                if self.ingGoal != self.goalPos:
                    self.posUpdate()
                    time.sleep(self.scTime/self.scSteps)
                    return 1
            time.sleep((self.scTime/self.scSteps - self.scMoveTime))

        self.posUpdate()
        self.pause()
        return 0


    def moveCert(self):
        for i in range(0,servo_num):
            self.ingGoal[i] = self.goalPos[i]
            self.bufferPos[i] = self.lastPos[i]

        while self.nowPos != self.goalPos:
            for i in range(0,servo_num):
                if self.lastPos[i] < self.goalPos[i]:
                    self.bufferPos[i] += self.pwmGenOut(self.scSpeed[i])/(1/self.scDelay)
                    newNow = int(round(self.bufferPos[i], 0))
                    if newNow > self.goalPos[i]:newNow = self.goalPos[i]
                    self.nowPos[i] = newNow
                elif self.lastPos[i] > self.goalPos[i]:
                    self.bufferPos[i] -= self.pwmGenOut(self.scSpeed[i])/(1/self.scDelay)
                    newNow = int(round(self.bufferPos[i], 0))
                    if newNow < self.goalPos[i]:newNow = self.goalPos[i]
                    self.nowPos[i] = newNow

                if not self.goalUpdate:
                    self.set_angle(i, self.nowPos[i])

                if self.ingGoal != self.goalPos:
                    self.posUpdate()
                    return 1
            self.posUpdate()
            time.sleep(self.scDelay-self.scMoveTime)

        else:
            self.pause()
            return 0


    def pwmGenOut(self, angleInput):
        return int(round(((self.ctrlRangeMax-self.ctrlRangeMin)/self.angleRange*angleInput),0))


    def setAutoTime(self, autoSpeedSet):
        self.scTime = autoSpeedSet


    def setDelay(self, delaySet):
        self.scDelay = delaySet


    def autoSpeed(self, ID, angleInput):
        self.scMode = 'auto'
        self.goalUpdate = 1
        for i in range(0,len(ID)):
            newGoal = self.initPos[ID[i]] + self.pwmGenOut(angleInput[i])*self.sc_direction[ID[i]]
            if newGoal>self.maxPos[ID[i]]:newGoal=self.maxPos[ID[i]]
            elif newGoal<self.minPos[ID[i]]:newGoal=self.minPos[ID[i]]
            self.goalPos[ID[i]] = newGoal
        self.goalUpdate = 0
        self.resume()


    def certSpeed(self, ID, angleInput, speedSet):
        self.scMode = 'certain'
        self.goalUpdate = 1
        for i in range(0,len(ID)):
            newGoal = self.initPos[ID[i]] + self.pwmGenOut(angleInput[i])*self.sc_direction[ID[i]]
            if newGoal>self.maxPos[ID[i]]:newGoal=self.maxPos[ID[i]]
            elif newGoal<self.minPos[ID[i]]:newGoal=self.minPos[ID[i]]
            self.goalPos[ID[i]] = newGoal
        self.speedUpdate(ID, speedSet)
        self.goalUpdate = 0
        self.resume()


    def moveWiggle(self):
        self.bufferPos[self.wiggleID] += self.wiggleDirection*self.sc_direction[self.wiggleID]*self.pwmGenOut(self.scSpeed[self.wiggleID])/(1/self.scDelay)
        newNow = int(round(self.bufferPos[self.wiggleID], 0))
        if self.bufferPos[self.wiggleID] > self.maxPos[self.wiggleID]:self.bufferPos[self.wiggleID] = self.maxPos[self.wiggleID]
        elif self.bufferPos[self.wiggleID] < self.minPos[self.wiggleID]:self.bufferPos[self.wiggleID] = self.minPos[self.wiggleID]
        self.nowPos[self.wiggleID] = newNow
        self.lastPos[self.wiggleID] = newNow
        if self.bufferPos[self.wiggleID] < self.maxPos[self.wiggleID] and self.bufferPos[self.wiggleID] > self.minPos[self.wiggleID]:
            self.set_angle(self.wiggleID, self.nowPos[self.wiggleID])
        else:
            self.stopWiggle()
        time.sleep(self.scDelay-self.scMoveTime)


    def stopWiggle(self):
        self.pause()
        self.posUpdate()


    def singleServo(self, ID, direcInput, speedSet):
        self.wiggleID = ID
        self.wiggleDirection = direcInput
        self.scSpeed[ID] = speedSet
        self.scMode = 'wiggle'
        self.posUpdate()
        self.resume()


    def moveAngle(self, ID, angleInput):
        # print(angleInput)
        self.nowPos[ID] = int(self.initPos[ID] + self.sc_direction[ID]*self.pwmGenOut(angleInput))
        # print(self.nowPos[ID])
        if self.nowPos[ID] > self.maxPos[ID]:self.nowPos[ID] = self.maxPos[ID]
        elif self.nowPos[ID] < self.minPos[ID]:self.nowPos[ID] = self.minPos[ID]
        self.lastPos[ID] = self.nowPos[ID]
        # print(self.nowPos[ID])
        self.set_angle(ID, self.nowPos[ID])


    def scMove(self):
        if self.scMode == 'init':
            self.moveInit()
        elif self.scMode == 'auto':
            self.moveAuto()
        elif self.scMode == 'certain':
            self.moveCert()
        elif self.scMode == 'wiggle':
            self.moveWiggle()


    def setPWM(self, ID, PWM_input):
        self.lastPos[ID] = PWM_input
        self.nowPos[ID] = PWM_input
        self.bufferPos[ID] = float(PWM_input)
        self.goalPos[ID] = PWM_input
        self.set_angle(ID, PWM_input)
        self.pause()


    def readAngle(self, ID):
        # текущее положение канала лежит в регистрах PCA9685 OFF_L/OFF_H.
        # при рестарте контейнера чип держит последние позиции, и по ним
        # можно понять, откуда серва поедет, чтобы не дернуть ее рывком
        try:
            reg = 0x06 + 4 * ID + 2
            buf = bytearray(2)
            self.i2c.writeto_then_readfrom(0x5f, bytes([reg]), buf)
            ticks = ((buf[1] << 8) | buf[0]) & 0x0FFF
            if ticks == 0 or ticks >= 4095:
                return None
            pulse_us = ticks * 1000000.0 / (50 * 4096)
            angle = (pulse_us - 500) / (2400 - 500) * 180
            if angle < 0 or angle > 180:
                return None
            return angle
        except Exception as e:
            print('readAngle error:', e)
            return None


    def run(self):
        while 1:
            self.__flag.wait()
            self.scMove()
            pass


if __name__ == '__main__':
    
    scGear = ServoCtrl()
    scGear.moveInit()
    # scGear.start()
    sc = ServoCtrl()
    # sc.setup()
    sc.start()
    
   

