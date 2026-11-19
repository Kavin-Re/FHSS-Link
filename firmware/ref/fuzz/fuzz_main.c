/* Deterministic mutation fuzz harness: fuzz_main <iterations> <seed>. Built plain and with ASan+UBSan (make san). Exits non-zero on an invariant violation. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fh.h"
static uint64_t S = 1;
static uint32_t rnd(void) { S ^= S << 13; S ^= S >> 7; S ^= S << 17; return (uint32_t)(S >> 16); }
static int die(const char *m, unsigned long it) { printf("FUZZ FAIL (iter %lu): %s\n", it, m); return 1; }
int main(int argc, char **argv) {
    unsigned long N = argc > 1 ? strtoul(argv[1], 0, 10) : 100000UL, it, ok_dec = 0, ok_ser = 0, ok_sync = 0, allow = 0;
    uint8_t mk[16], wire[FH_MAX_FRAME + 8], w2[FH_MAX_FRAME + 8]; size_t i, n; fh_frame_t f, g; fh_replay_t rp; fh_sync_t sy; fh_cfg_t cfg; fh_guard_t gd; fh_guard_cfg_t gc;
    char line[160]; fh_serial_rec_t rec;
    S = (argc > 2 ? strtoull(argv[2], 0, 10) : 1) * 0x9E3779B97F4A7C15ULL + 7; if (!S) S = 1;
    for (i = 0; i < 16; i++) mk[i] = (uint8_t)(rnd());
    fh_replay_init(&rp); fh_cfg_default(&cfg); fh_sync_init(&sy, 0);
    gc.allowed_mask = 0x1FFF; gc.max_power = 1; gc.max_duty_pct = 10; gc.max_burst_ms = 2000; gc.token_ttl_ms = 5000; gc.gap_reset_ms = 100; fh_guard_init(&gd, &gc, mk);
    for (it = 0; it < N; it++) {
        /* 1. packets: valid frame, then 0-4 random byte/bit edits or truncation/extension, then decode; accepted frames must re-encode to the same bytes */
        memset(&f, 0, sizeof f); f.type = (uint8_t)(rnd() % 3u); f.src = (uint8_t)rnd(); f.mode = (uint8_t)(rnd() % 4u); f.retry = (uint8_t)(rnd() % 4u); f.slot = rnd(); f.ctr = rnd(); f.map = (uint16_t)rnd();
        f.plen = (uint8_t)(rnd() % (FH_MAX_PAYLOAD + 1u)); for (i = 0; i < f.plen; i++) f.payload[i] = (uint8_t)rnd();
        if (fh_encode(mk, &f, wire, sizeof wire, &n) != FH_OK) return die("encode of a valid frame failed", it);
        memcpy(w2, wire, n); { unsigned e = rnd() % 5u, k; size_t len = n; for (k = 0; k < e; k++) { size_t p = rnd() % (len ? len : 1u); w2[p] = (uint8_t)(rnd() & 1u ? w2[p] ^ (1u << (rnd() % 8u)) : rnd()); }
            if (rnd() % 8u == 0) len = rnd() % (sizeof w2);
          if (rnd() % 16u == 0) for (k = 0; k < sizeof w2; k++) w2[k] = (uint8_t)rnd();
            if (fh_decode(mk, w2, len, &g) == FH_OK) { size_t m2; uint8_t re[FH_MAX_FRAME + 8]; ok_dec++;
                if (fh_encode(mk, &g, re, sizeof re, &m2) != FH_OK || m2 != len || memcmp(re, w2, len) != 0) return die("accepted frame does not re-encode identically", it);
                if (fh_replay_check_and_update(&rp, g.src, g.type, g.ctr) > 2) return die("replay result out of range", it); }
            (void)fh_frame_crc_ok(w2, len); }
        /* 2. serial lines: encode, mutate, parse; accepted lines must re-encode and parse to the same record */
        { size_t l = fh_serial_encode(line, sizeof line, rnd(), rnd() % 256u, (int)(rnd() % 2u), rnd() % 256u, (int32_t)(rnd() % 256u) - 128);
          unsigned e = rnd() % 4u, k; size_t len = l; if (!l) return die("serial encode failed", it);
          for (k = 0; k < e; k++) { size_t p = rnd() % len; line[p] = (char)(rnd() & 1u ? (int)(32 + rnd() % 95u) : (int)(rnd() & 0xFFu)); }
          if (rnd() % 8u == 0) len = rnd() % (l + 1u);
          if (fh_serial_parse(line, len, &rec) == FH_OK) { char b2[160]; size_t m2; fh_serial_rec_t r2; ok_ser++;
              m2 = fh_serial_encode(b2, sizeof b2, rec.slot, rec.ch, rec.ok, rec.retries, rec.rssi);
              if (!m2 || fh_serial_parse(b2, m2, &r2) != FH_OK || r2.slot != rec.slot || r2.ch != rec.ch || r2.ok != rec.ok || r2.retries != rec.retries || r2.rssi != rec.rssi) return die("serial round trip", it); } }
        /* 3. sync: random verified-packet events never break invariants */
        { int acc = fh_sync_on_packet(&sy, &cfg, (int)(rnd() % 2u), (uint64_t)rnd() % 5000u, (uint64_t)rnd() * 3u); ok_sync += (unsigned long)acc;
          if (rnd() % 3u == 0) fh_sync_on_miss(&sy, &cfg, rnd());
          if (rnd() % 7u == 0) (void)fh_sync_search_channel(&sy, &cfg, (uint64_t)rnd() * 5u);
          if ((unsigned)sy.st > 3u || (sy.has_anchor && sy.anchor_us > 0xFFFFFFFFFFFFULL)) return die("sync state out of range", it); }
        /* 4. guard: random request/token/kill stream; never allow when no token, killed, bad channel, or above the caps */
        { uint64_t now = (uint64_t)it * 3u + rnd() % 3u; uint32_t ch = rnd() % 20u, pw = rnd() % 4u, dt = 1u + rnd() % 30u; int r;
          if (rnd() % 50u == 0) fh_guard_accept_token(&gd, now, it, fh_guard_token_tag(mk, it));
          if (rnd() % 3000u == 0) fh_guard_kill(&gd, now);
          r = fh_guard_request(&gd, now, ch, pw, dt);
          if (r == FH_G_ALLOW) { allow++; if (gd.killed || ch >= 13u || pw > 1u || !gd.has_token) return die("guard allowed a forbidden request", it); } }
        /* 5. hop mapping always inside the mask */
        { fh_chmap_t m; uint32_t c; fh_chmap_set(&m, (uint16_t)rnd()); c = fh_hop_mapped(mk, ((uint64_t)rnd() << 24) ^ rnd(), &m); if (c >= 13u || !((m.mask >> c) & 1u) || m.n < 2u) return die("hop outside map", it); }
    }
    printf("fuzz ok: %lu iterations, decode accepted %lu, serial accepted %lu, sync accepted %lu, guard allowed %lu\n", N, ok_dec, ok_ser, ok_sync, allow);
    return 0;
}
