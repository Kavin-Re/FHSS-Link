/* Line-driven reference harness for tests/xval.py (cross-validation against the Python references). stdin commands, stdout answers. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fh.h"
static int hexv(int c) { return (c >= '0' && c <= '9') ? c - '0' : (c >= 'a' && c <= 'f') ? c - 'a' + 10 : (c >= 'A' && c <= 'F') ? c - 'A' + 10 : -1; }
static fh_guard_t G; static uint8_t GK[16]; static fh_ladder_t L;
int main(void) {
    char ln[512]; setvbuf(stdout, NULL, _IOLBF, 0);
    while (fgets(ln, sizeof ln, stdin)) {
        char cmd[8]; size_t n = strlen(ln); while (n && (ln[n - 1] == '\n' || ln[n - 1] == '\r')) ln[--n] = 0;
        if (sscanf(ln, "%7s", cmd) != 1) continue;
        if (!strcmp(cmd, "H")) {            /* H key32hex(16 bytes in wire order) slot M RW NCH */
            char kh[40]; unsigned long long slot; unsigned M, RW, NCH, i; uint8_t key[16]; fh_hopcfg_t c; uint32_t ch = 0, r = 0; uint64_t d = 0; int rc;
            if (sscanf(ln, "H %39s %llu %u %u %u", kh, &slot, &M, &RW, &NCH) != 5) { puts("ERR"); continue; }
            for (i = 0; i < 16; i++) key[i] = (uint8_t)(hexv(kh[2 * i]) * 16 + hexv(kh[2 * i + 1]));
            c.M = M; c.RW = RW; c.NCH = NCH; rc = fh_hop_cfg(&c, key, slot, &ch, &r, &d);
            printf("%d %u %u %llu\n", rc, ch, r, (unsigned long long)d);
        } else if (!strcmp(cmd, "S")) {     /* S slot ch ok retries rssi */
            unsigned long long slot; unsigned ch, ok, rt; int rssi; char o[64]; size_t k;
            if (sscanf(ln, "S %llu %u %u %u %d", &slot, &ch, &ok, &rt, &rssi) != 5) { puts("ERR"); continue; }
            k = fh_serial_encode(o, sizeof o, (uint32_t)slot, ch, (int)ok, rt, rssi); o[k] = 0; fputs(k ? o : "NONE\n", stdout);
        } else if (!strcmp(cmd, "P")) {     /* P <rest of line is the serial line, hex-encoded to survive whitespace> */
            char hx[400]; char raw[200]; size_t i, m; fh_serial_rec_t r; int rc;
            if (sscanf(ln, "P %399s", hx) != 1) { puts("ERR"); continue; }
            m = strlen(hx) / 2; for (i = 0; i < m && i < sizeof raw; i++) raw[i] = (char)(hexv(hx[2 * i]) * 16 + hexv(hx[2 * i + 1]));
            rc = fh_serial_parse(raw, m, &r);
            if (rc == FH_OK) printf("OK %u %u %d %u %d\n", r.slot, r.ch, r.ok, r.retries, r.rssi); else printf("ERR %d\n", rc);
        } else if (!strcmp(cmd, "GI")) {    /* GI : fresh guard, key 0..15, ch mask 0x00FF, power<=1, duty 10, burst 2000, ttl 5000, no gap reset */
            fh_guard_cfg_t c; unsigned i; for (i = 0; i < 16; i++) GK[i] = (uint8_t)i;
            c.allowed_mask = 0x00FF; c.max_power = 1; c.max_duty_pct = 10; c.max_burst_ms = 2000; c.token_ttl_ms = 5000; c.gap_reset_ms = 0xFFFFFFFFu; fh_guard_init(&G, &c, GK); puts("ok");
        } else if (!strcmp(cmd, "GT")) {    /* GT ms ctr good */
            unsigned long long ms, ctr; int good; if (sscanf(ln, "GT %llu %llu %d", &ms, &ctr, &good) != 3) { puts("ERR"); continue; }
            printf("%d\n", fh_guard_accept_token(&G, ms, ctr, fh_guard_token_tag(GK, ctr) ^ (good ? 0u : 1u)));
        } else if (!strcmp(cmd, "GK")) { unsigned long long ms; if (sscanf(ln, "GK %llu", &ms) == 1) fh_guard_kill(&G, ms); puts("ok");
        } else if (!strcmp(cmd, "GR")) {    /* GR ms ch power dt */
            unsigned long long ms; unsigned ch, pw, dt; if (sscanf(ln, "GR %llu %u %u %u", &ms, &ch, &pw, &dt) != 4) { puts("ERR"); continue; }
            printf("%d\n", fh_guard_request(&G, ms, ch, pw, dt));
        } else if (!strcmp(cmd, "LI")) { fh_ladder_init(&L); puts("ok");
        } else if (!strcmp(cmd, "LS")) {    /* LS slot ok ch avoiding */
            unsigned long long s; int ok, avoiding; unsigned ch; fh_ladder_event_t e; int sw;
            if (sscanf(ln, "LS %llu %d %u %d", &s, &ok, &ch, &avoiding) != 4) { puts("ERR"); continue; }
            sw = fh_ladder_step(&L, s, ok, ch, avoiding, &e); printf("%d %d\n", L.mode, sw);
        }
    }
    return 0;
}
