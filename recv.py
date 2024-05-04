#!/usr/bin/python3 -u

from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.animation import FuncAnimation
import socket
import struct
import threading
import time

MULTICAST_TAG_NOISE = 5391
MULTICAST_TAG_609 = 0xc261
MULTICAST_TAG_523_FREEZER = 0xc049
MULTICAST_TAG_523_FRIDGE = 0xc07c
MULTICAST_ADDR = '224.3.29.70'
MULTICAST_PORT = 50000
MAX_XAXIS = 10000

class Plotter():
    def __init__(self):
        self.noise = [ 0 ]
        self.dates = [ None ]

    def create_multicast(self):
        # socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((MULTICAST_ADDR, MULTICAST_PORT))
        group = socket.inet_aton(MULTICAST_ADDR)
        mreq = struct.pack('4sL', group, socket.INADDR_ANY)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    def start_client(self):
        threading.Thread(target=self.update, daemon=True).start()

    def create_client(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print('Connecting to server...')
        while True:
            try:
                self.sock.connect(('192.168.1.177', 50000))
                break
            except Exception:
                print('Server not responding, retrying...')
                time.sleep(4)

    def init_plot(self):
        # plot
        plt.rcParams.update({
            'font.family': 'monospace',
            'font.monospace': 'Liberation Mono',
            'font.size': '10.0',
            'font.weight': '100',
            'axes.edgecolor': '#ecf2f4',
            'axes.facecolor': '#1c2224',
            'axes.labelcolor': '#ecf2f4',
            'axes.labelweight': '700',
            'axes.linewidth': '0.5',
            'axes.titleweight': '700',
            'axes.ymargin' : '100',
            'xtick.labelcolor': '#ecf2f4',
            'xtick.color': '#ecf2f4',
            'ytick.labelcolor': '#ecf2f4',
            'ytick.color': '#ecf2f4',
            'figure.facecolor': '#2c3234',
            'figure.autolayout' : 'True',
            'legend.facecolor': '#2c3234',
            'legend.labelcolor': '#ecf2f4',
            'patch.linewidth': '0.5',
            'text.color': '#ecf2f4',
                })
        self.fig, ax = plt.subplots()
        ax.set_title('TEMPMONITOR RF')
        ax.set_xticklabels([], rotation=25)
        ax.grid(visible=True, axis='y', color='#3c4244', linewidth=0.5)
        #ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        #ax.xaxis.set_major_locator(plt.MaxNLocator(10))
        self.lines, = ax.plot([], [])
        #self.fig.tight_layout()
        animation = FuncAnimation(
                self.fig, self.animate, interval=1, 
                repeat=False, cache_frame_data=False)
        from PyQt5 import QtWidgets
        from PyQt5.QtCore import Qt
        figman = plt.get_current_fig_manager()
        window = figman.window
        window.showMaximized()
        canvas = self.fig.canvas
        canvas.setFixedHeight(200)
        plt.show()

    # update
    def animate(self, frame):
        self.lines.set_data(self.dates, self.noise)
        self.fig.gca().set_ylim([-0.05, 1.05])
        self.fig.gca().relim()
        self.fig.gca().autoscale_view()
        return self.lines

    def update(self):
        us = 0
        print('Waiting for data...')
        while True:
            d, a = self.sock.recvfrom(1024)
            length = len(d)
            if length == 0:
                print(f'Disconnected from server, reconnecting...')
                self.create_client()
                continue
            if length < 2:
                print(f'Invalid packet length {length} from {a}')
                continue
            tag, = struct.unpack('<H', d[:2])
            if tag == MULTICAST_TAG_609 and length == 8:
                bat, sig, temp, hum = struct.unpack('<bbhh', d[2:])
                temp /= 10
                hum /= 10
                temp = temp * 1.8 + 32
                print(f'[Acurite609] bat={bat}, sig={sig}, {temp:0.1f}f {hum:0.0f}%')
            elif tag == MULTICAST_TAG_523_FREEZER and length == 6:
                bat, sig, temp = struct.unpack('<bbh', d[2:])
                temp /= 10
                temp = temp * 1.8 + 32
                print(f'[Acurite523] Freezer: bat={bat}, sig={sig}, {temp:0.1f}f')
            elif tag == MULTICAST_TAG_523_FRIDGE and length == 6:
                bat, sig, temp = struct.unpack('<bbh', d[2:])
                temp /= 10
                temp = temp * 1.8 + 32
                print(f'[Acurite523] Fridge: bat={bat}, sig={sig}, {temp:0.1f}f')
            elif tag == MULTICAST_TAG_NOISE and length == 7:
                duration, rfs = struct.unpack('<Ib', d[2:])
                duration = int(duration / 200)
                self.dates += [ i for i in range(us, us + duration) ]
                self.dates = self.dates[-MAX_XAXIS:]
                self.noise += [ rfs ] * duration
                self.noise = self.noise[-MAX_XAXIS:]
                us += duration
            else:
                print(f'Invalid packet length {length}')

if __name__ == '__main__':
    plotter = Plotter()
    #plotter.create_multicast()
    plotter.create_client()
    plotter.start_client()
    plotter.init_plot()

