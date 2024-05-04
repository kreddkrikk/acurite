#!/usr/bin/python3 -u

"""
Sniffs 433MHz RF signals from the AcuRite 00523M refrigerator/freezer units.

The following example configures this module to listen for signals from a 
433MHz RF receiver's data pin on pin 17 and wait until a valid chunk of 1 or 
more blocks is received or a 70-second timeout is reached:

from acurite523 import Acurite523

acurite523 = Acurite523(pin_rx=17)
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

class Acurite523(Acurite):
    def __init__(self, pin_rx, verbose=False, debug=False):
        super().__init__(pin_rx, verbose, debug)
        self.freezer_signature = -1
        self.freezer_battery = -1
        self.freezer_signal = 0
        self.freezer_temp = None
        self.fridge_signature = -1
        self.fridge_battery = -1
        self.fridge_signal = 0
        self.fridge_temp = None

    def create_payload(self, signal_type):
        if signal_type == SIG_FREEZER:
            return struct.pack('<Hbbh', SIG_FREEZER, self.freezer_battery, 
                    self.freezer_signal, int(self.freezer_temp * 10))
        if signal_type == SIG_FRIDGE:
            return struct.pack('<Hbbh', SIG_FRIDGE, self.fridge_battery, 
                    self.fridge_signal, int(self.fridge_temp * 10))
        return None

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

    class ChunkBuilder:
        """Parsing and chunk-building for model-specific RF signals.
        """
        def __init__(self):
            self.chunk = []      # All blocks received in a single chunk
            self.block = 0       # All bits received in a single block
            self.block_size = 0  # Size in bits of current block
            self.last_rfs_type = SIGNAL_INV
            self.is_acurite = False
            self.block_open = False
            self.chunk_open = False
            self.block_opener_count = 0

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

        def parse_rf(self, duration, rfs):
            """Parse a single RF signal and update chunk/blocks.
            """
            rfs_type = SIGNAL_INV
            rfs_type = self.get_rfs_type(rfs, duration)
            #self.print_debug(f'{rfs} {duration}')
            if self.last_rfs_type == SIGNAL_BLOCK_OFF or not self.chunk_open:
                if rfs_type == SIGNAL_BLOCK_ON:
                    self.block_opener_count += 1
                if self.block_opener_count == 4:
                    self.block_opener_count = 0
                    if not self.chunk_open:
                        # Chunk start
                        self.chunk_open = True
                        self.block_open = True
                        self.is_acurite = True
                        self.block_size = 0
                        self.block = 0
                    # Block start
            elif self.last_rfs_type == SIGNAL_BIT_0_OFF and self.chunk_open:
                if rfs_type == SIGNAL_BIT_0_ON and self.block_size < SIGNAL_BIT_LENGTH:
                    self.block_size += 1
                elif rfs_type == SIGNAL_BIT_1_ON and self.block_size == SIGNAL_BIT_LENGTH:
                    # Block end
                    if self.block_size == SIGNAL_BIT_LENGTH:
                        self.chunk.append(self.block)
                    self.block_open = False
                    self.block_size = 0
                    self.block = 0
                elif rfs_type == SIGNAL_CHUNK_END:
                    # Chunk end
                    self.block_open = False
                    self.chunk_open = False
                    self.block_size = 0
                    self.block = 0
                self.block_opener_count = 0
            elif self.last_rfs_type == SIGNAL_BIT_1_OFF and self.chunk_open:
                if rfs_type == SIGNAL_BIT_1_ON and self.block_size < SIGNAL_BIT_LENGTH:
                    self.block |= (1 << (SIGNAL_BIT_LENGTH - self.block_size - 1))
                    self.block_size += 1
            elif rfs_type == SIGNAL_INV:
                self.block_opener_count = 0
                self.block_open = False
                self.chunk_open = False
                self.block_size = 0
                self.block = 0
            # Done
            self.last_rfs_type = rfs_type

    def validate_rf(self, builder):
        """Parses received RF signals.
        """
        # Now validate entire chunk
        now = datetime.now()
        freezer_signal = 0
        fridge_signal = 0
        chunk = builder.chunk
        if builder.is_acurite and len(chunk) > 0:
            if builder.block_size == SIGNAL_BIT_LENGTH:
                chunk.append(builder.block)
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
            if fridge_signal > 0:
                self.fridge_signal = fridge_signal
                if fridge_signal > 3:
                    fridge_signal = 3

        # Done
        if freezer_signal > 0:
            return SIG_FREEZER
        if fridge_signal > 0:
            return SIG_FRIDGE
        return 0
