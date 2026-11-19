#include "fh.h"
#include "fh_fmt.h"
const char *fh_guard_reason(int r) {
    static const char *n[] = { "ok", "kill switch active", "no valid token (expired or never received)", "channel not in the own-link set", "power level above cap",
                               "duty cycle would exceed limit", "continuous burst limit reached", "decision log full (fail safe)", "bad argument" };
    return (r >= 0 && r <= FH_G_ARG) ? n[r] : "?";
}
void fh_guard_init(fh_guard_t *g, const fh_guard_cfg_t *cfg, const uint8_t key[16]) {
    unsigned i; g->cfg = *cfg; g->clamped = 0;
    /* the limits can only be tightened, never loosened beyond the compile-time hard caps */
    if (g->cfg.max_duty_pct > FH_HARD_DUTY_PCT) { g->cfg.max_duty_pct = FH_HARD_DUTY_PCT; g->clamped = 1; }
    if (g->cfg.max_power > FH_HARD_POWER) { g->cfg.max_power = FH_HARD_POWER; g->clamped = 1; }
    if (g->cfg.max_burst_ms > FH_HARD_BURST_MS) { g->cfg.max_burst_ms = FH_HARD_BURST_MS; g->clamped = 1; }
    g->cfg.allowed_mask = (uint16_t)(g->cfg.allowed_mask & FH_ALL_MASK);
    for (i = 0; i < 16; i++) g->key[i] = key[i];
    g->has_ctr = 0; g->last_ctr = 0; g->has_token = 0; g->token_ms = 0; g->killed = 0; g->burst_ms = 0; g->last_end_ms = 0;
    g->head = g->count = 0; g->log = 0; g->log_ctx = 0; g->n_allow = g->n_deny = 0;
}
uint64_t fh_guard_token_tag(const uint8_t key[16], uint64_t ctr) {
    uint8_t b[9]; unsigned i; for (i = 0; i < 8; i++) b[i] = (uint8_t)(ctr >> (8u * i)); b[8] = 0x47;     /* 'G' domain byte */
    return fh_siphash24(key, b, 9);
}
static void glog(fh_guard_t *g, uint64_t now, const char *kind, int reason, uint32_t ch, uint32_t pw) { if (g->log) g->log(g->log_ctx, now, kind, reason, ch, pw); }
int fh_guard_accept_token(fh_guard_t *g, uint64_t now_ms, uint64_t ctr, uint64_t tag) {
    uint64_t exp = fh_guard_token_tag(g->key, ctr), d = exp ^ tag;
    int ok = (!g->has_ctr || ctr > g->last_ctr) && d == 0u;
    if (ok) { g->has_ctr = 1; g->last_ctr = ctr; g->has_token = 1; g->token_ms = now_ms; }
    glog(g, now_ms, "token", ok ? FH_G_ALLOW : FH_G_NOTOKEN, 0, 0); return ok;
}
void fh_guard_kill(fh_guard_t *g, uint64_t now_ms) { g->killed = 1; glog(g, now_ms, "kill", FH_G_KILLED, 0, 0); }
static uint32_t prune_sum(fh_guard_t *g, uint64_t now) {
    /* entries are ordered oldest..newest; drop those with now - t >= window */
    uint32_t sum = 0, i, idx, keep = 0;
    for (i = 0; i < g->count; i++) { idx = (g->head + FH_GUARD_RING - g->count + i) % FH_GUARD_RING; if (now - g->t[idx] < FH_GUARD_WINDOW_MS) { sum += g->d[idx]; keep++; } }
    g->count = keep; return sum;
}
int fh_guard_request(fh_guard_t *g, uint64_t now_ms, uint32_t ch, uint32_t power, uint32_t dt_ms) {
    int why = FH_G_ALLOW; uint32_t sum;
    if (dt_ms == 0u || ch >= FH_NCH_MAX) why = FH_G_ARG;
    else if (g->killed) why = FH_G_KILLED;
    else if (!g->has_token || now_ms < g->token_ms || now_ms - g->token_ms > g->cfg.token_ttl_ms) why = FH_G_NOTOKEN;
    else if (!((g->cfg.allowed_mask >> ch) & 1u)) why = FH_G_CHANNEL;
    else if (power > g->cfg.max_power) why = FH_G_POWER;
    else {
        uint32_t burst = g->burst_ms;
        if (g->last_end_ms != 0u || g->burst_ms != 0u) { if (now_ms >= g->last_end_ms && now_ms - g->last_end_ms > g->cfg.gap_reset_ms) burst = 0u; }
        sum = prune_sum(g, now_ms);
        if ((uint64_t)(sum + dt_ms) * 100u > (uint64_t)g->cfg.max_duty_pct * FH_GUARD_WINDOW_MS) why = FH_G_DUTY;
        else if ((uint64_t)burst + dt_ms > g->cfg.max_burst_ms) why = FH_G_BURST;
        else {
            uint32_t last = (g->head + FH_GUARD_RING - 1u) % FH_GUARD_RING;
            if (g->count > 0u && g->t[last] + g->d[last] == now_ms) g->d[last] += dt_ms;        /* contiguous emission: merge, keeps the ring small */
            else if (g->count >= FH_GUARD_RING) why = FH_G_LOGFULL;
            else { g->t[g->head] = now_ms; g->d[g->head] = dt_ms; g->head = (g->head + 1u) % FH_GUARD_RING; g->count++; }
            if (why == FH_G_ALLOW) { g->burst_ms = burst + dt_ms; g->last_end_ms = now_ms + dt_ms; }
        }
    }
    if (why != FH_G_ALLOW) { g->burst_ms = 0u; g->n_deny++; glog(g, now_ms, "deny", why, ch, power); return why; }
    g->n_allow++; glog(g, now_ms, "allow", FH_G_ALLOW, ch, power); return FH_G_ALLOW;
}
