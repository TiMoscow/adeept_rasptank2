#!/usr/bin/env python
from importlib import import_module
import os
from flask import Flask, render_template, Response, send_from_directory, request
from flask_cors import *
# import camera driver
import camera_opencv
from camera_opencv import Camera
import threading
from gpiozero import TonalBuzzer
from time import sleep

# Raspberry Pi camera module (requires picamera package)
# from camera_pi import Camera

app = Flask(__name__)
CORS(app, supports_credentials=True)
camera = Camera()

# Buzzer on GPIO18
_buzzer = TonalBuzzer(18)
_buzzer_lock = threading.Lock()
_buzzer_stop_event = threading.Event()

def _play_notes(notes):
    _buzzer_stop_event.clear()
    with _buzzer_lock:
        for note, dur in notes:
            if _buzzer_stop_event.is_set():
                break
            if note:
                _buzzer.play(note)
            sleep(dur)
            _buzzer.stop()
            sleep(0.05)

@app.route('/api/buzzer/beep')
def buzzer_beep():
    threading.Thread(target=_play_notes, args=([("C5", 0.3)],), daemon=True).start()
    return "beep"

@app.route('/api/buzzer/song')
def buzzer_song():
    song = [
        ["G4", 0.3], ["G4", 0.3], ["A4", 0.3], ["G4", 0.3], ["C5", 0.3], ["B4", 0.6],
        ["G4", 0.3], ["G4", 0.3], ["A4", 0.3], ["G4", 0.3], ["D5", 0.3], ["C5", 0.6],
        ["G4", 0.3], ["G4", 0.3], ["C5", 0.3], ["B4", 0.3], ["C5", 0.3], ["B4", 0.3], ["A4", 0.6],
        ["F5", 0.3], ["F5", 0.3], ["B4", 0.3], ["C5", 0.3], ["D5", 0.3], ["C5", 0.6]
    ]
    threading.Thread(target=_play_notes, args=(song,), daemon=True).start()
    return "playing"

@app.route('/api/buzzer/stop')
def buzzer_stop():
    _buzzer_stop_event.set()
    _buzzer.stop()
    return "stopped"

@app.route('/api/camera/flip', methods=['GET', 'POST'])
def camera_flip():
    # GET - текущее состояние, POST - переключить переворот камеры на180
    if request.method == 'POST':
        camera_opencv.flip_set(not camera_opencv.flip180)
    return {"flip": int(camera_opencv.flip180)}

def gen(camera):
    """Video streaming generator function."""
    while True:
        frame = camera.get_frame()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/video_feed')
def video_feed():
    """Video streaming route. Put this in the src attribute of an img tag."""
    return Response(gen(camera),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

dir_path = os.path.dirname(os.path.realpath(__file__))

@app.route('/api/img/<path:filename>')
def sendimg(filename):
    return send_from_directory(dir_path+'/dist/img', filename)

@app.route('/js/<path:filename>')
def sendjs(filename):
    return send_from_directory(dir_path+'/dist/js', filename)

@app.route('/css/<path:filename>')
def sendcss(filename):
    return send_from_directory(dir_path+'/dist/css', filename)

@app.route('/api/img/icon/<path:filename>')
def sendicon(filename):
    return send_from_directory(dir_path+'/dist/img/icon', filename)

@app.route('/fonts/<path:filename>')
def sendfonts(filename):
    return send_from_directory(dir_path+'/dist/fonts', filename)

@app.route('/<path:filename>')
def sendgen(filename):
    return send_from_directory(dir_path+'/dist', filename)

@app.route('/')
def index():
    return send_from_directory(dir_path+'/dist', 'index.html')

class webapp:
    def __init__(self):
        self.camera = camera

    def modeselect(self, modeInput):
        Camera.modeSelect = modeInput

    def modeselectApp(self, modeInput):
        camera_opencv.APPMode = modeInput

    def colorFindSet(self, H, S, V):
        camera.colorFindSet(H, S, V)

    def colorFindSetApp(self, H, S, V):
        camera.colorFindSetApp(H, S, V)
        
    def thread(self):
        app.run(host='0.0.0.0', port=5000,threaded=True)

    def startthread(self):
        fps_threading=threading.Thread(target=self.thread)         #Define a thread for FPV and OpenCV
        # fps_threading.setDaemon(False)                             #'True' means it is a front thread,it would close when the mainloop() closes
        fps_threading.daemon = False
        fps_threading.start()                                     #Thread starts


if __name__ == "__main__":
    WEB = webapp()
    try:
        WEB.startthread()
    except:
        print("exit")