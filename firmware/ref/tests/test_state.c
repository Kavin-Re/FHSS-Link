#include <string.h>
#include "fh.h"
#define C(x) do { chk((x) ? 1 : 0, #x, __LINE__); } while (0)
static void t_sync(void(*chk)(int, const char *, int)) {
    fh_cfg_t c; fh_sync_t s; uint64_t slot, t; int i;
    fh_cfg_default(&c); fh_sync_init(&s, 0);
    C(fh_is_beacon_slot(&c, 0) && fh_is_beacon_slot(&c, 16) && !fh_is_beacon_slot(&c, 5));
    C(fh_beacon_channel(&c, 0) == 1 && fh_beacon_channel(&c, 16) == 6 && fh_beacon_channel(&c, 32) == 11 && fh_beacon_channel(&c, 48) == 1);
    /* search dwell cycles through the rendezvous list */
    C(fh_sync_search_channel(&s, &c, 0) == 1); C(fh_sync_search_channel(&s, &c, (uint64_t)(c.nrdv * c.beacon_period + 1u) * c.slot_us) == 6);
    C(fh_sync_search_channel(&s, &c, (uint64_t)2 * (c.nrdv * c.beacon_period + 1u) * c.slot_us + 5) == 11);
    /* data packets cannot start synchronisation; a beacon can */
    C(fh_sync_on_packet(&s, &c, 0, 100, 5000000) == 0);
    C(fh_sync_on_packet(&s, &c, 1, 112, 5000000) == 1 && s.st == FH_ST_SYNC && s.anchor_us == 5000000 - c.tx_off_us);
    /* slot timing prediction */
    C(fh_sync_slot_start(&s, &c, 114) == s.anchor_us + 2u * c.slot_us);
    /* consistent packet confirms -> TRACK; one far outside the guard is rejected */
    C(fh_sync_on_packet(&s, &c, 0, 113, 5000000 + c.slot_us + 300) == 1 && s.st == FH_ST_TRACK);
    C(fh_sync_on_packet(&s, &c, 0, 114, 5000000 + 2u * c.slot_us + 9000) == 0);
    /* a recorded beacon replayed later: old slot number is refused (floor) even after losing sync */
    for (i = 0; i < 8; i++) fh_sync_on_miss(&s, &c, 0);
    C(s.st == FH_ST_LOST && s.n_lost == 1);
    C(fh_sync_on_packet(&s, &c, 1, 112, 9000000) == 0);       /* replayed old beacon */
    C(fh_sync_on_packet(&s, &c, 1, 128, 9000000) == 1 && s.st == FH_ST_SYNC);
    /* SYNC with misses falls back to SEARCH */
    for (i = 0; i < (int)c.sync_miss_max; i++) fh_sync_on_miss(&s, &c, 9000000);
    C(s.st == FH_ST_SEARCH && !s.has_anchor);
    /* guard grows with missed slots (drift allowance) */
    { fh_sync_t q; fh_sync_init(&q, 0); q.miss = 0; t = fh_sync_guard(&q, &c); q.miss = 20; C(fh_sync_guard(&q, &c) > t); }
    /* slot extension across the 32-bit wrap */
    slot = fh_slot_extend(0xFFFFFFF0ULL, 0x10u); C(slot == 0x100000010ULL);
}
static void t_afh(void(*chk)(int, const char *, int)) {
    fh_afh_t a; uint32_t i, ch, bad_used = 0, n = 0; uint16_t m; fh_chmap_t cm;
    fh_afh_init(&a, 13, 5); C(fh_afh_mean(&a, 0) == 32768u); C(fh_afh_avoiding(&a));   /* prior mean 0.5 < 0.6, same as sim/adaptive.py Thompson at start */
    for (i = 0; i < 3000; i++) { ch = i % 13u; fh_afh_update(&a, ch, ch >= 2u ? ((i * 2654435761u) % 100u) >= 1u : ((i * 2654435761u) % 100u) >= 95u); }
    C(fh_afh_mean(&a, 0) < 20000u && fh_afh_mean(&a, 1) < 20000u && fh_afh_mean(&a, 5) > 55000u); C(fh_afh_avoiding(&a));
    for (i = 0; i < 200; i++) { m = fh_afh_pick_map(&a, 32768u, 6u); fh_chmap_set(&cm, m); if ((m & 3u) != 0u) bad_used++; n += cm.n; }
    C(bad_used < 20u);                                       /* jammed channels 0 and 1 are almost always out of the map */
    C(n / 200u >= 6u && n / 200u <= 13u);
    for (i = 0; i < 100; i++) { uint32_t sv = fh_afh_sample(&a, 5); C(sv <= FH_Q); }
}
static void t_ladder(void(*chk)(int, const char *, int)) {
    fh_ladder_t l; fh_ladder_event_t e; char txt[200]; uint64_t s = 0; int i, sw = 0;
    fh_ladder_init(&l);
    for (i = 0; i < 200; i++) C(fh_ladder_step(&l, s++, 1, 3, 0, &e) == 0);           /* clean: stays NORMAL */
    for (i = 0; i < 30 && l.mode == 0; i++) sw += fh_ladder_step(&l, s++, 0, 4, 0, &e); /* all lost: upgrades at once */
    C(sw == 1 && l.mode >= FH_M_ADAPT);
    C(fh_ladder_event_text(&e, txt, sizeof txt) > 10u && strstr(txt, "NORMAL -> ") != NULL && strstr(txt, "most-hit channels [4,") != NULL);
    for (i = 0; i < 400 && l.mode != FH_M_SURVIVAL; i++) fh_ladder_step(&l, s++, 0, 4, 0, &e);
    C(l.mode == FH_M_SURVIVAL);
    /* hysteresis: no downgrade until 100 consecutive slots with want < mode; reference point = first slot whose window loss is below the SURVIVAL threshold (55%) */
    { int low_at = -1, down_at = -1; for (i = 0; i < 400; i++) { int m0 = l.mode; fh_ladder_step(&l, s++, 1, 4, 0, &e); if (low_at < 0 && l.nlost * 100u < 55u * l.nh) low_at = i; if (l.mode < m0 && down_at < 0) down_at = i; }
      C(low_at >= 0 && down_at >= 0 && down_at - low_at >= 99 && down_at - low_at <= 105); C(l.mode == FH_M_NORMAL); }
    /* ADAPT does not step down while the learner still avoids channels */
    fh_ladder_init(&l); l.mode = FH_M_ADAPT; for (i = 0; i < 500; i++) fh_ladder_step(&l, s++, 1, 1, 1, &e); C(l.mode == FH_M_ADAPT);
    for (i = 0; i < 150; i++) fh_ladder_step(&l, s++, 1, 1, 0, &e);
    C(l.mode == FH_M_NORMAL);
    C(fh_crit_tries(0) == 1 && fh_crit_tries(1) == 3 && fh_crit_tries(2) == 5 && fh_crit_tries(3) == 10);
}
static void t_guard(void(*chk)(int, const char *, int)) {
    uint8_t key[16]; fh_guard_t g; fh_guard_cfg_t c; uint64_t t; int i, allowed = 0;
    for (i = 0; i < 16; i++) key[i] = (uint8_t)(i + 9);
    c.allowed_mask = 0x0038; c.max_power = 5; c.max_duty_pct = 90; c.max_burst_ms = 999999; c.token_ttl_ms = 5000; c.gap_reset_ms = 50;
    fh_guard_init(&g, &c, key);
    C(g.cfg.max_power <= FH_HARD_POWER && g.cfg.max_duty_pct <= FH_HARD_DUTY_PCT && g.cfg.max_burst_ms <= FH_HARD_BURST_MS);   /* clamped to the compile-time caps */
#ifndef FH_SIM_UNSAFE_LIMITS
    C(g.clamped == 1 && g.cfg.max_duty_pct == 10u && g.cfg.max_power == 1u && g.cfg.max_burst_ms == 2000u);
#endif
    C(fh_guard_request(&g, 100, 3, 0, 10) == FH_G_NOTOKEN);                                     /* never received a token */
    C(fh_guard_accept_token(&g, 100, 1, fh_guard_token_tag(key, 1) ^ 1u) == 0);                  /* bad tag */
    C(fh_guard_accept_token(&g, 100, 1, fh_guard_token_tag(key, 1)) == 1);
    C(fh_guard_accept_token(&g, 110, 1, fh_guard_token_tag(key, 1)) == 0);                       /* replayed token */
    C(fh_guard_request(&g, 200, 7, 0, 10) == FH_G_CHANNEL);                                     /* channel outside own-link set */
    C(fh_guard_request(&g, 200, 3, g.cfg.max_power + 1u, 10) == FH_G_POWER);
    C(fh_guard_request(&g, 200, 3, 0, 10) == FH_G_ALLOW);
    C(fh_guard_request(&g, 5200, 3, 0, 10) == FH_G_NOTOKEN);                                    /* token expired (5100 ms after accept) */
    C(fh_guard_accept_token(&g, 5300, 2, fh_guard_token_tag(key, 2)) == 1);
    /* duty cycle: with the hard cap the node can be on for at most duty% of any 10 s window */
    for (t = 6000; t < 16000; t += 20) { if (fh_guard_request(&g, t, 4, 0, 10) == FH_G_ALLOW) allowed++; if (t % 1000u == 0u) fh_guard_accept_token(&g, t, 100u + t / 1000u, fh_guard_token_tag(key, 100u + t / 1000u)); }
    C((uint64_t)allowed * 10u * 100u <= (uint64_t)g.cfg.max_duty_pct * FH_GUARD_WINDOW_MS + 10u * 100u);
    C(allowed > 0);
    fh_guard_kill(&g, 16000); C(fh_guard_request(&g, 16001, 3, 0, 1) == FH_G_KILLED);
    /* continuous burst limit (use a fresh guard with a short burst cap and a large duty cap only where the build allows) */
    { fh_guard_t h; fh_guard_cfg_t d = c; int hit = 0; d.max_burst_ms = 50; d.max_duty_pct = 100; fh_guard_init(&h, &d, key); fh_guard_accept_token(&h, 0, 1, fh_guard_token_tag(key, 1));
      for (t = 10; t < 400; t++) { int r = fh_guard_request(&h, t, 3, 0, 1); if (r == FH_G_BURST) hit = 1; }
      C(hit || h.cfg.max_duty_pct < 100u);
      C(fh_guard_reason(FH_G_DUTY) != NULL && fh_guard_request(&h, 500, 99, 0, 1) == FH_G_ARG); }
}
void test_state(void(*chk)(int, const char *, int)) { t_sync(chk); t_afh(chk); t_ladder(chk); t_guard(chk); }
