#include <string.h>
#include "fh_link.h"
#define K_PROBE 0
#define K_BULK  1
#define K_CRIT  2
#define AFH_THR_Q16 32768u        /* channel kept if a posterior sample >= 0.5 */
static void ev(fh_node_t *n, const char *s) { if (n->evsink) { n->evsink(n->ev_ctx, s, strlen(s)); n->evsink(n->ev_ctx, "\n", 1); } }
void fh_node_init(fh_node_t *n, int is_master, fh_radio_t *r, const fh_cfg_t *cfg, const uint8_t master_key[16], uint8_t id, uint8_t peer, uint32_t boot, uint64_t t0_us) {
    memset(n, 0, sizeof *n); n->is_master = is_master; n->r = r; n->cfg = *cfg; fh_keys_derive(&n->keys, master_key); n->id = id; n->peer = peer;
    fh_sync_init(&n->sync, r->now_us(r->ctx)); fh_replay_init(&n->rp); fh_ctr_init(&n->ctr, boot);
    fh_chmap_set(&n->map, FH_ALL_MASK); fh_chmap_set(&n->next_map, FH_ALL_MASK); n->t0 = t0_us;
    fh_afh_init(&n->afh, cfg->M, boot * 7u + id); fh_ladder_init(&n->lad); n->last_rssi = -95;
}
static uint8_t slot_channel(const fh_node_t *n, uint64_t slot) {
    if (fh_is_beacon_slot(&n->cfg, slot)) return fh_beacon_channel(&n->cfg, slot);
    if (!n->cfg.hop_enable) return n->cfg.fixed_ch;
    return (uint8_t)fh_hop_mapped(n->keys.hop, slot, &n->map);
}
static void send_frame(fh_node_t *n, fh_frame_t *f) {
    uint8_t w[FH_MAX_FRAME]; size_t len;
    if (fh_encode(n->keys.mac, f, w, sizeof w, &len) == FH_OK) n->r->tx(n->r->ctx, w, len);
}
/* ---------------- master ---------------- */
static void m_begin_slot(fh_node_t *n, uint64_t slot) {
    n->cur_slot = slot; n->slot_valid = 1; n->done = 0; n->did_tx = 0; n->got_ok = 0; n->st.slots++;
    if (n->cfg.beacon_period && slot % n->cfg.beacon_period == 0) {       /* superframe boundary: apply the announced map, announce the next */
        n->map = n->next_map;
        fh_chmap_set(&n->next_map, n->lad.mode == FH_M_ADAPT ? fh_afh_pick_map(&n->afh, AFH_THR_Q16, FH_NCH / 2u) : FH_ALL_MASK);
    }
    n->cur_ch = slot_channel(n, slot); n->r->set_channel(n->r->ctx, n->cur_ch);
    if (n->cfg.crit_period && slot % n->cfg.crit_period == 0) {
        if (n->crit_pending) n->st.crit_missed++;
        n->crit_pending = 1; n->crit_slot0 = slot; n->crit_tries_used = 0; n->crit_id++; n->st.crit_sent++;
    }
    if (n->crit_pending && n->crit_tries_used < fh_crit_tries(n->lad.mode) && slot - n->crit_slot0 < n->cfg.crit_deadline) {
        n->cur_kind = K_CRIT; n->cur_attempt = n->crit_tries_used++;
    } else if (n->lad.mode == FH_M_SURVIVAL) { n->cur_kind = K_PROBE; n->cur_attempt = 0; }
    else { n->cur_kind = K_BULK; n->cur_attempt = 0; n->bulk_id++; }
}
static void m_tx(fh_node_t *n) {
    fh_frame_t f; uint32_t id = n->cur_kind == K_CRIT ? n->crit_id : n->bulk_id;
    memset(&f, 0, sizeof f);
    f.type = fh_is_beacon_slot(&n->cfg, n->cur_slot) ? FH_T_BEACON : FH_T_DATA; f.src = n->id; f.mode = (uint8_t)n->lad.mode; f.retry = (uint8_t)(n->cur_attempt > 3u ? 3u : n->cur_attempt);
    f.slot = (uint32_t)n->cur_slot; f.ctr = fh_ctr_next(&n->ctr); f.map = n->next_map.mask; f.plen = 6;
    f.payload[0] = (uint8_t)n->cur_kind; f.payload[1] = (uint8_t)id; f.payload[2] = (uint8_t)(id >> 8); f.payload[3] = (uint8_t)n->cur_attempt;
    f.payload[4] = (uint8_t)n->map.mask; f.payload[5] = (uint8_t)(n->map.mask >> 8);          /* the map in force now, so a late joiner is not lost until the next superframe */
    n->pend_ctr = f.ctr; send_frame(n, &f); n->did_tx = 1; n->st.tx++;
    if (n->cur_kind == K_BULK) n->st.bulk_tx++; else if (n->cur_kind == K_PROBE) n->st.probe_tx++;
}
static void m_collect(fh_node_t *n) {
    uint8_t b[FH_MAX_FRAME + 4]; size_t len; fh_rxinfo_t info; fh_frame_t f; int rc;
    while (n->r->rx(n->r->ctx, b, sizeof b, &len, &info)) {
        rc = fh_decode(n->keys.mac, b, len, &f);
        if (rc == FH_E_CRC) { n->st.rx_bad_crc++; continue; } if (rc == FH_E_MAC) { n->st.rx_bad_mac++; continue; } if (rc != FH_OK) { n->st.rx_other_err++; continue; }
        if (f.type != FH_T_ACK || f.src != n->peer || f.plen < 4u) continue;
        { uint32_t c = (uint32_t)f.payload[0] | ((uint32_t)f.payload[1] << 8) | ((uint32_t)f.payload[2] << 16) | ((uint32_t)f.payload[3] << 24);
          if (c != n->pend_ctr) continue; }
        if (fh_replay_check_and_update(&n->rp, f.src, FH_T_ACK, f.ctr) != FH_RP_NEW) { n->st.rx_dup++; continue; }
        n->got_ok = 1; n->last_rssi = info.rssi_dbm; n->st.acks_sent++;
    }
}
static void m_finish(fh_node_t *n) {
    char line[48], txt[160]; size_t l; fh_ladder_event_t e; int ok = n->got_ok; int32_t rssi = ok ? n->last_rssi : n->r->rssi(n->r->ctx);
    l = fh_serial_encode(line, sizeof line, (uint32_t)n->cur_slot, n->cur_ch, ok, n->cur_kind == K_CRIT ? n->cur_attempt : 0u, rssi);
    if (l && n->sink) n->sink(n->sink_ctx, line, l);
    if (ok) { n->st.acked++; if (n->cur_kind == K_CRIT) { n->st.crit_ok++; n->crit_pending = 0; } else if (n->cur_kind == K_BULK) n->st.bulk_ok++; }
    fh_afh_update(&n->afh, n->cur_ch, ok);
    if (fh_ladder_step(&n->lad, n->cur_slot, ok, n->cur_ch, fh_afh_avoiding(&n->afh), &e)) { if (fh_ladder_event_text(&e, txt, sizeof txt)) ev(n, txt); }
    n->done = 1;
}
static void master_poll(fh_node_t *n) {
    uint64_t now = n->r->now_us(n->r->ctx), rel, slot, ph;
    if (now < n->t0) return;
    rel = now - n->t0; slot = rel / n->cfg.slot_us; ph = rel % n->cfg.slot_us;
    if (!n->slot_valid || slot != n->cur_slot) { if (n->slot_valid && !n->done) { m_collect(n); m_finish(n); } m_begin_slot(n, slot); }
    if (!n->did_tx && ph >= n->cfg.tx_off_us) m_tx(n);
    if (n->did_tx && !n->done && ph >= n->cfg.ack_end_us) { m_collect(n); m_finish(n); }
}
/* ---------------- follower ---------------- */
static void f_handle(fh_node_t *n, const uint8_t *b, size_t len, const fh_rxinfo_t *info, int *newly_acquired) {
    fh_frame_t f; int rc = fh_decode(n->keys.mac, b, len, &f), was_search; uint64_t ref, slot; uint32_t cur_ctr;
    n->st.rx_frames++;
    if (rc == FH_E_CRC) { n->st.rx_bad_crc++; return; } if (rc == FH_E_MAC) { n->st.rx_bad_mac++; return; } if (rc != FH_OK) { n->st.rx_other_err++; return; }
    if (f.src != n->peer || (f.type != FH_T_DATA && f.type != FH_T_BEACON) || f.plen < 6u) return;
    if (fh_replay_check_and_update(&n->rp, f.src, f.type, f.ctr) != FH_RP_NEW) { n->st.rx_dup++; return; }
    was_search = (n->sync.st == FH_ST_SEARCH || n->sync.st == FH_ST_LOST || !n->sync.has_anchor);
    ref = n->sync.has_anchor ? n->sync.anchor_slot : n->sync.floor_slot;
    slot = fh_slot_extend(ref, f.slot);
    if (!fh_sync_on_packet(&n->sync, &n->cfg, f.type == FH_T_BEACON, slot, info->rx_ts_us)) { n->st.rx_rejected_time++; return; }
    fh_chmap_set(&n->next_map, f.map); fh_chmap_set(&n->map, (uint16_t)((uint16_t)f.payload[4] | (uint16_t)((uint16_t)f.payload[5] << 8)));
    n->ack_pending = 1; n->ack_ctr = f.ctr; n->ack_slot = slot; n->got_ok = 1; cur_ctr = f.ctr; (void)cur_ctr;
    if (was_search) { *newly_acquired = 1; n->slot_valid = 0; }
}
static void f_drain(fh_node_t *n, int *acq) {
    uint8_t b[FH_MAX_FRAME + 4]; size_t len; fh_rxinfo_t info;
    while (n->r->rx(n->r->ctx, b, sizeof b, &len, &info)) f_handle(n, b, len, &info, acq);
}
static void follower_poll(fh_node_t *n) {
    uint64_t now = n->r->now_us(n->r->ctx); int acq = 0;
    if (n->sync.st == FH_ST_SEARCH || n->sync.st == FH_ST_LOST || !n->sync.has_anchor) {
        uint8_t ch = fh_sync_search_channel(&n->sync, &n->cfg, now);
        if (!n->slot_valid || ch != n->cur_ch) { n->r->set_channel(n->r->ctx, ch); n->cur_ch = ch; }
        n->slot_valid = 0; f_drain(n, &acq);
        if (!acq) return;
        ev(n, "follower: acquired beacon");
        now = n->r->now_us(n->r->ctx);
    }
    {
        uint64_t cur, ss, ph, k;
        if (now < n->sync.anchor_us) return;
        cur = n->sync.anchor_slot + (now - n->sync.anchor_us) / n->cfg.slot_us;
        if (!n->slot_valid || cur != n->cur_slot) {
            if (n->slot_valid) {
                uint64_t gap = cur - n->cur_slot;                        /* slots that ended without an accepted packet; the one just ended counts if !got_ok */
                if (!n->got_ok) fh_sync_on_miss(&n->sync, &n->cfg, now);
                for (k = 1; k < gap && k < 8u; k++) fh_sync_on_miss(&n->sync, &n->cfg, now);
                if (n->sync.st == FH_ST_LOST) { ev(n, "follower: lost sync"); return; }
                if (n->sync.st == FH_ST_SEARCH) return;
                if (n->cfg.beacon_period && cur / n->cfg.beacon_period != n->cur_slot / n->cfg.beacon_period) n->map = n->next_map;
            }
            n->cur_slot = cur; n->slot_valid = 1; n->st.slots++; n->ack_pending = (n->got_ok && n->ack_slot == cur) ? n->ack_pending : 0;
            if (!(n->got_ok && n->ack_slot == cur)) n->got_ok = 0;
            n->cur_ch = slot_channel(n, cur); n->r->set_channel(n->r->ctx, n->cur_ch);
        }
        f_drain(n, &acq);
        ss = fh_sync_slot_start(&n->sync, &n->cfg, n->cur_slot); ph = now - ss;
        if (n->ack_pending && ph >= n->cfg.ack_off_us) {
            fh_frame_t f; memset(&f, 0, sizeof f);
            f.type = FH_T_ACK; f.src = n->id; f.mode = 0; f.retry = 0; f.slot = (uint32_t)n->ack_slot; f.ctr = fh_ctr_next(&n->ctr); f.map = 0; f.plen = 4;
            f.payload[0] = (uint8_t)n->ack_ctr; f.payload[1] = (uint8_t)(n->ack_ctr >> 8); f.payload[2] = (uint8_t)(n->ack_ctr >> 16); f.payload[3] = (uint8_t)(n->ack_ctr >> 24);
            send_frame(n, &f); n->ack_pending = 0; n->st.acks_sent++;
        }
    }
}
void fh_node_poll(fh_node_t *n) { if (n->is_master) master_poll(n); else follower_poll(n); }
