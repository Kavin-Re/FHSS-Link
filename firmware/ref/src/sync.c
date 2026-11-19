#include "fh.h"
void fh_cfg_default(fh_cfg_t *c) {
    /* ALL timing values below are design assumptions, UNMEASURED on hardware (docs/BRINGUP_28OCT.md). slot 20 ms is the figure in firmware/README.md. */
    c->slot_us = 20000u; c->tx_off_us = 2000u; c->ack_off_us = 8000u; c->ack_end_us = 14000u; c->pre_us = 500u; c->guard_us = 1500u; c->drift_ppm = 40u;
    c->beacon_period = 16u; c->nrdv = 3u; c->rdv[0] = 1u; c->rdv[1] = 6u; c->rdv[2] = 11u; c->rdv[3] = 0u;   /* logical 1/6/11 = Wi-Fi ch 2/7/12 under the HAL's +1 map; see bring-up doc */
    c->miss_lost = 8u; c->sync_miss_max = 3u; c->sync_confirm = 2u; c->lost_max = 50u;
    c->M = FH_NCH; c->hop_enable = 1u; c->fixed_ch = 0u; c->crit_period = 10u; c->crit_deadline = 10u;
}
const char *fh_state_name(fh_state_t s) { static const char *n[] = { "SEARCH", "SYNC", "TRACK", "LOST" }; return ((unsigned)s < 4u) ? n[s] : "?"; }
void fh_sync_init(fh_sync_t *s, uint64_t now_us) {
    s->st = FH_ST_SEARCH; s->has_anchor = 0; s->anchor_slot = 0; s->anchor_us = 0; s->miss = 0; s->confirm = 0; s->floor_slot = 0; s->has_floor = 0;
    s->rdv_idx = 0; s->dwell_start_us = now_us; s->n_acq = s->n_lost = s->n_search = s->n_rej = 0;
}
uint64_t fh_sync_slot_start(const fh_sync_t *s, const fh_cfg_t *c, uint64_t slot) {
    return (slot >= s->anchor_slot) ? s->anchor_us + (slot - s->anchor_slot) * c->slot_us : s->anchor_us - (s->anchor_slot - slot) * c->slot_us;
}
uint32_t fh_sync_guard(const fh_sync_t *s, const fh_cfg_t *c) {
    /* static guard + worst-case relative drift (2 x drift_ppm, both crystals) accumulated over the slots since the last good packet */
    uint64_t slots = (uint64_t)s->miss + 1u, acc = (2u * (uint64_t)c->drift_ppm * (uint64_t)c->slot_us * slots + 999999u) / 1000000u;
    return c->guard_us + (uint32_t)acc;
}
int fh_is_beacon_slot(const fh_cfg_t *c, uint64_t slot) { return c->beacon_period != 0u && (slot % c->beacon_period) == 0u; }
uint8_t fh_beacon_channel(const fh_cfg_t *c, uint64_t slot) {
    uint64_t k; if (c->nrdv == 0u) return 0u;
    k = (c->beacon_period ? slot / c->beacon_period : 0u) % c->nrdv; return c->rdv[k];
}
int fh_sync_on_packet(fh_sync_t *s, const fh_cfg_t *c, int is_beacon, uint64_t slot, uint64_t t_rx_us) {
    int64_t err; uint64_t exp_rx; uint32_t g;
    if (t_rx_us < c->tx_off_us) return 0;
    if (s->st == FH_ST_SEARCH || s->st == FH_ST_LOST || !s->has_anchor) {
        /* acquisition: beacons only, strictly newer than any beacon accepted before (a recorded beacon replayed later has an old slot) */
        if (!is_beacon) { s->n_rej++; return 0; }
        if (s->has_floor && slot <= s->floor_slot) { s->n_rej++; return 0; }
        s->anchor_slot = slot; s->anchor_us = t_rx_us - c->tx_off_us; s->has_anchor = 1; s->floor_slot = slot; s->has_floor = 1;
        s->st = FH_ST_SYNC; s->confirm = 1u; s->miss = 0; s->n_acq++;
        return 1;
    }
    /* SYNC or TRACK: the packet must land inside the guard window predicted from the anchor */
    exp_rx = fh_sync_slot_start(s, c, slot) + c->tx_off_us; g = fh_sync_guard(s, c);
    err = (int64_t)t_rx_us - (int64_t)exp_rx;
    if (err < -(int64_t)g || err > (int64_t)g || slot + 1u < s->anchor_slot || (is_beacon && s->has_floor && slot <= s->floor_slot && slot != s->anchor_slot)) { s->n_rej++; return 0; }
    if (is_beacon && (!s->has_floor || slot > s->floor_slot)) { s->floor_slot = slot; s->has_floor = 1; }
    s->anchor_slot = slot; s->anchor_us = t_rx_us - c->tx_off_us; s->miss = 0;
    if (s->st == FH_ST_SYNC) { s->confirm++; if (s->confirm >= c->sync_confirm) s->st = FH_ST_TRACK; }
    return 1;
}
void fh_sync_on_miss(fh_sync_t *s, const fh_cfg_t *c, uint64_t now_us) {
    if (s->st == FH_ST_SEARCH) return;
    s->miss++;
    if (s->st == FH_ST_SYNC) { if (s->miss >= c->sync_miss_max) { s->st = FH_ST_SEARCH; s->has_anchor = 0; s->confirm = 0; s->rdv_idx = 0; s->dwell_start_us = now_us; s->n_search++; } }
    else if (s->st == FH_ST_TRACK) { if (s->miss >= c->miss_lost) { s->st = FH_ST_LOST; s->n_lost++; } }
    else if (s->st == FH_ST_LOST) { if (s->miss >= c->lost_max) s->has_anchor = 0; }
}
uint8_t fh_sync_search_channel(fh_sync_t *s, const fh_cfg_t *c, uint64_t now_us) {
    uint64_t dwell;
    if (c->nrdv == 0u) return 0u;
    if (s->st == FH_ST_LOST) { s->st = FH_ST_SEARCH; s->rdv_idx = 0; s->dwell_start_us = now_us; s->n_search++; }
    /* beacon k is on rdv[k % nrdv] once per beacon_period slots, so a listener must stay nrdv beacon periods (+1 slot) on a channel to be sure to hear one */
    dwell = ((uint64_t)c->nrdv * c->beacon_period + 1u) * c->slot_us;
    if (now_us < s->dwell_start_us) s->dwell_start_us = now_us;                 /* clock went backwards (caller bug / wrap): restart the dwell, never loop */
    { uint64_t steps = (now_us - s->dwell_start_us) / dwell; s->dwell_start_us += steps * dwell; s->rdv_idx = (uint8_t)((s->rdv_idx + steps % c->nrdv) % c->nrdv); }
    return c->rdv[s->rdv_idx];
}
