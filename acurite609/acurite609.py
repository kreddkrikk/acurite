#!/usr/bin/python3 -u

"""
Sniffs 433MHz RF signals from the AcuRite 00609SBLA2 outdoor unit.

The following example configures this module to listen for signals from a 
433MHz RF receiver's data pin on pin 23 and wait until a valid chunk of 1 or
more blocks is received or a 40-second timeout is reached:

from acurite609 import Acurite609

acurite609 = Acurite609(pin_data=23)
acurite609.start()

while True:
    if acurite609.available(timeout=40):
        humidity = acurite609.humidity
        temperature = acurite609.temperature
        print(f'{temperature:.1f}C {humidity}%')
    else:
        print(f'timeout')
"""

from datetime import datetime
import ctypes
import RPi.GPIO as GPIO
import signal
import socket
import struct
import sys
import threading
import time

CHUNK_READ_TIME = 1             # Time in seconds to read an RF signal chunk
SIGNAL_BIT_LENGTH = 40          # Length of block in bits
SIGNAL_INV = -2
SIGNAL_OFF = -1
SIGNAL_BIT_0 = 0
SIGNAL_BIT_1 = 1
SIGNAL_BLOCK_START = 2
SIGNAL_BLOCK_END = 3
SIGNAL_CHUNK_START = 4
SIGNAL_CHUNK_END = 5
CHANNEL_ID = 2
MULTICAST_ADDR = '224.3.29.70'  # For noise reports only
MULTICAST_PORT = 51000

