#include "tempstation.h"

/**
 * Parsing && chunk-building for model-specific RF signals.
 */
Acurite523::Model::Model(std::vector<Acurite523::Device> devices) {
    this->devices = devices;
}

void Acurite523::Model::clear() {
    this->bitstream = 0;      // All bits received in a single bitstream
    this->bitstream_size = 0; // Size in bits of current bitstream
    this->last_rfs_type = ACURITE523_SIGNAL_INV;
    this->bitstream_open = false;
    this->bitstream_opener_count = 0;
    // Do not reset chunk variables
}

int Acurite523::Model::get_rfs_type(uint8_t rfs, uint32_t duration) {
    /* Returns the type of RF signal received.
       :param int rfs: RF signal received; either 0 || 1
       :param int duration: signal duration, in microseconds
       :return: the signal type
       :rtype: int
       */
    if (rfs == 0) {
        if (duration >= 100 && duration < 300)
            return ACURITE523_SIGNAL_BIT_0_OFF;
        else if (duration >= 300 && duration < 500)
            return ACURITE523_SIGNAL_BIT_1_OFF;
        else if (duration >= 500 && duration < 700)
            return ACURITE523_SIGNAL_BITSTREAM_OFF;
    }
    else if (rfs == 1) {
        if (duration >= 100 && duration < 300)
            return ACURITE523_SIGNAL_BIT_1_ON;
        else if (duration >= 300 && duration < 500)
            return ACURITE523_SIGNAL_BIT_0_ON;
        else if (duration >= 500 && duration < 700)
            return ACURITE523_SIGNAL_BITSTREAM_ON;
        else if (duration >= 20000 && duration < 60000)
            return ACURITE523_SIGNAL_CHUNK_END;
    }
    return ACURITE523_SIGNAL_INV;
}

bool Acurite523::Model::is_bit_signal(int rfs_type) {
    return 
        rfs_type == ACURITE523_SIGNAL_BIT_0_OFF || 
        rfs_type == ACURITE523_SIGNAL_BIT_0_ON || 
        rfs_type == ACURITE523_SIGNAL_BIT_1_OFF || 
        rfs_type == ACURITE523_SIGNAL_BIT_1_ON;
}

void Acurite523::Model::open_bitstream() {
    bitstream_open = true;
    bitstream_size = 0;
    bitstream = 0;
}

void Acurite523::Model::close_bitstream() {
    bitstream_open = false;
    bitstream_size = 0;
    bitstream = 0;
}

void Acurite523::Model::open_chunk() {
    chunk_open = true;
    open_bitstream();
}

void Acurite523::Model::close_chunk() {
    chunk_open = false;
    close_bitstream();
}

uint64_t Acurite523::Model::parse_rf(uint32_t duration, uint8_t rfs) {
    /* Parse a single RF signal && update chunk/bitstreams.
    */
    uint64_t result = 0;
    int rfs_type = ACURITE523_SIGNAL_INV;
    rfs_type = get_rfs_type(rfs, duration);
    if (last_rfs_type == ACURITE523_SIGNAL_BITSTREAM_OFF || !chunk_open) {
        if (rfs_type == ACURITE523_SIGNAL_BITSTREAM_ON)
            bitstream_opener_count += 1;
        if (bitstream_opener_count == 4) {
            bitstream_opener_count = 0;
            if (!chunk_open)
                open_chunk();
        }
    }
    else if (last_rfs_type == ACURITE523_SIGNAL_BIT_0_OFF && chunk_open) {
        if (rfs_type == ACURITE523_SIGNAL_BIT_0_ON && bitstream_size < ACURITE523_SIGNAL_BIT_LENGTH) {
            bitstream_size += 1;
            if (bitstream_size == ACURITE523_SIGNAL_BIT_LENGTH) {
                result = bitstream;
                close_bitstream();
            }
        }
        else if (rfs_type == ACURITE523_SIGNAL_BIT_1_ON && bitstream_size == ACURITE523_SIGNAL_BIT_LENGTH) {
            // Bitstream end
            result = bitstream;
            close_bitstream();
        }
        else if (rfs_type == ACURITE523_SIGNAL_CHUNK_END) {
            // Chunk end
            if (bitstream_size == ACURITE523_SIGNAL_BIT_LENGTH)
                result = bitstream;
            close_chunk();
        }
        bitstream_opener_count = 0;
    }
    else if (last_rfs_type == ACURITE523_SIGNAL_BIT_1_OFF && chunk_open) {
        if (rfs_type == ACURITE523_SIGNAL_BIT_1_ON && bitstream_size < ACURITE523_SIGNAL_BIT_LENGTH) {
            bitstream |= ((uint64_t)1L << (ACURITE523_SIGNAL_BIT_LENGTH - bitstream_size - 1));
            bitstream_size += 1;
            if (bitstream_size == ACURITE523_SIGNAL_BIT_LENGTH) {
                result = bitstream;
                close_bitstream();
            }
        }
    }
    last_rfs_type = rfs_type;

    // Done
    return result;
}

