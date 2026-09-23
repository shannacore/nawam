/* Nawam security metadata validation. Copyright (c) 2026 Shanna Studio.
 * GPL-3.0-or-later. Pure input validation; no network or filesystem access.
 */
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <string.h>

static inline int NawamHexDigit(unsigned char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

/* Validate ALL rows before passing text to the permissive upstream parsers.
 * 0 = SBAT/SVN, 1 = SHA-1 certificate thumbprints. Empty lists are rejected.
 */
static inline unsigned NawamSecurityTextValid(const char* text, size_t size, int kind)
{
    size_t pos = 0, start, end, i, comma;
    unsigned count = 0, base, digit;
    uint64_t version;
    if (text == NULL || size == 0 || size > 64 * 1024)
        return 0;
    while (pos < size) {
        start = pos;
        while (pos < size && text[pos] != '\n') {
            unsigned char c = (unsigned char)text[pos];
            if ((c < 32 && c != '\t' && c != '\r') || c > 126)
                return 0;
            if (c == '\r' && (pos + 1 == size || text[pos + 1] != '\n'))
                return 0;
            pos++;
        }
        end = pos;
        if (pos < size) pos++;
        if (end > start && text[end - 1] == '\r') end--;
        if (end == start || text[start] == '#') continue;
        if (kind) {
            if (end - start != 40) return 0;
            for (i = start; i < end; i++)
                if (NawamHexDigit((unsigned char)text[i]) < 0) return 0;
        } else {
            comma = start;
            while (comma < end && text[comma] != ',') {
                char c = text[comma];
                if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                    (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-')) return 0;
                comma++;
            }
            if (comma == start || comma - start > 127 || comma == end) return 0;
            i = comma + 1;
            base = 10;
            if (end - i >= 2 && text[i] == '0' && text[i + 1] == 'x') { base = 16; i += 2; }
            start = i;
            version = 0;
            for (; i < end && text[i] != ','; i++) {
                digit = (unsigned)NawamHexDigit((unsigned char)text[i]);
                if (digit >= base || version > (UINT32_MAX - digit) / base) return 0;
                version = version * base + digit;
            }
            if (i == start || version == 0) return 0;
            if (i < end) {
                /* Only the standard SBAT format version row has a date column. */
                if (comma < 4 || memcmp(text + comma - 4, "sbat", 4) || end - i != 11) return 0;
                for (++i; i < end; i++) if (text[i] < '0' || text[i] > '9') return 0;
            }
        }
        count++;
    }
    return count;
}

/* Bounded JSON syntax walker, including complete consumption and nesting cap.
 * Values remain spans into the downloaded buffer; no allocations or mutation.
 */
static inline void NawamJsonSpace(const char** p, const char* end)
{
    while (*p < end && (**p == ' ' || **p == '\t' || **p == '\r' || **p == '\n')) (*p)++;
}

static inline int NawamJsonString(const char** p, const char* end)
{
    unsigned i;
    if (*p == end || *(*p)++ != '"') return 0;
    while (*p < end) {
        unsigned char c = (unsigned char)*(*p)++;
        if (c == '"') return 1;
        if (c < 32) return 0;
        if (c == '\\') {
            if (*p == end) return 0;
            c = (unsigned char)*(*p)++;
            if (c == 'u') {
                for (i = 0; i < 4; i++)
                    if (*p == end || NawamHexDigit((unsigned char)*(*p)++) < 0) return 0;
            } else if (strchr("\"\\/bfnrt", c) == NULL || c == 0) return 0;
        }
    }
    return 0;
}

static inline int NawamJsonValue(const char** p, const char* end, unsigned depth)
{
    char close;
    const char* start;
    if (depth > 32) return 0;
    NawamJsonSpace(p, end);
    if (*p == end) return 0;
    if (**p == '"') return NawamJsonString(p, end);
    if (**p == '{' || **p == '[') {
        close = *(*p)++ == '{' ? '}' : ']';
        NawamJsonSpace(p, end);
        if (*p < end && **p == close) { (*p)++; return 1; }
        for (;;) {
            if (close == '}') {
                if (!NawamJsonString(p, end)) return 0;
                NawamJsonSpace(p, end);
                if (*p == end || *(*p)++ != ':') return 0;
            }
            if (!NawamJsonValue(p, end, depth + 1)) return 0;
            NawamJsonSpace(p, end);
            if (*p == end) return 0;
            if (**p == close) { (*p)++; return 1; }
            if (*(*p)++ != ',') return 0;
            NawamJsonSpace(p, end);
        }
    }
    if (end - *p >= 4 && (!memcmp(*p, "true", 4) || !memcmp(*p, "null", 4))) { *p += 4; return 1; }
    if (end - *p >= 5 && !memcmp(*p, "false", 5)) { *p += 5; return 1; }
    if (**p == '-') (*p)++;
    if (*p == end) return 0;
    if (**p == '0') (*p)++;
    else {
        start = *p;
        while (*p < end && **p >= '0' && **p <= '9') (*p)++;
        if (*p == start) return 0;
    }
    if (*p < end && **p == '.') {
        start = ++(*p);
        while (*p < end && **p >= '0' && **p <= '9') (*p)++;
        if (*p == start) return 0;
    }
    if (*p < end && (**p == 'e' || **p == 'E')) {
        (*p)++;
        if (*p < end && (**p == '+' || **p == '-')) (*p)++;
        start = *p;
        while (*p < end && **p >= '0' && **p <= '9') (*p)++;
        if (*p == start) return 0;
    }
    return 1;
}

static inline const char* NawamJsonMember(const char* p, const char* end, const char* name)
{
    const char *key, *value, *found = NULL;
    size_t length = strlen(name);
    NawamJsonSpace(&p, end);
    if (p == end || *p++ != '{') return NULL;
    for (;;) {
        NawamJsonSpace(&p, end);
        if (p == end || *p == '}') return found;
        key = p;
        if (!NawamJsonString(&p, end)) return NULL;
        value = p;
        NawamJsonSpace(&p, end);
        if (p == end || *p++ != ':') return NULL;
        NawamJsonSpace(&p, end);
        if ((size_t)(value - key) == length + 2 && !memcmp(key + 1, name, length)) {
            if (found != NULL) return NULL;
            found = p;
        }
        if (!NawamJsonValue(&p, end, 0)) return NULL;
        NawamJsonSpace(&p, end);
        if (p == end || *p == '}') return found;
        if (*p++ != ',') return NULL;
    }
}

static inline int NawamCommitTimestamp(const char* text, size_t size, uint64_t* stamp, char sha[41])
{
    const char *p, *end, *object, *s;
    unsigned i, year, month, day, hour, minute, second, limit;
    uint64_t days = 0;
    static const unsigned mdays[] = {31,28,31,30,31,30,31,31,30,31,30,31};
    if (text == NULL || size == 0 || size > 1024 * 1024) return 0;
    p = text; end = text + size;
    if (!NawamJsonValue(&p, end, 0)) return 0;
    NawamJsonSpace(&p, end);
    if (p != end) return 0;
    p = text; NawamJsonSpace(&p, end);
    if (*p++ != '[') return 0;
    NawamJsonSpace(&p, end);
    object = p;
    if (!NawamJsonValue(&p, end, 0)) return 0;
    NawamJsonSpace(&p, end);
    if (p == end || *p != ']') return 0; /* exactly one commit */
    s = NawamJsonMember(object, p, "sha");
    if (s == NULL || p - s < 42 || *s != '"' || s[41] != '"') return 0;
    for (i = 0; i < 40; i++) if (NawamHexDigit((unsigned char)s[i + 1]) < 0) return 0;
    memcpy(sha, s + 1, 40); sha[40] = 0;
    s = NawamJsonMember(object, p, "commit");
    if (s == NULL) return 0;
    s = NawamJsonMember(s, p, "committer");
    if (s == NULL) return 0;
    s = NawamJsonMember(s, p, "date");
    if (s == NULL || p - s < 22 || s[0] != '"' || s[21] != '"') return 0;
    s++;
    for (i = 0; i < 20; i++) {
        char sep = i == 4 || i == 7 ? '-' : i == 10 ? 'T' : i == 13 || i == 16 ? ':' : i == 19 ? 'Z' : 0;
        if (sep ? s[i] != sep : (s[i] < '0' || s[i] > '9')) return 0;
    }
#define NAWAM_DEC2(n) ((unsigned)(s[n] - '0') * 10 + (unsigned)(s[(n) + 1] - '0'))
    year = NAWAM_DEC2(0) * 100 + NAWAM_DEC2(2); month = NAWAM_DEC2(5); day = NAWAM_DEC2(8);
    hour = NAWAM_DEC2(11); minute = NAWAM_DEC2(14); second = NAWAM_DEC2(17);
#undef NAWAM_DEC2
    if (year < 1970 || month < 1 || month > 12 || hour > 23 || minute > 59 || second > 59) return 0;
    limit = mdays[month - 1] + (month == 2 && year % 4 == 0 && (year % 100 != 0 || year % 400 == 0));
    if (day == 0 || day > limit) return 0;
    for (i = 1970; i < year; i++) days += 365 + (i % 4 == 0 && (i % 100 != 0 || i % 400 == 0));
    for (i = 1; i < month; i++) days += mdays[i - 1] + (i == 2 && year % 4 == 0 && (year % 100 != 0 || year % 400 == 0));
    *stamp = ((days + day - 1) * 24 + hour) * 3600 + minute * 60 + second;
    return *stamp != 0;
}
