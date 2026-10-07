FROM debian:trixie-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# RPi-репозиторий для python3-lgpio (пакет только там)
RUN echo "deb [trusted=yes] http://archive.raspberrypi.com/debian trixie main" > /etc/apt/sources.list.d/raspi.list

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    build-essential \
    libjpeg-dev \
    zlib1g-dev \
    libopenblas-dev \
    liblapack-dev \
    gfortran \
    libhdf5-dev \
    libavcodec-dev \
    libavformat-dev \
    libswscale-dev \
    libv4l-dev \
    libxvidcore-dev \
    libx264-dev \
    libgtk-3-dev \
    pkg-config \
    libffi-dev \
    libxml2-dev \
    libssl-dev \
    cython3 \
    v4l-utils \
    python3-opencv \
    opencv-data \
    libcamera-dev \
    libcamera-tools \
    python3-gpiozero \
    python3-lgpio \
    python3-libcamera \
    python3-picamera2 \
    i2c-tools \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# lgpio ставится pip-зависимостью adafruit-blinka, но его версия конфликтует
# с gpiozero. После установки удаляем pip-версию, остается системная из RPi-репо.
RUN pip3 install --no-cache-dir --break-system-packages \
    adafruit-blinka \
    adafruit-circuitpython-motor \
    adafruit-circuitpython-pca9685 \
    adafruit-circuitpython-ads7830 \
    flask \
    flask_cors \
    numpy \
    pyzmq \
    imutils \
    pybase64 \
    psutil \
    websockets==13.0 \
    rpi_ws281x \
    smbus \
    pillow \
    RPi.GPIO \
    spidev && \
    pip3 uninstall -y --break-system-packages lgpio && \
    apt-get update && apt-get install -y --reinstall python3-lgpio && \
    python3 -c "import lgpio; assert 'dist-packages' in lgpio.__file__, lgpio.__file__"

COPY . /app/adeept_rasptank2

WORKDIR /app/adeept_rasptank2

CMD ["python3", "web/WebServer.py"]
