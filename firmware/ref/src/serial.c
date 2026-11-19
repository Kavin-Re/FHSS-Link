#include "fh.h"
#include "fh_fmt.h"
/* $FH,slot,ch,ok,retries,rssi*CRC8\n  - CRC-8 (0x07, init 0) over the text between '$' and '*' */
size_t fh_serial_encode(char *out, size_t cap, uint32_t slot, uint32_t ch, int ok, uint32_t retries, int32_t rssi) {
    fh_wbuf_t w; size_t bodylen; uint8_t crc;
    fh_wb_init(&w, out, cap);
    fh_wb_c(&w, '$'); fh_wb_s(&w, "FH,"); fh_wb_u(&w, slot); fh_wb_c(&w, ','); fh_wb_u(&w, ch); fh_wb_c(&w, ',');
    fh_wb_u(&w, ok ? 1u : 0u); fh_wb_c(&w, ','); fh_wb_u(&w, retries); fh_wb_c(&w, ','); fh_wb_i(&w, rssi);
    if (w.over) return 0;
    bodylen = w.n - 1u;
    crc = fh_crc8((const uint8_t *)out + 1, bodylen);
    fh_wb_c(&w, '*'); fh_wb_hex2(&w, crc); fh_wb_c(&w, '\n');
    return w.over ? 0u : w.n;
}
static int hexv(char c) { if (c >= '0' && c <= '9') return c - '0'; if (c >= 'a' && c <= 'f') return c - 'a' + 10; if (c >= 'A' && c <= 'F') return c - 'A' + 10; return -1; }
/* parse a decimal field [i, end); neg allowed if allow_neg. returns 0 on format error, 2 on range error, 1 ok */
static int num(const char *s, size_t i, size_t end, int allow_neg, int64_t *v) {
    int neg = 0, big = 0; uint64_t a = 0;
    if (i < end && s[i] == '-' && allow_neg) { neg = 1; i++; }
    if (i >= end) return 0;
    for (; i < end; i++) {
        if (s[i] < '0' || s[i] > '9') return 0;
        if (a > 100000000000ULL) big = 1; else a = a * 10u + (uint64_t)(s[i] - '0');
    }
    if (big) return 2;
    *v = neg ? -(int64_t)a : (int64_t)a; return 1;
}
int fh_serial_parse(const char *line, size_t len, fh_serial_rec_t *rec) {
    size_t b = 0, e = len, star, i, fs[6], nf = 0, start; int64_t v[5]; int k, r, rng = 0, t1, t2; unsigned tag;
    while (b < e && (line[b] == ' ' || line[b] == '\t')) b++;
    while (e > b && (line[e - 1] == '\n' || line[e - 1] == '\r' || line[e - 1] == ' ' || line[e - 1] == '\t')) e--;
    if (e - b < 6u || line[b] != '$') return FH_E_FORMAT;
    star = e; while (star > b + 1u && line[star - 1u] != '*') star--;
    if (star <= b + 1u) return FH_E_FORMAT;                  /* no '*' */
    star--;                                                   /* index of the last '*' */
    t1 = (star + 1u < e) ? hexv(line[star + 1u]) : -1;
    if (t1 < 0) return FH_E_FORMAT;
    if (star + 2u == e) tag = (unsigned)t1;
    else if (star + 3u == e && (t2 = hexv(line[star + 2u])) >= 0) tag = ((unsigned)t1 << 4) | (unsigned)t2;
    else return FH_E_FORMAT;
    /* body = line[b+1, star) ; fields */
    start = b + 1u;
    if (star - start < 3u || line[start] != 'F' || line[start + 1u] != 'H' || line[start + 2u] != ',') return FH_E_FORMAT;
    fs[nf++] = start + 3u;
    for (i = start + 3u; i < star; i++) if (line[i] == ',') { if (nf >= 6u) return FH_E_FORMAT; fs[nf++] = i + 1u; }
    if (nf != 5u) return FH_E_FORMAT;
    for (k = 0; k < 5; k++) {
        size_t fe = (k < 4) ? fs[k + 1] - 1u : star;
        r = num(line, fs[k], fe, k == 4, &v[k]);
        if (r == 0) return FH_E_FORMAT;
        if (r == 2) rng = 1;
    }
    if (fh_crc8((const uint8_t *)line + start, star - start) != (uint8_t)tag) return FH_E_CRC;
    if (rng || v[0] < 0 || v[0] > 0xFFFFFFFFLL || v[1] > 255 || (v[2] != 0 && v[2] != 1) || v[3] > 255 || v[4] < -128 || v[4] > 127) return FH_E_RANGE;
    if (rec) { rec->slot = (uint32_t)v[0]; rec->ch = (uint32_t)v[1]; rec->ok = (int)v[2]; rec->retries = (uint32_t)v[3]; rec->rssi = (int32_t)v[4]; }
    return FH_OK;
}
