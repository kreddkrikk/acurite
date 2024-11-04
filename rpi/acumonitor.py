#!/usr/bin/python3 -u

from acurite523 import Acurite523
from acurite609 import Acurite609
from datetime import datetime
from queue import Queue
import struct
import threading
import time

"""
Sniffs 433MHz RF signals from supported Acurite models.
"""

STATUS_UNKNOWN      = 0
STATUS_OK           = 1
DEVICE_FREEZER   = 9690
DEVICE_FRIDGE    = 7784
DEVICE_OUTDOOR   = 8501

class Acumonitor:
    def __init__(self, pin_rx, verbosity=0):
        self.updated = datetime.now()
        self.pin_rx = pin_rx
        self.waiters = []
        self.print_verbose = print if verbosity > 1 else lambda *a, **k: None
        self.print_debug = print if verbosity > 2 else lambda *a, **k: None

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pin_rx, GPIO.IN)

        # Create devices for each model
        acurite523 = [
                Acurite523.Device(DEVICE_FREEZER, verbosity),
                Acurite523.Device(DEVICE_FRIDGE, verbosity)]
        acurite609 = [
                Acurite609.Device(DEVICE_OUTDOOR, verbosity)]

        # Create models
        self.models = [
                Acurite523.Model(acurite523),
                Acurite609.Model(acurite609)]

    def update_stats(self, device):
        payload = device.create_payload(STATUS_OK)

        # Notify other threads
        for waiter in self.waiters:
            waiter.put(payload)

    def parse_rf(self, duration, rfs):
        # Parse model-specific RF pulses
        for model in self.models:
            if result := model.parse_rf(duration, rfs):
                # Got valid signal for model, parse each device
                for device in model.devices:
                    if device.validate_bitstream(result):
                        self.update_stats(device)
                        return True
        # No valid signals found
        return False
    
    def reset_rf(self):
        for model in self.models:
            model.clear()

    def read_rf(self):
        """Callback function that reads a continous stream of RF pulses until
        valid data is received. Performs analog to digital conversion via the 
        model-specific parsing function. The parsing function attempts to 
        filter out any noise and build a valid chunk of binary data comprising 
        the temperature, humidity, etc.
        """
        prev_rfs = -1
        start = datetime.now()
        self.reset_rf()

        while True:
            rfs = GPIO.input(self.pin_rx) ^ 1
            now = datetime.now()
            if prev_rfs >= 0 and rfs != prev_rfs:
                duration = (now - start).microseconds
                if duration >= 100:
                    self.print_debug(f'{rfs} {duration}')
                    if self.parse_rf(duration, prev_rfs):
                        self.reset_rf()
            if rfs != prev_rfs:
                start = now
            prev_rfs = rfs
            time.sleep(0.0001) # 100us

    def available(self, timeout=None):
        """Waits until an RF signal chunk with at least one valid bitstream is
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
            # No payload because timeout, so create one
            data = None
        self.waiters.remove(waiter)
        return data

    def start(self):
        """Start listening for signals from the RF module.
        """
        self.print_verbose('# started script')
        threading.Thread(target=self.read_rf, daemon=True).start()

    def stop(self):
        """Stop listening for signals.
        """
        GPIO.remove_event_detect(self.pin_rx)

