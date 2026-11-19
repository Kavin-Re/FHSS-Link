#include "fh.h"
/* discounted Beta(a,b) counts in Q16 (65536 = 1.0). gamma 0.99 = 64881/65536, floor 0.001 = 66/65536 (as sim/adaptive.py Thompson). */
static uint64_t rng_next(uint64_t *s) { uint64_t x = *s; x ^= x >> 12; x ^= x << 25; x ^= x >> 27; *s = x; return x * 0x2545F4914F6CDD1DULL; }
static uint32_t isqrt64(uint64_t v) { uint64_t r = 0, b = (uint64_t)1 << 62; while (b > v) b >>= 2; while (b) { if (v >= r + b) { v -= r + b; r = (r >> 1) + b; } else r >>= 1; b >>= 2; } return (uint32_t)r; }
void fh_afh_init(fh_afh_t *s, uint32_t n, uint32_t seed) {
    uint32_t i; s->n = (n > FH_NCH_MAX) ? FH_NCH_MAX : n; s->rng = 0x9E3779B97F4A7C15ULL ^ ((uint64_t)seed << 17) ^ seed; if (!s->rng) s->rng = 1;
    for (i = 0; i < FH_NCH_MAX; i++) { s->a[i] = FH_Q; s->b[i] = FH_Q; }
}
void fh_afh_update(fh_afh_t *s, uint32_t ch, int ok) {
    uint32_t i;
    if (ch >= s->n) return;
    for (i = 0; i < s->n; i++) {
        uint32_t a = (uint32_t)(((uint64_t)s->a[i] * 64881u) >> 16), b = (uint32_t)(((uint64_t)s->b[i] * 64881u) >> 16);
        s->a[i] = a < 66u ? 66u : a; s->b[i] = b < 66u ? 66u : b;
    }
    if (ok) s->a[ch] += FH_Q; else s->b[ch] += FH_Q;
}
uint32_t fh_afh_mean(const fh_afh_t *s, uint32_t ch) {
    uint64_t t; if (ch >= s->n) return 0; t = (uint64_t)s->a[ch] + s->b[ch]; return (uint32_t)(((uint64_t)s->a[ch] << 16) / t);
}
int fh_afh_avoiding(const fh_afh_t *s) {
    uint32_t i; for (i = 0; i < s->n; i++) if (fh_afh_mean(s, i) < 39322u) return 1;   /* 0.6 in Q16 (39321.6 rounded up) */
    return 0;
}
uint32_t fh_afh_sample(fh_afh_t *s, uint32_t ch) {
    uint64_t S, var; uint32_t m, sd; int64_t z, v; uint32_t u;
    if (ch >= s->n) return 0;
    m = fh_afh_mean(s, ch); S = (uint64_t)s->a[ch] + s->b[ch];
    var = ((uint64_t)m * (FH_Q - m)) / (S + FH_Q);            /* Beta variance ab/((a+b)^2 (a+b+1)), Q16 */
    sd = isqrt64(var << 16);
    u = (uint32_t)(rng_next(&s->rng) >> 48);                    /* uniform 16 bit */
    z = ((int64_t)u * 2 - 65536) * 113513 / 65536;              /* uniform on [-sqrt3, sqrt3] (unit variance), Q16 */
    v = (int64_t)m + (z * (int64_t)sd) / 65536;
    return (uint32_t)(v < 0 ? 0 : v > (int64_t)FH_Q ? (int64_t)FH_Q : v);
}
uint16_t fh_afh_pick_map(fh_afh_t *s, uint32_t thr_q16, uint32_t min_good) {
    uint32_t i, j, cnt = 0, sm[FH_NCH_MAX]; uint16_t mask = 0; uint32_t used = 0;
    for (i = 0; i < s->n; i++) { sm[i] = fh_afh_sample(s, i); if (sm[i] >= thr_q16) { mask = (uint16_t)(mask | (1u << i)); cnt++; } }
    if (min_good > s->n) min_good = s->n;
    while (cnt < min_good) {            /* too few channels pass: add the best remaining by sample (ties: lowest index) */
        uint32_t best = FH_NCH_MAX, bv = 0;
        for (j = 0; j < s->n; j++) if (!((mask >> j) & 1u) && (best == FH_NCH_MAX || sm[j] > bv)) { best = j; bv = sm[j]; }
        if (best == FH_NCH_MAX) break;
        mask = (uint16_t)(mask | (1u << best)); cnt++; used++;
    }
    (void)used; return mask;
}
