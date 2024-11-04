# Description

Source code for parsing RF signals from wireless AcuRite models using a 433MHz receiver. More detailed research on analog-to-digital signal parsing can be found in [docs](docs).

# Introduction

In 2014 someone [reverse engineered](https://rayshobby.net/reverse-engineer-wireless-temperature-humidity-rain-sensors-part-2/) the RF signals of the AcuRite 00592W3 humidity/temperature sensor. Using this as a starting point, I decided to do the same with more recent models for data logging purposes. This method uses cheap 433MHz receivers to capture RF signals on Raspberry Pi and ESP32 boards for wireless transfer and data storage.

# Supported products

- AcuRite Digital Refrigerator/Freezer Thermometer model 00523
- AcuRite Digital Thermometer model 00609SBLA1

# Requirements

## Microcontroller board 

Any IC or board with digital pins that are capable of interfacing with a 433MHz superheterodyne receiver can be used. Source files are provided for Raspberry Pi and ESP32. See the README.md in the board's directory for usage information.

## 433MHZ superheterodyne receiver

A 433MHz superheterodyne receiver is recommended for capturing RF signals from wireless AcuRite thermometers. The following models have been tested.

### SRX882S

Accurate but fails to capture signals from devices at a greater distance. For the latter a more sensitive model like the RXB12 should be used.

### RXB12

More sensitive than the SRX882 but picks up far more noise. Noise can be eliminated with proper filtering on the software-side. This was the model I ended up using in the end.

# Notes

## Noise reduction

The interference caused by the Raspberry Pi's noisy power supply and pins can corrupt wireless data captured by the receiver. One solution is to switch to a different model board like an ESP32 or Arduino and use a clean power source with plenty of amperage (>= 1A), e.g. a USB phone charger.

## Noise filtering

When filtering out noise, it is highly recommended to make use of any parity bits and checksums for validating bitstream data. More often than not one or more of the bitstreams in a signal burst will fail to reach the receiver in an uncorrupted state. This is especially true for devices that will be placed inside a thick, metal enclosure like a refrigerator.

## Future support

Feel free to fork this repository and use the research to add support for other wireless Acurite devices.
