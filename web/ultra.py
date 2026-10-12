#!/usr/bin/python3
# File name   : Ultrasonic.py
# Description : Detection distance and tracking with ultrasonic
# Website     : www.adeept.com
# Author      : Adeept
# Date        : 2024/03/10

from gpiozero import DistanceSensor
from time import sleep
import threading

Tr = 23
Ec = 24
sensor = DistanceSensor(echo=Ec, trigger=Tr,max_distance=2) # Maximum detection distance 2m.

# Замер один на весь робот: движение и экран радара ходят сюда из разных потоков
_dist_lock = threading.Lock()

def checkdist():
    with _dist_lock:
        return (sensor.distance) *100 # Unit: cm

if __name__ == "__main__":
    while True:
        distance = checkdist() 
        print("%.2f cm" %distance)
        sleep(0.05)
