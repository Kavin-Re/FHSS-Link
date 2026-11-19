/* 3-node host demo in ONE process: node 0 = TX master, node 1 = RX follower, node 2 = JAM (own-link test source behind the safety guard).
 * usage: demo [--slots N] [--scenario clean|static|sweep|random|phases] [--seed S] [--out PREFIX] [--kill-at SLOT] [--rx-boot-ms MS]
 * Writes PREFIX.log ($FH lines from the TX node, one per slot: replayable in the dashboard), PREFIX.events.txt, PREFIX.summary.txt. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fh_link.h"
#include "mock_radio.h"
static FILE *flog, *fev;
static void sink_log(void *c, const char *s, size_t n) { (void)c; fwrite(s, 1, n, flog); }
static void sink_ev(void *c, const char *s, size_t n) { (void)c; fwrite(s, 1, n, fev); }
static uint32_t gden[16]; static uint64_t gnow_ms; static uint32_t g_first_denies;
static void guard_log(void *c, uint64_t now_ms, const char *kind, int reason, uint32_t ch, uint32_t pw) {
    (void)c; (void)pw; (void)ch;
    if (kind[0] == 'a' || (kind[0] == 't' && reason == FH_G_ALLOW)) return;                                   /* "allow": counted in the guard, not logged one by one */
    if (kind[0] == 'd') { gden[reason]++; if (g_first_denies++ >= 3u) return; }
    fprintf(fev, "guard t=%llu ms %s: %s\n", (unsigned long long)now_ms, kind, fh_guard_reason(reason));
}
static uint64_t jr = 88172645463325252ULL;
static uint32_t jrand(void) { jr ^= jr << 13; jr ^= jr >> 7; jr ^= jr << 17; return (uint32_t)(jr >> 16); }
static const char *PH[] = { "clean", "static-2", "wide-8of13", "random-4", "clean2" };
static int phase_of(const char *sc, uint64_t slot, uint64_t T) { return strcmp(sc, "phases") == 0 ? (int)((slot * 5u) / T) : 0; }
static uint16_t jam_set(const char *sc, uint64_t slot, uint64_t T) {
    uint16_t m = 0; uint32_t k;
    if (strcmp(sc, "static") == 0) return 1u << 3;
    if (strcmp(sc, "sweep") == 0) return (uint16_t)(1u << (slot % 13u));
    if (strcmp(sc, "random") == 0) return (uint16_t)(1u << (jrand() % 13u));
    if (strcmp(sc, "phases") == 0) {
        switch (phase_of(sc, slot, T)) { case 1: return 0x3; case 2: return 0xFF; case 3: for (k = 0; k < 4u;) { uint32_t c = jrand() % 13u; if (!((m >> c) & 1u)) { m = (uint16_t)(m | (1u << c)); k++; } } return m; default: return 0; }
    }
    return 0;
}
int main(int argc, char **argv) {
    uint64_t slots = 3000, seed = 1, kill_at = 0, rx_boot_ms = 1234; const char *sc = "phases", *out = "demo"; int i; char path[300];
    mr_world_t W; fh_radio_t rtx, rrx, rjam; fh_node_t tx, rx; fh_cfg_t cfg; uint8_t mk[16]; fh_keys_t jk; fh_guard_t g; fh_guard_cfg_t gc;
    uint64_t t, tend, tick = 50, last_ms = (uint64_t)-1, tok_ctr = 0, tok_ms = (uint64_t)-1; uint16_t jset = 0; uint64_t jslot = (uint64_t)-1;
    fh_stats_t snap[6]; uint8_t snapmode[6]; uint64_t jam_emit_ms = 0; int ph, curph = -1; uint32_t sw0 = 0;
    for (i = 1; i + 1 < argc; i += 2) {
        if (!strcmp(argv[i], "--slots")) slots = strtoull(argv[i + 1], 0, 10); else if (!strcmp(argv[i], "--scenario")) sc = argv[i + 1];
        else if (!strcmp(argv[i], "--seed")) seed = strtoull(argv[i + 1], 0, 10); else if (!strcmp(argv[i], "--out")) out = argv[i + 1];
        else if (!strcmp(argv[i], "--kill-at")) kill_at = strtoull(argv[i + 1], 0, 10); else if (!strcmp(argv[i], "--rx-boot-ms")) rx_boot_ms = strtoull(argv[i + 1], 0, 10);
        else { fprintf(stderr, "unknown option %s\n", argv[i]); return 2; }
    }
    snprintf(path, sizeof path, "%s.log", out); flog = fopen(path, "w"); snprintf(path, sizeof path, "%s.events.txt", out); fev = fopen(path, "w");
    if (!flog || !fev) { perror("open"); return 1; }
    for (i = 0; i < 16; i++) mk[i] = (uint8_t)(0x5A ^ (i * 17));            /* DEMO master key: published in the repo, NOT a secret */
    fh_cfg_default(&cfg); jr ^= seed * 0x9E3779B97F4A7C15ULL; if (!jr) jr = 1;
    mr_world_init(&W, seed);
    mr_add_node(&W, &rtx, 0, 0, 0); mr_add_node(&W, &rrx, 35, (int64_t)rx_boot_ms * -1000 + 2000000, 0); mr_add_node(&W, &rjam, -20, 0, 1);   /* RX: +35 ppm crystal, own boot-time offset */
    fh_node_init(&tx, 1, &rtx, &cfg, mk, 1, 2, 1, 0); fh_node_init(&rx, 0, &rrx, &cfg, mk, 2, 1, 1, 0);
    tx.sink = sink_log; tx.evsink = sink_ev; rx.evsink = sink_ev;
    fh_keys_derive(&jk, mk);
    gc.allowed_mask = FH_ALL_MASK; gc.max_power = 1; gc.max_duty_pct = 100; gc.max_burst_ms = 60000; gc.token_ttl_ms = 5000; gc.gap_reset_ms = 50;
    fh_guard_init(&g, &gc, jk.guard); g.log = guard_log;
    fprintf(fev, "build: guard hard limits duty=%u%% power=%u burst=%u ms (clamped=%d)\n", (unsigned)FH_HARD_DUTY_PCT, (unsigned)FH_HARD_POWER, (unsigned)FH_HARD_BURST_MS, g.clamped);
    tend = (slots + 1u) * cfg.slot_us;
    memset(snap, 0, sizeof snap);
    for (t = 0; t < tend; t += tick) {
        uint64_t now_ms = t / 1000u, slot = t / cfg.slot_us;
        mr_advance(&W, t);
        if (strcmp(sc, "phases") == 0 && (ph = phase_of(sc, slot, slots)) != curph && slot < slots) { if (curph >= 0) { snap[curph + 1] = tx.st; snapmode[curph + 1] = (uint8_t)tx.lad.mode; } curph = ph; if (curph == 0) snap[0] = tx.st; }
        fh_node_poll(&tx); fh_node_poll(&rx);
        /* jam node: authenticated token from the TX board once per second (modelled as a direct call, not over the radio) */
        if (now_ms / 1000u != tok_ms) { tok_ms = now_ms / 1000u; tok_ctr++; fh_guard_accept_token(&g, now_ms, tok_ctr, fh_guard_token_tag(jk.guard, tok_ctr)); }
        if (kill_at && slot == kill_at && jslot != slot) fh_guard_kill(&g, now_ms);
        if (slot != jslot) { jslot = slot; jset = (slot < slots) ? jam_set(sc, slot, slots) : 0; }
        if (jset && now_ms != last_ms) {                      /* one 1 ms noise burst per millisecond while the pattern is on */
            uint32_t c, first = 1, allowed = 0;
            for (c = 0; c < FH_NCH; c++) if ((jset >> c) & 1u) {
                if (first) { allowed = (fh_guard_request(&g, now_ms, c, 1, 1) == FH_G_ALLOW); first = 0; }
                if (allowed) { rjam.set_channel(rjam.ctx, (uint8_t)c); rjam.tx(rjam.ctx, (const uint8_t *)"\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF", 8); }
            }
            if (allowed) jam_emit_ms++;
        }
        last_ms = now_ms; gnow_ms = now_ms;
    }
    if (curph >= 0) { snap[curph + 1] = tx.st; snapmode[curph + 1] = (uint8_t)tx.lad.mode; }
    fclose(flog);
    snprintf(path, sizeof path, "%s.summary.txt", out); { FILE *fs = fopen(path, "w"); FILE *o[2]; int k;
        o[0] = stdout; o[1] = fs;
        for (k = 0; k < 2; k++) { FILE *f = o[k]; if (!f) continue;
            fprintf(f, "scenario=%s slots=%llu seed=%llu  (HOST SIMULATION - nothing here has run on an ESP32)\n", sc, (unsigned long long)slots, (unsigned long long)seed);
            if (curph >= 0) for (i = 0; i < 5; i++) { fh_stats_t a = snap[i], b = snap[i + 1]; uint32_t cs = b.crit_sent - a.crit_sent, co = b.crit_ok - a.crit_ok, sl = b.slots - a.slots, bo = b.bulk_ok - a.bulk_ok;
                fprintf(f, "  phase %-10s slots %4u  critical %3u/%3u (%.2f)  bulk goodput %.2f pkts/slot  mode at end %s\n", PH[i], sl, co, cs, cs ? (double)co / cs : 0.0, sl ? (double)bo / sl : 0.0, fh_mode_name(snapmode[i + 1])); }
            fprintf(f, "  TX: slots %u acked %u (%.1f%%) crit %u/%u missed %u | ladder switches %u final mode %s\n", tx.st.slots, tx.st.acked, 100.0 * tx.st.acked / (tx.st.slots ? tx.st.slots : 1), tx.st.crit_ok, tx.st.crit_sent, tx.st.crit_missed, tx.lad.switches, fh_mode_name(tx.lad.mode));
            fprintf(f, "  TX frame errors: crc %u mac %u | RX: frames %u crc %u mac %u dup %u time-rejected %u | RX sync %s acq %u lost %u search %u\n", tx.st.rx_bad_crc, tx.st.rx_bad_mac, rx.st.rx_frames, rx.st.rx_bad_crc, rx.st.rx_bad_mac, rx.st.rx_dup, rx.st.rx_rejected_time, fh_state_name(rx.sync.st), rx.sync.n_acq, rx.sync.n_lost, rx.sync.n_search);
            fprintf(f, "  medium: tx %u delivered %u jam-dropped %u jam-corrupted %u clean-dropped %u | jam emitted %llu ms, guard allow %u deny %u (denies: duty %u burst %u no-token %u killed %u)\n", W.st_tx, W.st_delivered, W.st_jam_drop, W.st_jam_flip, W.st_clean_drop, (unsigned long long)jam_emit_ms, g.n_allow, g.n_deny, gden[FH_G_DUTY], gden[FH_G_BURST], gden[FH_G_NOTOKEN], gden[FH_G_KILLED]);
        }
        if (fs) fclose(fs); }
    (void)sw0; (void)gnow_ms; fclose(fev); return 0;
}
