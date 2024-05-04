#!/usr/bin/python3 -u

from acumonitor import Acumonitor

MULTICAST_ADDR = '224.3.29.70'
MULTICAST_PORT = 50000

acumonitor = Acumonitor(23, verbose=True)
#acumonitor.enable_multicast(MULTICAST_ADDR, MULTICAST_PORT, noise=False)
acumonitor.enable_server(MULTICAST_PORT)
acumonitor.start()

while True:
    if acumonitor.available(timeout=70):
        pass
    else:
        print(f'timeout')

