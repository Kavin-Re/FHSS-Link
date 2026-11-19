#include "fh.h"
#define ROTL(x, b) (uint64_t)(((x) << (b)) | ((x) >> (64 - (b))))
#define SIPROUND do { \
    v0 += v1; v1 = ROTL(v1, 13); v1 ^= v0; v0 = ROTL(v0, 32); \
    v2 += v3; v3 = ROTL(v3, 16); v3 ^= v2; \
    v0 += v3; v3 = ROTL(v3, 21); v3 ^= v0; \
    v2 += v1; v1 = ROTL(v1, 17); v1 ^= v2; v2 = ROTL(v2, 32); } while (0)

static uint64_t rd64(const uint8_t *p, size_t n) { uint64_t v = 0; size_t i; for (i = 0; i < n; i++) v |= (uint64_t)p[i] << (8u * i); return v; }

uint64_t fh_siphash24(const uint8_t key[16], const uint8_t *in, size_t len) {
    uint64_t k0 = rd64(key, 8), k1 = rd64(key + 8, 8);
    uint64_t v0 = k0 ^ 0x736f6d6570736575ULL, v1 = k1 ^ 0x646f72616e646f6dULL;
    uint64_t v2 = k0 ^ 0x6c7967656e657261ULL, v3 = k1 ^ 0x7465646279746573ULL;
    size_t full = len - (len % 8), i; uint64_t m, b;
    for (i = 0; i < full; i += 8) { m = rd64(in + i, 8); v3 ^= m; SIPROUND; SIPROUND; v0 ^= m; }
    b = ((uint64_t)(len & 0xFFu) << 56) | rd64(in + full, len - full);
    v3 ^= b; SIPROUND; SIPROUND; v0 ^= b;
    v2 ^= 0xFF; SIPROUND; SIPROUND; SIPROUND; SIPROUND;
    return v0 ^ v1 ^ v2 ^ v3;
}
uint16_t fh_crc16(const uint8_t *d, size_t n) {
    unsigned int c = 0xFFFFu; size_t i; int j;
    for (i = 0; i < n; i++) { c ^= (unsigned int)d[i] << 8; for (j = 0; j < 8; j++) c = ((c & 0x8000u) ? ((c << 1) ^ 0x1021u) : (c << 1)) & 0xFFFFu; }
    return (uint16_t)c;
}
uint8_t fh_crc8(const uint8_t *d, size_t n) {
    unsigned int c = 0; size_t i; int j;
    for (i = 0; i < n; i++) { c ^= d[i]; for (j = 0; j < 8; j++) c = ((c & 0x80u) ? ((c << 1) ^ 0x07u) : (c << 1)) & 0xFFu; }
    return (uint8_t)c;
}
void fh_derive(uint8_t out[16], const uint8_t master[16], const char label[4]) {
    uint8_t m[5]; unsigned i, j;
    for (j = 0; j < 4; j++) m[j] = (uint8_t)label[j];
    for (i = 0; i < 2; i++) {
        uint64_t h; m[4] = (uint8_t)i; h = fh_siphash24(master, m, 5);
        for (j = 0; j < 8; j++) out[i * 8u + j] = (uint8_t)(h >> (8u * j));
    }
}
void fh_keys_derive(fh_keys_t *k, const uint8_t master[16]) {
    fh_derive(k->hop, master, "hop1"); fh_derive(k->mac, master, "mac1"); fh_derive(k->guard, master, "grd1");
}
void fh_replay_init(fh_replay_t *r) {
    uint32_t i; r->tick = 0;
    for (i = 0; i < FH_REPLAY_CAP; i++) { r->e[i].used = 0; r->e[i].origin = 0; r->e[i].cls = 0; r->e[i].highest = 0; r->e[i].bitmap = 0; r->e[i].last_used = 0; }
}
int fh_replay_check_and_update(fh_replay_t *r, uint16_t origin, uint8_t cls, uint32_t ctr) {
    uint32_t i, found = FH_REPLAY_CAP, free_i = FH_REPLAY_CAP, lru = 0; int have_lru = 0; fh_rp_entry_t *e;
    r->tick++;
    for (i = 0; i < FH_REPLAY_CAP; i++) {
        if (r->e[i].used) {
            if (r->e[i].origin == origin && r->e[i].cls == cls) { found = i; break; }
            if (!have_lru || r->e[i].last_used < r->e[lru].last_used ||
                (r->e[i].last_used == r->e[lru].last_used &&
                 (r->e[i].origin < r->e[lru].origin || (r->e[i].origin == r->e[lru].origin && r->e[i].cls < r->e[lru].cls)))) { lru = i; have_lru = 1; }
        } else if (free_i == FH_REPLAY_CAP) free_i = i;
    }
    if (found == FH_REPLAY_CAP) {
        uint32_t s = (free_i != FH_REPLAY_CAP) ? free_i : lru; e = &r->e[s];
        e->used = 1; e->origin = origin; e->cls = cls; e->highest = ctr; e->bitmap = 1u; e->last_used = r->tick;
        return FH_RP_NEW;
    }
    e = &r->e[found]; e->last_used = r->tick;
    if (ctr > e->highest) {
        uint32_t sh = ctr - e->highest;
        e->bitmap = (sh >= 64u) ? 1u : ((e->bitmap << sh) | 1u); e->highest = ctr; return FH_RP_NEW;
    } else {
        uint32_t d = e->highest - ctr;
        if (d >= 64u) return FH_RP_OLD;
        if ((e->bitmap >> d) & 1u) return FH_RP_DUP;
        e->bitmap |= ((uint64_t)1u << d); return FH_RP_NEW;
    }
}
void fh_ctr_init(fh_ctr_t *c, uint32_t boot) { c->boot = boot; c->seq = 0; }
uint32_t fh_ctr_next(fh_ctr_t *c) {
    uint32_t v;
    if (c->boot >= 4096u) return 0xFFFFFFFFu;            /* exhausted: saturate (replay window then rejects every further frame) */
    v = (c->boot << 20) | c->seq;
    c->seq++;
    if (c->seq >= (1u << 20)) { c->seq = 0; c->boot++; }
    return v;
}
