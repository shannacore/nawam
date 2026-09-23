/* Nawam network input guards. Copyright (c) 2026 Shanna Studio.
 * GPL-3.0-or-later. No disk operations or Windows dependencies.
 */
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <string.h>

/* HTTP Content-Length is an unsigned decimal, not a strtoull prefix. */
static inline int NawamParseContentLength(const char* text, size_t size, uint64_t* result)
{
    uint64_t value = 0;
    size_t i;
    if (text == NULL || result == NULL || size == 0)
        return 0;
    for (i = 0; i < size; i++) {
        unsigned int digit = (unsigned char)text[i] - '0';
        if (digit > 9 || value > (UINT64_MAX - digit) / 10)
            return 0;
        value = value * 10 + digit;
    }
    *result = value;
    return value != 0;
}

static inline int NawamDownloadLengthValid(uint64_t length, int buffered)
{
    /* Memory downloads are component/metadata files, never whole ISOs. */
    return length != 0 && (!buffered ||
        (length <= 64ULL * 1024 * 1024 && length <= SIZE_MAX - 2));
}

static inline int NawamDownloadChunkValid(uint64_t length, uint64_t used, uint64_t chunk)
{
    return used <= length && chunk <= length - used;
}

static inline uint32_t NawamReadLE32(const uint8_t* p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
        ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

/* Validate every EFI signature-list extent before accepting a downloaded DBX.
 * Structural validation is not cryptographic verification. The transport source
 * remains Microsoft's HTTPS repository; do not weaken upstream trust anchors.
 */
static inline int NawamDbxValid(const uint8_t* data, size_t size)
{
    size_t offset;
    static const uint8_t sha256[16] = { 0x26,0x16,0xc4,0xc1,0x4c,0x50,0x92,0x40,0xac,0xa9,0x41,0xf9,0x36,0x93,0x43,0x28 };
    uint32_t auth_length, list_length, header_length, signature_length;
    int first = 1;
    if (data == NULL || size < 40)
        return 0;
    auth_length = NawamReadLE32(data + 16);
    if (auth_length < 24 || auth_length > size - 16)
        return 0;
    offset = 16 + (size_t)auth_length;
    if (offset == size)
        return 0;
    while (offset < size) {
        if (size - offset < 28)
            return 0;
        list_length = NawamReadLE32(data + offset + 16);
        header_length = NawamReadLE32(data + offset + 20);
        signature_length = NawamReadLE32(data + offset + 24);
        if (list_length < 28 || list_length > size - offset ||
            header_length > list_length - 28 || signature_length <= 16 ||
            list_length - 28 - header_length < signature_length ||
            (list_length - 28 - header_length) % signature_length != 0)
            return 0;
        /* hash.c consumes the first list as SHA-256 with a 16-byte owner. */
        if ((first && memcmp(data + offset, sha256, 16) != 0) ||
            (memcmp(data + offset, sha256, 16) == 0 && signature_length != 48))
            return 0;
        first = 0;
        offset += list_length;
    }
    return offset == size;
}
