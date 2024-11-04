Source files for use with ESP32 systems. Modify/rename main source file `acumonitor.ino` as needed. When valid data is received by an Acurite device, `updateStats` is called:

```
void updateStats(Acurite::Device& device) {
  Payload *payload = device.create_payload(STATUS_OK);
  /* ... do something with payload ... */
  delete payload;
}
```

`Payload` definition:

```
struct Payload {
    uint32_t tag;
    uint16_t model;
    uint16_t device;
    uint8_t status;
    uint8_t battery;
    int16_t temperature;
    int16_t humidity;
} __attribute__((packed));
```

Unofficial IDs for supported models and devices:

```python
MODEL_ACURITE523 = 1592 # 38 06
MODEL_ACURITE609 = 6585 # b9 19
DEVICE_OUTDOOR   = 8501 # 35 21
DEVICE_FREEZER   = 9690 # da 25
DEVICE_FRIDGE    = 7784 # 68 1e
```
