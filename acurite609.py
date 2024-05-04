#!/usr/bin/python3 -u

"""
Sniffs 433MHz RF signals from the AcuRite 00609SBLA2 outdoor unit.

The following example configures this module to listen for signals from a 
433MHz RF receiver's data pin on pin 23 and wait until a valid chunk of 1 or
more blocks is received or a 40-second timeout is reached:

from acurite609 import Acurite609

acurite609 = Acurite609(pin_rx=23)
acurite609.start()

while True:
    if acurite609.available(timeout=40):
        humidity = acurite609.humidity
        temperature = acurite609.temperature
        print(f'{temperature:.1f}C {humidity}%')
    else:
        print(f'timeout')
"""

from acurite import Acurite
from datetime import datetime
import ctypes
import RPi.GPIO as GPIO
import signal
import socket
import struct
import sys
import threading
import time

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
MULTICAST_TAG = 0xc261

class Acurite609(Acurite):
    def __init__(self, pin_rx, verbose=False, debug=False):
        super().__init__(pin_rx, verbose, debug)
        self.signature = -1
        self.battery = -1
        self.signal = 0
        self.temperature = None
        self.humidity = None

    def create_payload(self, signal_type):
        return struct.pack('<Hbbhh', MULTICAST_TAG, 
                self.battery, self.signal, 
                int(self.temperature * 10), int(self.humidity * 10))

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

    class ChunkBuilder:
        """Parsing and chunk-building for model-specific RF signals.
        """
        def __init__(self):
            self.chunk = []      # Will contain all blocks received in a single chunk
            self.block = 0       # Will contain all bits received in a single block
            self.block_size = 0  # Size in bits of current block
            self.last_rfs_type = SIGNAL_INV
            self.is_acurite = False
            self.block_open = False
            self.chunk_open = False

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

        def parse_rf(self, duration, rfs):
            """Parse a single RF signal and update chunk/blocks.
            """
            rfs_type = SIGNAL_INV
            rfs_type = self.get_rfs_type(rfs, duration)
            #self.print_debug(f'{rfs} {duration}')
            # Last signal must be SIGNAL_OFF
            if self.last_rfs_type == SIGNAL_OFF and not self.chunk_open:
                if rfs_type == SIGNAL_BLOCK_START:
                    self.chunk_open = True
                    self.block_open = True
                    self.is_acurite = True
                    self.block_size = 0
                    self.block = 0
            elif self.last_rfs_type == SIGNAL_OFF and self.chunk_open:
                if rfs_type == SIGNAL_BLOCK_START and not self.block_open:
                    if self.block_size == SIGNAL_BIT_LENGTH:
                        self.chunk.append(self.block)
                    self.block_open = True
                    self.block_size = 0
                    self.block = 0
                elif rfs_type == SIGNAL_BLOCK_END and self.block_open:
                    if self.block_size == SIGNAL_BIT_LENGTH:
                        self.chunk.append(self.block)
                    self.block_open = False
                    self.block_size = 0
                    self.block = 0
                elif rfs_type == SIGNAL_CHUNK_END:
                    self.last_rfs_type = rfs_type
                    if self.block_size == SIGNAL_BIT_LENGTH:
                        self.chunk.append(self.block)
                    self.block_open = False
                    self.chunk_open = False
                    self.block_size = 0
                    self.block = 0
                elif self.is_bit_signal(rfs_type) and self.block_open:
                    if rfs_type == SIGNAL_BIT_1 and self.block_size < SIGNAL_BIT_LENGTH:
                        self.block |= (1 << (SIGNAL_BIT_LENGTH - self.block_size - 1))
                    self.block_size += 1
            # Done
            self.last_rfs_type = rfs_type

    def validate_rf(self, builder):
        """Parses received RF signals.
        """
        # Now validate entire chunk
        now = datetime.now()
        self.signal = 0
        chunk = builder.chunk
        if builder.is_acurite and len(chunk) > 0:
            if builder.block_size == SIGNAL_BIT_LENGTH:
                chunk.append(builder.block)
            self.print_verbose(f'[{now}] {{')
            for block in chunk:
                if self.validate_block(block):
                    self.signal += 1
            self.print_verbose('}')
            if self.signal > 6:
                self.signal = 6

        # Done
        if self.signal > 0:
            return MULTICAST_TAG
        return 0
