#include "acumonitor.h"

/**
 * Parsing && chunk-building for model-specific RF signals.
 */
Acurite609::Model::Model(std::vector<Acurite609::Device> devices) {
    this->devices = devices;
}

void Acurite609::Model::clear() {
    bitstream = 0;      // Will contain all bits received in a single bitstream
    bitstream_size = 0; // Size in bits of current bitstream
    last_rfs_type = ACURITE609_SIGNAL_INV;
    bitstream_open = false;
    // Only manually reset chunk status in parse_rf
}

int Acurite609::Model::get_rfs_type(uint8_t rfs, uint32_t duration) {
    /* Returns the type of RF signal received.

    :param int rfs: RF signal received; either 0 || 1
    :param int duration: signal duration, in microseconds
    :return: the signal type
    :rtype: int
    */
    if (rfs == 0) {
        if (duration < 1200)
            return ACURITE609_SIGNAL_OFF;
    }
    else if (rfs == 1) {
        if (duration < 300)
            return ACURITE609_SIGNAL_CHUNK_START;
        else if (duration >= 300 && duration < 1200)
            return ACURITE609_SIGNAL_BIT_0;
        else if (duration >= 1200 && duration < 3000)
            return ACURITE609_SIGNAL_BIT_1;
        else if (duration >= 8700 && duration < 9000)
            return ACURITE609_SIGNAL_BITSTREAM_START;
        else if (duration >= 10000 && duration < 20000)
            return ACURITE609_SIGNAL_BITSTREAM_END;
        else if (duration >= 20000 && duration < 40000)
            return ACURITE609_SIGNAL_CHUNK_END;
    }
    return ACURITE609_SIGNAL_INV;
}

bool Acurite609::Model::is_bit_signal(int rfs_type) {
    return rfs_type == ACURITE609_SIGNAL_BIT_0 || rfs_type == ACURITE609_SIGNAL_BIT_1;
}

void Acurite609::Model::open_bitstream() {
    bitstream_open = true;
    bitstream_size = 0;
    bitstream = 0;
}

void Acurite609::Model::close_bitstream() {
    bitstream_open = false;
    bitstream_size = 0;
    bitstream = 0;
}

void Acurite609::Model::open_chunk() {
    chunk_open = true;
    open_bitstream();
}

void Acurite609::Model::close_chunk() {
    chunk_open = false;
    close_bitstream();
}

uint64_t Acurite609::Model::parse_rf(uint32_t duration, uint8_t rfs) {
    /* Parse a single RF signal && update chunk/bitstreams.
     */
    uint64_t result = 0;
    int rfs_type = ACURITE609_SIGNAL_INV;
    rfs_type = get_rfs_type(rfs, duration);
    // Last signal must be ACURITE609_SIGNAL_OFF
    if (last_rfs_type == ACURITE609_SIGNAL_OFF && !chunk_open) {
        if (rfs_type == ACURITE609_SIGNAL_BITSTREAM_START)
            open_chunk();
    }
    else if (last_rfs_type == ACURITE609_SIGNAL_OFF && chunk_open) {
        if (rfs_type == ACURITE609_SIGNAL_BITSTREAM_START && !bitstream_open) {
            if (bitstream_size == ACURITE609_SIGNAL_BIT_LENGTH)
                result = bitstream;
            open_bitstream();
        }
        else if (rfs_type == ACURITE609_SIGNAL_BITSTREAM_END && bitstream_open) {
            if (bitstream_size == ACURITE609_SIGNAL_BIT_LENGTH)
                result = bitstream;
            close_bitstream();
        }
        else if (rfs_type == ACURITE609_SIGNAL_CHUNK_END) {
            last_rfs_type = rfs_type;
            if (bitstream_size == ACURITE609_SIGNAL_BIT_LENGTH)
                result = bitstream;
            close_chunk();
        }
        else if (is_bit_signal(rfs_type) && bitstream_open) {
            if (rfs_type == ACURITE609_SIGNAL_BIT_1 && bitstream_size < ACURITE609_SIGNAL_BIT_LENGTH)
                bitstream |= ((uint64_t)1L << (ACURITE609_SIGNAL_BIT_LENGTH - bitstream_size - 1));
            bitstream_size += 1;
            if (bitstream_size == ACURITE609_SIGNAL_BIT_LENGTH) {
                result = bitstream;
                close_bitstream();
            }
        }
    }
    last_rfs_type = rfs_type;

    // Done
    return result;
}

Acurite609::Device::Device(uint16_t device) {
    this->device = device;
    this->temperature = 0;
    this->humidity = 0;
    this->battery = 0;
    this->signature = 0;
}

Payload *Acurite609::Device::create_payload(uint8_t status) {
    Payload *payload = new Payload();
    payload->tag = TAG_TEMPMONITOR;
    payload->model = MODEL_ACURITE609;
    payload->device = device;
    payload->status = status;
    payload->battery = battery;
    payload->temperature = int16_t(temperature * 10);
    payload->humidity = int16_t(humidity * 10);
    return payload;
}

bool Acurite609::Device::validate_checksum(uint64_t bitstream) {
    uint8_t checksum = bitstream & 0xff;
    uint32_t calculated = (((bitstream >> 8) & 0xff) + 
            ((bitstream >> 16) & 0xff) +
            ((bitstream >> 24) & 0xff) + 
            ((bitstream >> 32))) & 0xff;
    if (checksum != calculated) {
        Serial.print("bad checksum: ");
        Serial.print(checksum, HEX);
    }
    return checksum == calculated;
}

/**
 * Validates the signature && checksum of the specified bitstream.
 *
 * @param bitstream bitstream of data to validate
 * @return true if bitstream is good, false if bad
 */
bool Acurite609::Device::validate_bitstream(uint64_t bitstream) {
    if (bitstream == 0)
        return false;
    Serial.print("[");
    Serial.print(bitstream, BIN);
    Serial.print("] ");
    uint16_t sig = bitstream >> 32;
    if (signature != 0 && signature != sig) {
        Serial.print("bad signature: ");
        Serial.println(sig, HEX);
        return false;
    }
    int cha = (bitstream >> 28) & 0x03;
    if (cha != ACURITE609_CHANNEL_ID) {
        Serial.print("bad channel: ");
        Serial.println(cha);
        return false;
    }
    if (!validate_checksum(bitstream)) {
        Serial.print(", signature: ");
        Serial.println(sig, HEX);
        return false;
    }
    uint8_t bat = (bitstream >> 30) & 0x03;
    float temp = (bitstream >> 15) & 0x1fff;
    if ((uint16_t)temp & 0x1000 == 0x1000)
        temp = -(0x2000 - temp);
    temp /= 20;
    float hum = (bitstream >> 8) & 0x7f;
    if (hum < 1 || hum > 99 || temp < -40 || temp > 70) {
        Serial.print("invalid data: ");
        Serial.print(temp);
        Serial.print("C ");
        Serial.print(hum);
        Serial.println("%");
        return false;
    }
    // Set the instance values
    if (signature == 0)
        signature = sig;
    battery = bat;
    humidity = hum;
    temperature = temp;
    Serial.print("outdoor: ");
    Serial.print(temp * 1.8 + 32);
    Serial.print("F ");
    Serial.print(hum);
    Serial.print("%, battery=");
    Serial.println(bat);
    return true;
}

