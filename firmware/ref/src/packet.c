#include "fh.h"
static void w32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24); }
static uint32_t r32(const uint8_t *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }
int fh_encode(const uint8_t mackey[16], const fh_frame_t *f, uint8_t *out, size_t cap, size_t *outlen) {
    size_t n, tot; uint32_t mac; uint16_t crc;
    if (!mackey || !f || !out || !outlen) return FH_E_ARG;
    if (f->plen > FH_MAX_PAYLOAD) return FH_E_PLEN;
    if (f->type > FH_T_ACK) return FH_E_TYPE;
    if (f->mode > 3u || f->retry > 3u) return FH_E_RSVD;
    tot = FH_OVERHEAD + f->plen;
    if (cap < tot) return FH_E_LEN;
    out[0] = (uint8_t)((FH_VER << 4) | f->type); out[1] = f->src; out[2] = (uint8_t)(f->mode | (f->retry << 2));
    w32(out + 3, f->slot); w32(out + 7, f->ctr); out[11] = (uint8_t)f->map; out[12] = (uint8_t)(f->map >> 8); out[13] = f->plen;
    for (n = 0; n < f->plen; n++) out[FH_HDR + n] = f->payload[n];
    n = FH_HDR + f->plen;
    mac = (uint32_t)fh_siphash24(mackey, out, n); w32(out + n, mac); n += FH_MAC_LEN;
    crc = fh_crc16(out, n); out[n] = (uint8_t)crc; out[n + 1] = (uint8_t)(crc >> 8);
    *outlen = tot; return FH_OK;
}
int fh_frame_crc_ok(const uint8_t *buf, size_t len) {
    uint16_t c;
    if (!buf || len < FH_MIN_FRAME || len > FH_MAX_FRAME) return 0;
    c = (uint16_t)((uint16_t)buf[len - 2] | (uint16_t)((uint16_t)buf[len - 1] << 8));
    return fh_crc16(buf, len - 2) == c;
}
int fh_decode(const uint8_t mackey[16], const uint8_t *buf, size_t len, fh_frame_t *out) {
    size_t plen, n; uint32_t mac, d = 0; size_t i;
    if (!mackey || !buf || !out) return FH_E_ARG;
    if (len < FH_MIN_FRAME || len > FH_MAX_FRAME) return FH_E_LEN;
    if (!fh_frame_crc_ok(buf, len)) return FH_E_CRC;
    if ((buf[0] >> 4) != FH_VER) return FH_E_VER;
    if ((buf[0] & 0x0Fu) > FH_T_ACK) return FH_E_TYPE;
    if (buf[2] & 0xF0u) return FH_E_RSVD;
    plen = buf[13];
    if (plen > FH_MAX_PAYLOAD || len != FH_OVERHEAD + plen) return FH_E_PLEN;
    n = FH_HDR + plen; mac = r32(buf + n);
    { uint32_t exp = (uint32_t)fh_siphash24(mackey, buf, n); for (i = 0; i < 4; i++) d |= ((exp ^ mac) >> (8u * i)) & 0xFFu; if (d) return FH_E_MAC; }
    out->type = buf[0] & 0x0Fu; out->src = buf[1]; out->mode = buf[2] & 3u; out->retry = (buf[2] >> 2) & 3u;
    out->slot = r32(buf + 3); out->ctr = r32(buf + 7); out->map = (uint16_t)((uint16_t)buf[11] | (uint16_t)((uint16_t)buf[12] << 8));
    out->plen = (uint8_t)plen; for (i = 0; i < FH_MAX_PAYLOAD; i++) out->payload[i] = (i < plen) ? buf[FH_HDR + i] : 0u;
    return FH_OK;
}
