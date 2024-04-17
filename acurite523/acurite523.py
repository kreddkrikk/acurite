#!/usr/bin/python3 -u

"""
Sniffs 433MHz RF signals from the AcuRite 00523M refrigerator/freezer units.

The following example configures this module to listen for signals from a 
433MHz RF receiver's data pin on pin 17 and wait until a valid chunk of 1 or 
more blocks is received or a 70-second timeout is reached:

from acurite523 import Acurite523

acurite523 = Acurite523(pin_data=17)
acurite523.start()

while True:
    if acurite523.available(timeout=70):
        freezer_temp = acurite523.freezer_temp
        fridge_temp = acurite523.fridge_temp
        if freezer_temp:
            # Do something
        if fridge_temp:
            # Do something
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
SIGNAL_BIT_LENGTH = 48          # Length of block in bits
SIGNAL_INV = -2
SIGNAL_BIT_0_OFF = 0
SIGNAL_BIT_0_ON = 1
SIGNAL_BIT_1_OFF = 2
SIGNAL_BIT_1_ON = 3
SIGNAL_BLOCK_OFF = 4
SIGNAL_BLOCK_ON = 5
SIGNAL_CHUNK_END = 6
CHANNEL_ID = 0                  # Not used here for now
SIG_FREEZER = 0xc049            # Signatures seem to be hardcoded?
SIG_FRIDGE = 0xc07c
MULTICAST_ADDR = '224.3.29.70'  # For noise reports only
MULTICAST_PORT = 51000

class Acurite523:
    def __init__(self, pin_data, verbose=False, debug=False):
        self.libc = ctypes.CDLL('libc.so.6')
        self.notify_stop = False
        self.updated = datetime.now()
        self.freezer_signature = -1
        self.freezer_battery = -1
        self.freezer_signal = 0
        self.freezer_temp = None
        self.fridge_signature = -1
        self.fridge_battery = -1
        self.fridge_signal = 0
        self.fridge_temp = None
        self.multicaster = None
        self.pin_data = pin_data
        self.print_verbose = print if verbose else lambda *a, **k: None
        self.print_debug = print if debug else lambda *a, **k: None
        self.condition = threading.Condition()
        def handler(s, f):
            sys.exit(0)
        signal.signal(signal.SIGINT, handler)
        self.plot = [[], []]
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin_data, GPIO.IN)

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
            if duration >= 100 and duration < 300:
                return SIGNAL_BIT_0_OFF
            elif duration >= 300 and duration < 500:
                return SIGNAL_BIT_1_OFF
            elif duration >= 500 and duration < 700:
                return SIGNAL_BLOCK_OFF
        elif rfs == 1:
            if duration >= 100 and duration < 300:
                return SIGNAL_BIT_1_ON
            elif duration >= 300 and duration < 500:
                return SIGNAL_BIT_0_ON
            elif duration >= 500 and duration < 700:
                return SIGNAL_BLOCK_ON
            elif duration >= 20000 and duration < 60000:
                return SIGNAL_CHUNK_END
        return SIGNAL_INV

    def is_bit_signal(self, rfs_type):
        return rfs_type == SIGNAL_BIT_0 or rfs_type == SIGNAL_BIT_1

    def validate_checksum(self, block):
        checksum = block & 0xff
        calculated = (((block >> 8) & 0xff) + 
                ((block >> 16) & 0xff) +
                ((block >> 24) & 0xff) + 
                ((block >> 32) & 0xff) + 
                ((block >> 40))) & 0xff
        if checksum != calculated:
            self.print_verbose(
                    f'bad checksum: {calculated:#x} (expected {checksum:#x})')
        return checksum == calculated

    def validate_block(self, block):
        """Validates the signature and checksum of the specified block.

        :param int block: the block of data to validate
        :return: True if block is good, False if bad
        """
        self.print_verbose(f'[{block:048b}] ', end='')
        if block == 0:
            return 0
        if not self.validate_checksum(block):
            return 0
        signature = block >> 32
        battery = (block >> 30) & 0x03
        temp = ((block >> 9) & 0x3f80) | ((block >> 8) & 0x7f)
        temp = (temp - 1800) / 18
        if temp < -40 and temp >= 70:
            self.print_verbose(f'invalid temperature {temp}F')
            return 0
        if signature == SIG_FREEZER:
            if self.freezer_signature == -1:
                self.freezer_signature = signature
            self.freezer_temp = temp
            self.freezer_battery = battery
            self.freezer_signal += 1
            self.print_verbose('freezer: ', end='')
        elif signature == SIG_FRIDGE:
            if self.fridge_signature == -1:
                self.fridge_signature = signature
            self.fridge_temp = temp
            self.fridge_battery = battery
            self.fridge_signal += 1
            self.print_verbose('fridge: ', end='')
        else:
            self.print_verbose(f'bad signature: {signature:#x}')
            return 0
        self.print_verbose(f'battery={battery}, {temp:.1f}C')
        return signature

    def multicast_noise(self, data):
        """Sends RF nosie signals over the multicast address/port.

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
                if duration >= 100:
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
        chunk = []      # All blocks received in a single chunk
        block = 0       # All bits received in a single block
        block_size = 0  # Size in bits of current block
        last_rfs_type = SIGNAL_INV
        is_acurite = False
        block_open = False
        chunk_open = False
        block_opener_count = 0
        for duration, rfs in zip(db[0], db[1]):
            rfs_type = SIGNAL_INV
            rfs_type = self.get_rfs_type(rfs, duration)
            self.print_debug(f'{rfs} {duration}')
            if last_rfs_type == SIGNAL_BLOCK_OFF or not chunk_open:
                if rfs_type == SIGNAL_BLOCK_ON:
                    block_opener_count += 1
                if block_opener_count == 4:
                    block_opener_count = 0
                    if not chunk_open:
                        # Chunk start
                        chunk_open = True
                        block_open = True
                        is_acurite = True
                        block_size = 0
                        block = 0
                    # Block start
            elif last_rfs_type == SIGNAL_BIT_0_OFF and chunk_open:
                if rfs_type == SIGNAL_BIT_0_ON and block_size < SIGNAL_BIT_LENGTH:
                    block_size += 1
                elif rfs_type == SIGNAL_BIT_1_ON and block_size == SIGNAL_BIT_LENGTH:
                    # Block end
                    if block_size == SIGNAL_BIT_LENGTH:
                        chunk.append(block)
                    block_open = False
                    block_size = 0
                    block = 0
                elif rfs_type == SIGNAL_CHUNK_END:
                    # Chunk end
                    block_open = False
                    chunk_open = False
                    block_size = 0
                    block = 0
                block_opener_count = 0
            elif last_rfs_type == SIGNAL_BIT_1_OFF and chunk_open:
                if rfs_type == SIGNAL_BIT_1_ON and block_size < SIGNAL_BIT_LENGTH:
                    block |= (1 << (SIGNAL_BIT_LENGTH - block_size - 1))
                    block_size += 1
            elif rfs_type == SIGNAL_INV:
                block_opener_count = 0
                block_open = False
                chunk_open = False
                block_size = 0
                block = 0
            last_rfs_type = rfs_type

        # Now validate entire chunk
        now = datetime.now()
        freezer_signal = 0
        fridge_signal = 0
        if is_acurite and len(chunk) > 0:
            if block_size == SIGNAL_BIT_LENGTH:
                chunk.append(block)
            self.print_verbose(f'[{now}] {{')
            for block in chunk:
                signature = self.validate_block(block)
                if signature == SIG_FREEZER:
                    freezer_signal += 1
                elif signature == SIG_FRIDGE:
                    fridge_signal += 1
            self.print_verbose('}')
            if freezer_signal > 0:
                self.freezer_signal = freezer_signal
                if freezer_signal > 3:
                    freezer_signal = 3
                self.updated = now
            if fridge_signal > 0:
                self.fridge_signal = fridge_signal
                if fridge_signal > 3:
                    fridge_signal = 3
                self.updated = now

        # Notify other threads
        if freezer_signal > 0 or fridge_signal > 0:
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
                self.print_verbose(f'[{now}] Acurite523: timeout')
                self.updated = now
                self.freezer_signal = 0
                self.fridge_signal = 0
            return result

    def start(self, condition=None):
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