class Acurite609:
    def __init__(self, pin_data, verbose=False, debug=False):
        self.libc = ctypes.CDLL('libc.so.6')
        self.notify_stop = False
        self.signature = -1
        self.battery = -1
        self.signal = 0
        self.age = 0
        self.updated = datetime.now()
        self.temperature = None
        self.humidity = None
        self.multicaster = None
        self.pin_data = pin_data
        self.print_verbose = print if verbose else lambda *a, **k: None
        self.print_debug = print if debug else lambda *a, **k: None
        self.condition = threading.Condition()
        self.plot = [[], []]
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin_data, GPIO.IN)
        def handler(s, f):
            self.stop()
            sys.exit(0)
        signal.signal(signal.SIGINT, handler)

    def enable_multicast(self):
        self.multicaster = socket.socket(
                socket.AF_INET, socket.SOCK_DGRAM)
        self.multicaster.setsockopt(
                socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 60)

    def get_rfs_type(self, rfs, duration):
        """Returns the type of RF signal received.

        :param int rfs: RF signal received; either 0 or 1
        :param int duration: signal duration, in microseconds
        :return: the signal type
        :rtype: int
        """
        if rfs == 0:
            if duration < 1200:
                return SIGNAL_OFF
        elif rfs == 1:
            if duration < 300:
                return SIGNAL_CHUNK_START
            elif duration >= 300 and duration < 1200:
                return SIGNAL_BIT_0
            elif duration >= 1200 and duration < 3000:
                return SIGNAL_BIT_1
            elif duration >= 3000 and duration < 9000:
                return SIGNAL_BLOCK_START
            elif duration >= 10000 and duration < 20000:
                return SIGNAL_BLOCK_END
            elif duration >= 20000 and duration < 40000:
                return SIGNAL_CHUNK_END
        return SIGNAL_INV

    def is_bit_signal(self, rfs_type):
        return rfs_type == SIGNAL_BIT_0 or rfs_type == SIGNAL_BIT_1

    def validate_checksum(self, block):
        checksum = block & 0xff
        calculated = (((block >> 8) & 0xff) + 
                ((block >> 16) & 0xff) +
                ((block >> 24) & 0xff) + 
                ((block >> 32))) & 0xff
        if checksum != calculated:
            self.print_verbose(
                    f'bad checksum: {calculated:#x} (expected {checksum:#x})')
        return checksum == calculated

    def validate_block(self, block):
        """Validates the signature and checksum of the specified block.

        :param int block: the block of data to validate
        :return: True if block is good, False if bad
        """
        self.print_verbose(f'[{block:040b}] ', end='')
        if block == 0:
            return False
        channel = (block >> 28) & 0x03
        if channel != CHANNEL_ID:
            self.print_verbose(
                    f'bad channel: {channel} (expected {CHANNEL_ID})')
            return False
        if not self.validate_checksum(block):
            return False
        signature = block >> 32
        if self.signature == -1:
            self.signature = signature
        elif self.signature != signature:
            self.print_verbose(f'bad signature: {signature:#x}')
            return False
        self.battery = (block >> 30) & 0x03
        self.print_verbose(
                f'signature={self.signature:x}, battery={self.battery}, ', end='')
        temp = (block >> 15) & 0x1fff
        if temp & 0x1000 == 0x1000:
            temp = -(0x2000 - temp)
        temp /= 20
        hum = (block >> 8) & 0x7f
        if hum >= 1 and hum <= 99 and temp >= -40 and temp <= 70:
            self.humidity = hum
            self.temperature = temp
            self.print_verbose(f'{temp:.1f}C {hum}%')
            return True
        else:
            self.print_verbose(f'invalid temperature {temp}F')
            return False

    def multicast_noise(self, data):
        """Sends RF noise signals over the multicast address/port.

        :param int data: number of pulses received in a single second
        """
        try:
            self.multicaster.sendto(data, (MULTICAST_ADDR, MULTICAST_PORT))
        except Exception as e:
            print(f'Noise multicast failed: {type(e)}: {e}')

    def parse_rf(self, channel):
        """Callback function that parses received RF signals.
        """
        count = 0
        elapsed = 0     # Seconds since initial RF signal received
        db = [[],[]]
        prev_rfs = -1
        start = birth = datetime.now()

        # Allow at least CHUNK_READ_TIME seconds to read all RF signals
        while elapsed < CHUNK_READ_TIME:
            rfs = GPIO.input(self.pin_data) ^ 1
            now = datetime.now()
            if prev_rfs >= 0 and rfs != prev_rfs:
                duration = (now - birth).microseconds
                db[0].append(duration)
                db[1].append(prev_rfs)
            if rfs != prev_rfs:
                birth = now
            elapsed = (now - start).seconds
            prev_rfs = rfs
            count += 1
            self.libc.usleep(1) # Avoids heavy CPU usage when high noise
        data = struct.pack('<I', count)
        if self.multicaster:
            self.multicast_noise(data)

        # Parse the signals and build each block
        chunk = []      # Will contain all blocks received in a single chunk
        block = 0       # Will contain all bits received in a single block
        block_size = 0  # Size in bits of current block
        last_rfs_type = SIGNAL_INV
        is_acurite = False
        block_open = False
        chunk_open = False
        for duration, rfs in zip(db[0], db[1]):
            rfs_type = SIGNAL_INV
            rfs_type = self.get_rfs_type(rfs, duration)
            self.print_debug(f'{rfs} {duration}')
            # Last signal must be SIGNAL_OFF
            if last_rfs_type == SIGNAL_OFF and not chunk_open:
                if rfs_type == SIGNAL_BLOCK_START:
                    chunk_open = True
                    block_open = True
                    is_acurite = True
                    block_size = 0
                    block = 0
            elif last_rfs_type == SIGNAL_OFF and chunk_open:
                if rfs_type == SIGNAL_BLOCK_START and not block_open:
                    if block_size == SIGNAL_BIT_LENGTH:
                        chunk.append(block)
                    block_open = True
                    block_size = 0
                    block = 0
                elif rfs_type == SIGNAL_BLOCK_END and block_open:
                    if block_size == SIGNAL_BIT_LENGTH:
                        chunk.append(block)
                    block_open = False
                    block_size = 0
                    block = 0
                elif rfs_type == SIGNAL_CHUNK_END:
                    last_rfs_type = rfs_type
                    if block_size == SIGNAL_BIT_LENGTH:
                        chunk.append(block)
                    block_open = False
                    chunk_open = False
                    block_size = 0
                    block = 0
                elif self.is_bit_signal(rfs_type) and block_open:
                    if rfs_type == SIGNAL_BIT_1 and block_size < SIGNAL_BIT_LENGTH:
                        block |= (1 << (SIGNAL_BIT_LENGTH - block_size - 1))
                    block_size += 1
            last_rfs_type = rfs_type

        # Now validate entire chunk
        now = datetime.now()
        self.signal = 0
        if is_acurite and len(chunk) > 0:
            if block_size == SIGNAL_BIT_LENGTH:
                chunk.append(block)
            self.print_verbose(f'[{now}] {{')
            for block in chunk:
                if self.validate_block(block):
                    self.signal += 1
            self.print_verbose('}')
            if self.signal > 6:
                self.signal = 6
            if self.signal > 0:
                self.updated = now

        # Notify other threads
        if self.signal > 0:
            with self.condition:
                self.condition.notify()

    def available(self, timeout=None):
        """Waits until an RF signal chunk with at least one valid block is
        received or the timeout has been reached.

        :param int timeout: timeout in seconds or None to wait indefinitely
        :return: True if successful, False on timeout
        :rtype: bool
        """
        with self.condition:
            result = self.condition.wait(timeout=timeout)
            if not result:
                now = datetime.now()
                self.print_verbose(f'[{now}] Acurite609: timeout')
                self.updated = now
                self.signal = 0
            return result

    def start(self):
        """Start listening for signals from the RF module.
        """
        self.begin = datetime.now()
        self.print_verbose('# started script')
        GPIO.add_event_detect(self.pin_data, GPIO.FALLING, self.parse_rf)

    def stop(self):
        """Stop listening for signals.
        """
        GPIO.remove_event_detect(self.pin_data)
        GPIO.cleanup()
