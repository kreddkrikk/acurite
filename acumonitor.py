#!/usr/bin/python3 -u

from acurite523 import Acurite523
from acurite609 import Acurite609
from datetime import datetime
from queue import Queue
import ctypes
import RPi.GPIO as GPIO
import signal
import socket
import struct
import sys
import threading
import time

CHUNK_READ_TIME = 1             # Time in seconds to read an RF signal chunk

class Acumonitor:
    def __init__(self, pin_rx, verbose=False, debug=False):
        self.updated = datetime.now()
        self.multicaster = None
        self.pin_rx = pin_rx
        self.waiters = []
        self.libc = ctypes.CDLL('libc.so.6')
        self.print_verbose = print if verbose else lambda *a, **k: None
        self.print_debug = print if debug else lambda *a, **k: None
        self.acurite523 = Acurite523(pin_rx, verbose, debug)
        self.acurite609 = Acurite609(pin_rx, verbose, debug)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin_rx, GPIO.IN)
        def handler(s, f):
            self.stop()
            sys.exit(0)
        signal.signal(signal.SIGINT, handler)

    def enable_multicast(self, addr, port, noise=False):
        self.multicast_addr = addr
        self.multicast_port = port
        self.multicaster = socket.socket(
                socket.AF_INET, socket.SOCK_DGRAM)
        self.multicaster.setsockopt(
                socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 60)
        self.acurite523.set_multicaster(
                self.multicaster, addr, port, noise)
        self.acurite609.set_multicaster(
                self.multicaster, addr, port, noise)

    def enable_server(self, port):
        threading.Thread(
                target=self.start_server, args=(port,), daemon=True).start()

    def start_server(self, port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind(('', port))
        sock.listen()
        while True:
            s, a = sock.accept()
            threading.Thread(target=self.accept_connection, args=(s, a), 
                    daemon=True).start()

    def accept_connection(self, sock, addr):
        print(f'Connected to {addr}')
        while True:
            data = self.available(timeout=70)
            if data:
                try:
                    sock.send(data)
                except Exception:
                    print(f'Disconnected from {addr}')
                    return

    def multicast_stats(self, data):
        try:
            self.multicaster.sendto(
                    data, (self.multicast_addr, self.multicast_port))
        except Exception as e:
            print(f'Stat multicast failed: {type(e)}: {e}')

    def update_stats(self, device, signal_type):
        data = device.create_payload(signal_type)
        if data and self.multicaster:
            self.multicast_stats(data)

        # Notify other threads
        for waiter in self.waiters:
            waiter.put(data)

    def read_rf(self, channel):
        """Callback function that reads a continous stream of RF pulses for 1 
        or more seconds while performing analog to digital conversion via the 
        model-specific parsing function. The parsing function attempts to 
        filter out any noise and build a valid chunk of binary data comprising 
        the temperature, humidity, etc.
        """
        count = 0
        elapsed = 0     # Seconds since initial RF signal received
        prev_rfs = -1
        start = birth = datetime.now()
        builder523 = self.acurite523.ChunkBuilder()
        builder609 = self.acurite609.ChunkBuilder()

        # Allow at least CHUNK_READ_TIME seconds to read all RF signals
        while elapsed < CHUNK_READ_TIME:
            rfs = GPIO.input(self.pin_rx) ^ 1
            now = datetime.now()
            if prev_rfs >= 0 and rfs != prev_rfs:
                duration = (now - birth).microseconds
                if duration >= 100:
                    if self.multicaster and self.multicast_noise_on:
                        self.multicast_noise(duration, prev_rfs)
                    # Parse model-specific RF pulses
                    builder523.parse_rf(duration, prev_rfs)
                    builder609.parse_rf(duration, prev_rfs)
            if rfs != prev_rfs:
                birth = now
            elapsed = (now - start).seconds
            prev_rfs = rfs
            count += 1
            self.libc.usleep(1) # Avoids heavy CPU usage when high noise

        # Now validate model-specific data
        if signal_type := self.acurite523.validate_rf(builder523):
            self.update_stats(self.acurite523, signal_type)
        if signal_type := self.acurite609.validate_rf(builder609):
            self.update_stats(self.acurite609, signal_type)

    def available(self, timeout=None):
        """Waits until an RF signal chunk with at least one valid block is
        received or the timeout has been reached.

        :param int timeout: timeout in seconds or None to wait indefinitely
        :return: True if successful, False on timeout
        :rtype: bool
        """
        data = None
        waiter = Queue()
        self.waiters.append(waiter)
        try:
            data = waiter.get(block=True, timeout=timeout)
        except Exception:
            data = None
        self.waiters.remove(waiter)
        return data

    def start(self):
        """Start listening for signals from the RF module.
        """
        self.begin = datetime.now()
        self.print_verbose('# started script')
        GPIO.add_event_detect(self.pin_rx, GPIO.FALLING, self.read_rf)

    def stop(self):
        """Stop listening for signals.
        """
        GPIO.remove_event_detect(self.pin_rx)
        GPIO.cleanup()

