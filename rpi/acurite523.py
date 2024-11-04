#!/usr/bin/python3 -u

"""
Parses 433MHz RF signals from the AcuRite 00523M refrigerator/freezer units.
"""

import struct

SIGNAL_BIT_LENGTH = 48              # Length of bitstream in bits
SIGNAL_INV = -2
SIGNAL_BIT_0_OFF = 0
SIGNAL_BIT_0_ON = 1
SIGNAL_BIT_1_OFF = 2
SIGNAL_BIT_1_ON = 3
SIGNAL_BITSTREAM_OFF = 4
SIGNAL_BITSTREAM_ON = 5
SIGNAL_CHUNK_END = 6
ACURITE523_SIG_FREEZER = 0xc049  # Signatures seem to be hardcoded?
ACURITE523_SIG_FRIDGE = 0xc07c
MODEL_ACURITE523 = 1592
MODEL_ACURITE609 = 6585
DEVICE_FREEZER   = 9690
DEVICE_FRIDGE    = 7784
TAG_TEMPMONITOR = 0x38073162

class Acurite523():
    class Model():
        """Parsing and chunk-building for model-specific RF signals.
        """
        def __init__(self, devices):
            self.devices = devices
            self.bitstream = 0       # All bits received in a single bitstream
            self.bitstream_size = 0  # Size in bits of current bitstream
            self.last_rfs_type = SIGNAL_INV
            self.bitstream_open = False
            self.chunk_open = False
            self.bitstream_opener_count = 0

        def clear(self):
            self.bitstream = 0
            self.bitstream_size = 0
            self.last_rfs_type = SIGNAL_INV
            self.bitstream_open = False
            self.chunk_open = False
            self.bitstream_opener_count = 0

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
                    return SIGNAL_BITSTREAM_OFF
            elif rfs == 1:
                if duration >= 100 and duration < 300:
                    return SIGNAL_BIT_1_ON
                elif duration >= 300 and duration < 500:
                    return SIGNAL_BIT_0_ON
                elif duration >= 500 and duration < 700:
                    return SIGNAL_BITSTREAM_ON
                elif duration >= 20000 and duration < 60000:
                    return SIGNAL_CHUNK_END
            return SIGNAL_INV

        def is_bit_signal(self, rfs_type):
            return (
                    rfs_type == SIGNAL_BIT_0_OFF or 
                    rfs_type == SIGNAL_BIT_0_ON or 
                    rfs_type == SIGNAL_BIT_1_OFF or 
                    rfs_type == SIGNAL_BIT_1_ON)

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
            if self.last_rfs_type == SIGNAL_BITSTREAM_OFF or not self.chunk_open:
                if rfs_type == SIGNAL_BITSTREAM_ON:
                    self.bitstream_opener_count += 1
                if self.bitstream_opener_count == 4:
                    self.bitstream_opener_count = 0
                    if not self.chunk_open:
                        # Chunk start
                        self.open_chunk()
                    # Bitstream start
            elif self.last_rfs_type == SIGNAL_BIT_0_OFF and self.chunk_open:
                if rfs_type == SIGNAL_BIT_0_ON and self.bitstream_size < SIGNAL_BIT_LENGTH:
                    self.bitstream_size += 1
                    if self.bitstream_size == SIGNAL_BIT_LENGTH:
                        result = self.bitstream
                        self.close_bitstream()
                elif rfs_type == SIGNAL_BIT_1_ON and self.bitstream_size == SIGNAL_BIT_LENGTH:
                    # Bitstream end
                    result = self.bitstream
                    self.close_bitstream()
                elif rfs_type == SIGNAL_CHUNK_END:
                    # Chunk end
                    if self.bitstream_size == SIGNAL_BIT_LENGTH:
                        result = self.bitstream
                    self.close_chunk()
                self.bitstream_opener_count = 0
            elif self.last_rfs_type == SIGNAL_BIT_1_OFF and self.chunk_open:
                if rfs_type == SIGNAL_BIT_1_ON and self.bitstream_size < SIGNAL_BIT_LENGTH:
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
            self.temperature = None
            self.battery = -1
            if device == DEVICE_FREEZER:
                self.signature = ACURITE523_SIG_FREEZER
            elif device == DEVICE_FRIDGE:
                self.signature = ACURITE523_SIG_FRIDGE
            else:
                self.signature = 0

        def create_payload(self, status):
            return struct.pack('<IHHbbhh', TAG_TEMPMONITOR, 
                    MODEL_ACURITE523, self.device, status, self.battery, 
                    int(self.temperature * 10), 0)

        def validate_checksum(self, bitstream):
            checksum = bitstream & 0xff
            calculated = (((bitstream >> 8) & 0xff) + 
                    ((bitstream >> 16) & 0xff) +
                    ((bitstream >> 24) & 0xff) + 
                    ((bitstream >> 32) & 0xff) + 
                    ((bitstream >> 40))) & 0xff
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
            sig = bitstream >> 32
            if sig != self.signature:
                return False
            self.print_verbose(f'[{bitstream:048b}] ', end='')
            if not self.validate_checksum(bitstream):
                self.print_verbose(f', signature: {sig:#x}')
                return False
            bat = (bitstream >> 30) & 0x03
            temp = ((bitstream >> 9) & 0x3f80) | ((bitstream >> 8) & 0x7f)
            temp = (temp - 1800) / 18
            if temp < -40 and temp >= 70:
                self.print_verbose(f'invalid data {temp:.1f}C')
                return False
            # Set the instance values
            self.battery = bat
            self.temperature = temp
            temp = temp * 1.8 + 32
            if self.signature == ACURITE523_SIG_FREEZER:
                self.print_verbose('freezer: ', end='')
            elif self.signature == ACURITE523_SIG_FRIDGE:
                self.print_verbose('fridge: ', end='')
            self.print_verbose(f'{temp:.1f}F, battery={bat}')
            return True

