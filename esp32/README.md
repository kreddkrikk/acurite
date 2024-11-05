Source files for use with ESP32 systems. Modify/rename main source file `acumonitor.ino` as needed. When valid data is received by an Acurite device, `updateStats` is called:

```cpp
void updateStats(Acurite::Device& device) {
  Payload *payload = device.create_payload(STATUS_OK);
  /* ... do something with payload ... */
  delete payload;
}
```

`Payload` definition:

```cpp
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

```cpp
#define MODEL_ACURITE523  1592 // 38 06
#define MODEL_ACURITE609  6585 // b9 19
#define DEVICE_FREEZER  9690   // 35 21
#define DEVICE_FRIDGE   7784   // da 25
#define DEVICE_OUTDOOR  8501   // 68 1e
```