Acurite523::Device::Device(uint16_t device) {
    this->device = device;
    this->temperature = 0;
    this->battery = 0;
    // Signatures are hardcoded for these devices
    if (device == DEVICE_FREEZER)
        this->signature = ACURITE523_SIG_FREEZER;
    else if (device == DEVICE_FRIDGE)
        this->signature = ACURITE523_SIG_FRIDGE;
    else
        this->signature = 0;
}

Payload *Acurite523::Device::create_payload(uint8_t status) {
    Payload *payload = new Payload();
    payload->tag = TAG_TEMPMONITOR;
    payload->model = MODEL_ACURITE523;
    payload->device = device;
    payload->status = status;
    payload->battery = battery;
    payload->temperature = int16_t(temperature * 10);
    payload->humidity = 0;
    return payload;
}

bool Acurite523::Device::validate_checksum(uint64_t bitstream) {
    uint8_t checksum = bitstream & 0xff;
    uint32_t calculated = (((bitstream >> 8) & 0xff) + 
            ((bitstream >> 16) & 0xff) +
            ((bitstream >> 24) & 0xff) + 
            ((bitstream >> 32) & 0xff) + 
            ((bitstream >> 40))) & 0xff;
    if (checksum != calculated) {
        Serial.print("bad checksum: ");
        Serial.print(checksum, HEX);
    }
    return checksum == calculated;
}

bool Acurite523::Device::validate_parity(uint8_t parity, uint8_t value) {
    int on_bits = 0;
    for (int i = 0; i < 8; i++) {
        on_bits += value & 1;
        value >>= 1;
    }
    return (on_bits % 2) == parity;
}

bool Acurite523::Device::validate_bitstream(uint64_t bitstream) {
    /* Validates the signature and checksum of the specified bitstream.

       :param int bitstream: the bitstream of data to validate
       :return: true if bitstream is good, false if bad
       */
    // Parse and validate data
    if (bitstream == 0)
        return false;
    uint16_t sig = bitstream >> 32;
    if (sig != signature)
        return false;
    Serial.print("[");
    Serial.print(bitstream, BIN);
    Serial.print("] ");
    if (!validate_checksum(bitstream)) {
        Serial.print(", signature: ");
        Serial.println(signature, HEX);
        return false;
    }
    uint8_t bat = (bitstream >> 30) & 0x03;
    // Validate parity bit
    uint8_t parity1 = (bitstream >> 15) & 1;
    uint8_t byte1 = (bitstream >> 8) & 0x7f;
    uint8_t parity2 = (bitstream >> 23) & 1;
    uint8_t byte2 = (bitstream >> 16) & 0x7f;
    if (!validate_parity(parity1, byte1) || !validate_parity(parity2, byte2)) {
        Serial.println("parity bit fail");
        return false;
    }
    // Validate temperature
    float temp = ((uint16_t)byte2 << 7) | byte1;
    temp = (temp - 1800) / 18;
    if (temp < -40 || temp >= 70) {
        Serial.print("invalid data: ");
        Serial.print(temp);
        Serial.println("C");
        return false;
    }
    // Set the instance values
    battery = bat;
    temperature = temp;
    if (signature == ACURITE523_SIG_FREEZER)
        Serial.print("freezer: ");
    else if (signature == ACURITE523_SIG_FRIDGE)
        Serial.print("fridge: ");
    Serial.print(temp * 1.8 + 32);
    Serial.print("F, battery=");
    Serial.println(bat);
    return true;
}

