#include "fh.h"
uint64_t fh_hop_digest(const uint8_t key[16], uint64_t slot, uint8_t retry) {
    uint64_t m = ((uint64_t)retry << FH_SLOT_BITS) | (slot & FH_SLOT_MASK); uint8_t b[8]; unsigned i;
    for (i = 0; i < 8; i++) b[i] = (uint8_t)(m >> (8u * i));
    return fh_siphash24(key, b, 8);
}
int fh_hop_cfg(const fh_hopcfg_t *c, const uint8_t key[16], uint64_t slot, uint32_t *chan, uint32_t *retries, uint64_t *first_digest) {
    uint32_t retry, ch; uint64_t mask, thresh;
    if (!c || !key || c->M < 1u || c->RW < 1u || c->RW > 32u || c->NCH < 1u || c->RW * c->NCH > 64u) return FH_E_ARG;
    if ((uint64_t)c->M > ((uint64_t)1 << c->RW)) return FH_E_ARG;
    mask = (((uint64_t)1) << c->RW) - 1u; thresh = (((uint64_t)1) << c->RW) % (uint64_t)c->M;
    for (retry = 0; retry < 256u; retry++) {
        uint64_t d = fh_hop_digest(key, slot, (uint8_t)retry);
        if (retry == 0 && first_digest) *first_digest = d;
        for (ch = 0; ch < c->NCH; ch++) {
            uint64_t x = (d >> (c->RW * ch)) & mask, p = x * (uint64_t)c->M;
            if ((p & mask) >= thresh) { if (chan) *chan = (uint32_t)(p >> c->RW); if (retries) *retries = retry; return FH_OK; }
        }
    }
    return FH_E_RANGE;   /* unreachable in practice (4.4e-18 per hop for M=13); Python would loop with an 8-bit wrapping retry */
}
uint32_t fh_hop(const uint8_t key[16], uint64_t slot, uint32_t M) {
    fh_hopcfg_t c; uint32_t ch = 0;
    c.M = M; c.RW = 32; c.NCH = 2;
    if (fh_hop_cfg(&c, key, slot, &ch, NULL, NULL) != FH_OK) return 0;
    return ch;
}
void fh_chmap_set(fh_chmap_t *m, uint16_t mask) {
    unsigned i; uint16_t x = (uint16_t)(mask & FH_ALL_MASK);
    m->n = 0;
    for (i = 0; i < FH_NCH; i++) if ((x >> i) & 1u) m->n++;
    if (m->n < 2u) { x = FH_ALL_MASK; m->n = (uint8_t)FH_NCH; }
    m->mask = x; m->n = 0;
    for (i = 0; i < FH_NCH; i++) if ((x >> i) & 1u) m->list[m->n++] = (uint8_t)i;
}
uint32_t fh_hop_mapped(const uint8_t key[16], uint64_t slot, const fh_chmap_t *m) {
    return m->list[fh_hop(key, slot, m->n)];
}
uint64_t fh_slot_extend(uint64_t ref, uint32_t lo32) {
    uint64_t base = (ref & ~(uint64_t)0xFFFFFFFFu) | lo32, best = base, dbest, c;
    dbest = (base > ref) ? base - ref : ref - base;
    if (base >= ((uint64_t)1 << 32)) { c = base - ((uint64_t)1 << 32); if (ref - c < dbest) { best = c; dbest = ref - c; } }
    c = base + ((uint64_t)1 << 32);
    if (c <= FH_SLOT_MASK && c - ref < dbest) { best = c; }
    return best;
}
