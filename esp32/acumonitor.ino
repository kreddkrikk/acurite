#include "acumonitor.h"

#define PIN_RX 10

// Devices
Acurite523::Device freezer(DEVICE_FREEZER);
Acurite523::Device fridge(DEVICE_FRIDGE);
Acurite609::Device outdoor(DEVICE_OUTDOOR);
Acurite523::Model acurite523({ freezer, fridge });
Acurite609::Model acurite609({ outdoor });

// Tracking
int prevRfs = -1;
uint32_t start = micros(); // Start time of contiguous pulse

void setup() {
}

void updateStats(Acurite::Device& device) {
  Payload *payload = device.create_payload(STATUS_OK);
  /* ... do something with payload ... */
  delete payload;
}

bool parseRf(uint32_t duration, uint8_t rfs) {
    uint64_t result;
    if (result = acurite523.parse_rf(duration, rfs)) {
        for (Acurite523::Device device : acurite523.devices) {
            if (device.validate_bitstream(result)) {
                updateStats(device);
                return true;
            }
        }
    }
    if (result = acurite609.parse_rf(duration, rfs)) {
        for (Acurite609::Device device : acurite609.devices) {
            if (device.validate_bitstream(result)) {
                updateStats(device);
                return true;
            }
        }
    }
    return false;
}

void resetRf() {
    acurite523.clear();
    acurite609.clear();
    start = micros();
}

void loop() {
    /* Read a continous stream of RF pulses until valid temperature data is
       received. Performs analog to digital conversion in each read via the 
       model-specific parsing function. The parsing function attempts to 
       filter out any noise and build a valid bitstream of binary data comprising 
       the temperature, humidity, etc.
     */
    int rfs = 0;
    uint32_t now = 0;
    uint32_t duration = 0;

    // Read until a valid bitstream is received
    rfs = digitalRead(PIN_RX) ^ 1;
    now = micros();
    if (prevRfs >= 0 && rfs != prevRfs) {
        duration = now - start;
        if (duration >= 100) {
            // Parse model-specific RF pulses
            if (parseRf(duration, prevRfs))
                resetRf();
        }
    }
    if (rfs != prevRfs)
        start = now;
    prevRfs = rfs;
}

