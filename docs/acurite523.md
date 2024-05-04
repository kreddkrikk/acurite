# AcuRite Digital Refrigerator/Freezer Thermometer model 00523

Sniffs 433MHz RF signals from the 00523 fridge/freezer units. The 433MHz receiver module being used in this experiment is the RXB12 receiver. The 00523M units send temperature data as analog RF signals every ~60 seconds. Temperature range per the manual is -40C to 70C.

## Usage

The following example configures this module to listen for signals from a 
433MHz RF receiver's data pin on pin 17 and wait until a valid chunk of 1 or 
more blocks is received or a 70-second timeout is reached:

```python
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
```

## Analog RF signal to digital conversion format

A single chunk of analog signals is sent every ~60 seconds. This chunk comprises 3 identical blocks of data that can be converted to binary data. See the following sample data of various temperature readings:

```
Signature                P Byte 1  P Byte 0  Checksum  Calculated           C      F

110000000100100111001001 1 0001011 0 0111100 10011001  (1468 - 1800) / 18 = -18.5C -1.3F
110000000100100111001001 1 0001011 1 1000110 00100011  (1478 - 1800) / 18 = -17.9C -0.2F
110000000100100111001001 0 0001100 0 1011001 00110111  (1625 - 1800) / 18 = -9.8C       
110000000100100111001001 0 0001100 1 1111100 11011010  (1660 - 1800) / 18 = -7.8C       
110000000100100111001001 1 0001101 1 1101101 01001100  (1773 - 1800) / 18 = -1.5C       
110000000100100111001001 1 0001110 1 0000001 11100001  (1793 - 1800) / 18 = -0.4C       
110000000100100111001001 1 0001110 1 0011010 11111010  (1818 - 1800) / 18 = 1.0C        
110000000100100111001001 1 0001110 0 1110111 11010111  (1911 - 1800) / 18 = 6.1C        
110000000100100111001001 0 0001111 0 1010000 00110001  (2000 - 1800) / 18 = 11.1C       
110000000100100111001001 1 0010000 1 0000100 11100110  (2052 - 1800) / 18 = 14.0C       
110000000100100111001001 0 0010001 0 1101111 01010010  (2287 - 1800) / 18 = 27.0C  80.60
110000000100100111001001 0 0010001 0 1110111 01011010  (2295 - 1800) / 18 = 27.5C  81.50
110000000100100111001001 0 0010010 0 0000011 11100111  (2307 - 1800) / 18 = 28.1C  82.58
110000000100100111001001 0 0010010 1 0001101 01110001  (2317 - 1800) / 18 = 28.7C  83.66

P = parity bit
C = celsius
F = fahrenheit
```

Each block starts with a signature. For example, in all of the samples above:

```
110000000100100111001001
```

This is followed by a two-byte temperature base value. In the first sample:

```
1 0001011 0 0111100
```

The highest bit of both bytes (separated by spaces in the sample data) is a parity bit that specifies whether the number of set bits in the remaining 7 bits is odd (1) or even (0). To convert the base value to celsius, first shift out the two parity bits to get a 14-bit value:

```
00010110111100 = 1468
```

Then subtract 1800 and divide by 18:

```
(1468 - 1800) / 18 = -18.5C
```

Following the temperature data is a 1-byte checksum at the end of the block:

```
10011001 = 0x99
```

This value is the lower byte of the sum of all preceding bytes:

```
11000000 (0xc0) + 01001001 (0x49) + 11001001 (0xc9) + 10001011 (0x8b) + 00111100 (0x3c) = 0x299
```
