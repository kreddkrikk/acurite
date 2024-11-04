#!/usr/bin/python3 -u

"""
Parses 433MHz RF signals from the AcuRite 00609SBLA2 outdoor unit.
"""

import struct

SIGNAL_BIT_LENGTH = 40          # Length of bitstream in bits
SIGNAL_INV = -2
SIGNAL_OFF = -1
SIGNAL_BIT_0 = 0
SIGNAL_BIT_1 = 1
SIGNAL_BITSTREAM_START = 2
SIGNAL_BITSTREAM_END = 3
SIGNAL_CHUNK_START = 4
SIGNAL_CHUNK_END = 5
CHANNEL_ID = 2
MODEL_ACURITE523 = 1592
MODEL_ACURITE609 = 6585
TAG_TEMPMONITOR = 0x38073162

class Acurite609():
    class Model():
        """Parsing and chunk-building for model-specific RF signals.
        """
        def __init__(self, devices):
            self.devices = devices
            self.bitstream = 0       # Will contain all bits received in a single bitstream
            self.bitstream_size = 0  # Size in bits of current bitstream
            self.last_rfs_type = SIGNAL_INV
            self.bitstream_open = False
            self.chunk_open = False

        def clear(self):
            self.bitstream = 0
            self.bitstream_size = 0
            self.last_rfs_type = SIGNAL_INV
            self.bitstream_open = False
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
                elif duration >= 8700 and duration < 9000:
                    return SIGNAL_BITSTREAM_START
                elif duration >= 10000 and duration < 20000:
                    return SIGNAL_BITSTREAM_END
                elif duration >= 20000 and duration < 40000:
                    return SIGNAL_CHUNK_END
            return SIGNAL_INV

        def is_bit_signal(self, rfs_type):
            return rfs_type == SIGNAL_BIT_0 or rfs_type == SIGNAL_BIT_1

        def open_bitstream(self):
            self.bitstream_open = True
            self.bitstream_size = 0
            self.bitstream = 0

        def close_bitstream(self):
            self.bitstream_open = False
            self.bitstream_size = 0
            self.bitstream = 0

        def open_chunk(self):
            self.chunk_open = True
            self.open_bitstream()

        def close_chunk(self):
            self.chunk_open = False
            self.close_bitstream()

        def parse_rf(self, duration, rfs):
            """Parse a single RF signal and update chunk/bitstreams.
            """
            result = 0
            rfs_type = SIGNAL_INV
            rfs_type = self.get_rfs_type(rfs, duration)
            # Last signal must be SIGNAL_OFF
            if self.last_rfs_type == SIGNAL_OFF and not self.chunk_open:
                if rfs_type == SIGNAL_BITSTREAM_START:
                    self.open_chunk()
            elif self.last_rfs_type == SIGNAL_OFF and self.chunk_open:
                if rfs_type == SIGNAL_BITSTREAM_START and not self.bitstream_open:
                    if self.bitstream_size == SIGNAL_BIT_LENGTH:
                        result = self.bitstream
                    self.open_bitstream()
                elif rfs_type == SIGNAL_BITSTREAM_END and self.bitstream_open:
                    if self.bitstream_size == SIGNAL_BIT_LENGTH:
                        result = self.bitstream
                    self.close_bitstream()
                elif rfs_type == SIGNAL_CHUNK_END:
                    self.last_rfs_type = rfs_type
                    if self.bitstream_size == SIGNAL_BIT_LENGTH:
                        result = self.bitstream
                    self.close_chunk()
                elif self.is_bit_signal(rfs_type) and self.bitstream_open:
                    if rfs_type == SIGNAL_BIT_1 and self.bitstream_size < SIGNAL_BIT_LENGTH:
                        self.bitstream |= (1 << (SIGNAL_BIT_LENGTH - self.bitstream_size - 1))
                    self.bitstream_size += 1
                    if self.bitstream_size == SIGNAL_BIT_LENGTH:
                        result = self.bitstream
                        self.close_bitstream()
            self.last_rfs_type = rfs_type
            # Done
            return result

    class Device():
        def __init__(self, device, verbosity=0):
            self.print_verbose = print if verbosity > 1 else lambda *a, **k: None
            self.print_debug = print if verbosity > 2 else lambda *a, **k: None
            self.device = device
            self.temperature = 0
            self.humidity = 0
            self.battery = 0
            self.signature = 0

        def create_payload(self, status):
            return struct.pack('<IHHbbhh', TAG_TEMPMONITOR, 
                    MODEL_ACURITE609, self.device, status, self.battery, 
                    int(self.temperature * 10), int(self.humidity * 10))

        def validate_checksum(self, bitstream):
            checksum = bitstream & 0xff
            calculated = (((bitstream >> 8) & 0xff) + 
                    ((bitstream >> 16) & 0xff) +
                    ((bitstream >> 24) & 0xff) + 
                    ((bitstream >> 32))) & 0xff
            if checksum != calculated:
                self.print_verbose(f'bad checksum: {calculated:#x}', end='')
            return checksum == calculated

        def validate_bitstream(self, bitstream):
            """Validates the signature and checksum of the specified bitstream.

            :param int bitstream: the bitstream of data to validate
            :return: True if bitstream is good, False if bad
            """
            if bitstream == 0:
                return False
            self.print_verbose(f'[{bitstream:040b}] ', end='')
            sig = bitstream >> 32
            if self.signature != 0 and self.signature != sig:
                self.print_verbose(f'bad signature: {sig:#x}')
                return False
            cha = (bitstream >> 28) & 0x03
            if cha != CHANNEL_ID:
                self.print_verbose(f'bad channel: {cha}')
                return False
            if not self.validate_checksum(bitstream):
                self.print_verbose(f', signature: {sig:#x}')
                return False
            bat= (bitstream >> 30) & 0x03
            temp = (bitstream >> 15) & 0x1fff
            if temp & 0x1000 == 0x1000:
                temp = -(0x2000 - temp)
            temp /= 20
            hum = (bitstream >> 8) & 0x7f
            if hum < 1 or hum > 99 or temp < -40 or temp > 70:
                self.print_verbose(f'invalid data: {temp}C {hum}%')
                return False
            # Set the instance values
            if self.signature == 0:
                self.signature = sig
            self.battery = bat
            self.humidity = hum
            self.temperature = temp
            temp = temp * 1.8 + 32
            self.print_verbose(f'outdoor: {temp:.1f}F {hum}%, battery={bat}')
            return True

