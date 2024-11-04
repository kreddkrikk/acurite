#include <stdint.h>
#include <vector>

/* All network packets must be prefixed with this value. */
#define TAG_TEMPMONITOR 0x38073162

/* Models */
#define MODEL_ACURITE523  1592
#define MODEL_ACURITE609  6585

/* Devices */
#define DEVICE_FREEZER  9690
#define DEVICE_FRIDGE   7784
#define DEVICE_OUTDOOR  8501

/* Status */
#define STATUS_UNKNOWN       0
#define STATUS_OK            1
#define STATUS_READ_FAIL     2
#define STATUS_TIMEOUT       3
#define STATUS_NO_DATA       4

/* Format must match between sender and receiver. */
struct Payload {
    uint32_t tag;
    uint16_t model;
    uint16_t device;
    uint8_t status;
    uint8_t battery;
    int16_t temperature;
    int16_t humidity;
} __attribute__((packed));

class Acurite {
    public:
        Acurite() { }
        class Device {
            public:
                Device() { }
                uint16_t device;
                virtual bool validate_bitstream(uint64_t bitstream) = 0;
                virtual Payload *create_payload(uint8_t status) = 0;
        };
        class Model {
            public:
                Model() { }
                std::vector<Device> devices;
                virtual void clear() = 0;
                virtual uint64_t parse_rf(uint32_t duration, uint8_t rfs) = 0;
        };
};

#define ACURITE523_SIGNAL_BIT_LENGTH   48      // Length of bitstream in bits
#define ACURITE523_SIGNAL_INV          -2
#define ACURITE523_SIGNAL_BIT_0_OFF    0
#define ACURITE523_SIGNAL_BIT_0_ON     1
#define ACURITE523_SIGNAL_BIT_1_OFF    2
#define ACURITE523_SIGNAL_BIT_1_ON     3
#define ACURITE523_SIGNAL_BITSTREAM_OFF    4
#define ACURITE523_SIGNAL_BITSTREAM_ON     5
#define ACURITE523_SIGNAL_CHUNK_END    6
#define ACURITE523_CHANNEL_ID          0       // Not used here for now
#define ACURITE523_SIG_FREEZER         0xc049  // Signatures seem to be hardcoded?
#define ACURITE523_SIG_FRIDGE          0xc07c

class Acurite523 : public Acurite {
    public:
        class Device : public Acurite::Device {
            public:
                Device(uint16_t device);
                Payload *create_payload(uint8_t status) override;
                bool validate_bitstream(uint64_t bitstream) override;
            private:
                uint16_t signature;
                uint8_t battery;
                float temperature;
                bool validate_checksum(uint64_t bitstream);
                bool validate_parity(uint8_t parity, uint8_t value);
        };
        class Model : public Acurite::Model {
            public:
                std::vector<Device> devices;
                Model(std::vector<Device> devices);
                void clear() override;
                uint64_t parse_rf(uint32_t duration, uint8_t rfs) override;
            private:
                bool is_acurite;
                bool chunk_open;
                uint64_t bitstream;     // Will contain all bits received in a single bitstream
                int bitstream_size;     // Size in bits of current bitstream
                bool bitstream_open;
                /* 4 contiguous opener signals mark the start of a bitstream. */
                int bitstream_opener_count;
                int last_rfs_type;
                int get_rfs_type(uint8_t rfs, uint32_t duration);
                bool is_bit_signal(int rfs_type);
                void open_bitstream();
                void close_bitstream();
                void open_chunk();
                void close_chunk();
        };
};

#define ACURITE609_SIGNAL_BIT_LENGTH   40          // Length of bitstream in bits
#define ACURITE609_SIGNAL_INV          -2
#define ACURITE609_SIGNAL_OFF          -1
#define ACURITE609_SIGNAL_BIT_0        0
#define ACURITE609_SIGNAL_BIT_1        1
#define ACURITE609_SIGNAL_BITSTREAM_START  2
#define ACURITE609_SIGNAL_BITSTREAM_END    3
#define ACURITE609_SIGNAL_CHUNK_START  4
#define ACURITE609_SIGNAL_CHUNK_END    5
#define ACURITE609_CHANNEL_ID          2
#define ACURITE609_TAG                 0xc261

class Acurite609 : public Acurite {
    public:
        class Device : public Acurite::Device {
            public:
                Device(uint16_t device);
                Payload *create_payload(uint8_t status) override;
                bool validate_bitstream(uint64_t bitstream) override;
            private:
                uint16_t signature;
                uint8_t battery;
                float temperature;
                float humidity;
                bool validate_checksum(uint64_t bitstream);
        };
        class Model : public Acurite::Model {
            public:
                std::vector<Device> devices;
                Model(std::vector<Device> devices);
                void clear() override;
                uint64_t parse_rf(uint32_t duration, uint8_t rfs) override;
            private:
                uint64_t bitstream;     // Will contain all bits received in a single bitstream
                int bitstream_size;     // Size in bits of current bitstream
                int last_rfs_type;
                bool is_acurite;
                bool bitstream_open;
                bool chunk_open;
                int get_rfs_type(uint8_t rfs, uint32_t duration);
                bool is_bit_signal(int rfs_type);
                void open_bitstream();
                void close_bitstream();
                void open_chunk();
                void close_chunk();
        };
};

