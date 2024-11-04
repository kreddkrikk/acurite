Scripts for Raspberry Pi. Requires Python 3.9+. Example code for use with 433MHz receiver connected to GPIO17:

```python
from acumonitor import Acumonitor

acumonitor = Acumonitor(pin_rx=17, verbosity=2)
acumonitor.start()

while True:
    data = acumonitor.available(timeout=70)
    if data:
        # Do something with data
    else:
        print(f'timeout')
```

Data is received in 14-byte chunks in the following format:

```
62 31 07 38  always 0x38073162
xx xx        model ID
xx xx        device ID
xx           status
xx           battery
xx xx        temperature
xx xx        humidity
```

Unofficial IDs for supported models and devices:

```python
MODEL_ACURITE523 = 1592 # 38 06
MODEL_ACURITE609 = 6585 # b9 19
DEVICE_OUTDOOR   = 8501 # 35 21
DEVICE_FREEZER   = 9690 # da 25
DEVICE_FRIDGE    = 7784 # 68 1e
```
