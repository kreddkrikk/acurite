#!/usr/bin/python3 -u

from datetime import datetime
import ctypes
import RPi.GPIO as GPIO
import signal
import socket
import struct
import sys
import threading
import time

MULTICAST_TAG_NOISE = 5391

class Acurite:
    def __init__(self, pin_rx, verbose=False, debug=False):
        self.multicaster = None
        self.multicast_noise_on = False
        self.pin_rx = pin_rx
        self.print_verbose = print if verbose else lambda *a, **k: None
        self.print_debug = print if debug else lambda *a, **k: None
        def handler(s, f):
            self.stop()
            sys.exit(0)
        signal.signal(signal.SIGINT, handler)

    def set_multicaster(self, multicaster, addr, port, noise=False):
        self.multicaster = multicaster
        self.multicast_addr = addr
        self.multicast_port = port
        self.multicast_noise_on = noise

    def multicast_noise(self, duration, rfs):
        """Sends RF noise signals over the multicast address/port.

        :param int data: number of pulses received in a single second
        """
        data = struct.pack('<HIb', MULTICAST_TAG_NOISE, duration, rfs)
        try:
            self.multicaster.sendto(
                    data, (self.multicast_addr, self.multicast_port))
        except Exception as e:
            print(f'Noise multicast failed: {type(e)}: {e}')

