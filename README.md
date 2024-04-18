# Description

Scripts to parse RF signals from wireless AcuRite models using a 433MHz receiver.

# Introduction

In 2014 someone [reverse engineered](https://rayshobby.net/reverse-engineer-wireless-temperature-humidity-rain-sensors-part-2/) the RF signals of the AcuRite 00592W3 humidity/temperature sensor. Using this as a starting point, I decided to do the same with more recent models for data logging purposes, using cheap 433MHz receivers to capture RF signals and a Raspberry Pi to interface with them and store the data to disk.

# Supported products

- AcuRite Digital Refrigerator/Freezer Thermometer model 00523
- AcuRite Digital Thermometer model 00609SBLA1

See the README.md in each product's subdirectory for a breakdown of the reverse engineering process and example code for importing the script and reading values.

# Requirements

## Microcontroller board 

Any IC or board with digital pins that are capable of interfacing with a 433MHz superheterodyne receiver can be used, but the Python scripts here are written for use with the GPIO pins on Raspberry Pi models. Python 3.9+ is required in this case.

## 433MHZ superheterodyne receiver

A 433MHz superheterodyne is recommended for capturing RF signals from wireless AcuRite thermometers. The following models have been tested.

### SRX882

Accurate but fails to capture signals from certain wireless units at a distance. For the latter a more sensitive model like the RXB12 should be used.

### RXB12

More sensitive than the SRX882 but picks up far more noise. Noise can be eliminated with proper filtering on the software-side.
