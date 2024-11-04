# AcuRite Digital Thermometer model 00609SBLA1

Sniffs 433MHz radio frequency (RF) signals from the AcuRite 00609SBLA2 outdoor unit using the SRX882S Micropower Superheterodyne Receiver Module. The 00609SBLA2 outdoor unit sends temperature and humidity data as analog RF signals, approximately 9 times every 5 minutes (~33.33 seconds). Temperature range per the manual is -40C to 70C.

## Analog RF signal to digital conversion format

The 00609SBLA2 outdoor unit sends RF signals as a single RF burst of analog pulses every ~30 seconds. A 'chunk' here refers to the binary representation of this burst which is composed of a group of one to six identical, contiguous 'blocks'. A 'block' is a collection of analog pulses representing one contiguous stream of bits. Below is an example of a block after binary conversion:

```
1100000010100001010110110010010111100001

Name          Binary          Decimal     Adjusted
Signature:    11000000        0xc0
Battery:      10              2           low
Channel:      10              2           Channel A
Temperature:  0001010110110   694 0x2b6   694/20 = 35C (95F)
Humidity:     0100101         37          37%
Checksum:     11100001
```

The checksum is the sum of the first four bytes.

Below freezing values need to be subtracted from 0x2000:

```
1100000010101111110000010100010101110101

Name          Binary          Decimal     Adjusted
Signature:    11000000        0xc0
Battery:      10              2           low
Channel:      10              2           Channel A
Temperature:  1111110000010   8066 0x1f82 -(0x2000-0x1f82)/20 = -6C (21F)
Humidity:     1000101         69          69%
Checksum:     01110101
```

After replacing outdoor unit's batteries:

```
0000111100100001001000110010011101111010

Name          Binary          Decimal     Adjusted
Signature:    00001111        0x0f
Battery:      00              0           good
Channel:      10              2           Channel A
Temperature:  0001001000110   582 0x246   582/20 = 29.1C (84.38F)
Humidity:     0100111         39          39%
Checksum:     01111010
```

The signature is randomly generated each time the device boots.

