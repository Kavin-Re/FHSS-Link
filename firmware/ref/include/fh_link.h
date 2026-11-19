/* Link layer glue: master (TX) and follower (RX) nodes built only on fh_radio_t + fh.h. Poll-driven, no clock reads outside radio->now_us.
 * HOST-TESTED ONLY. Portable C99, no allocation. */
#ifndef FH_LINK_H
#define FH_LINK_H
#include "fh.h"
#include "fh_radio.h"
typedef struct {
    uint32_t slots, tx, acked, crit_sent, crit_ok, crit_missed, bulk_tx, bulk_ok, probe_tx;
    uint32_t rx_frames, rx_bad_crc, rx_bad_mac, rx_other_err, rx_dup, rx_rejected_time, acks_sent;
} fh_stats_t;
typedef struct fh_node {
    int is_master; fh_radio_t *r; fh_cfg_t cfg; fh_keys_t keys; uint8_t id, peer;
    fh_sync_t sync; fh_replay_t rp; fh_ctr_t ctr; fh_chmap_t map, next_map;
    uint64_t t0; uint64_t cur_slot; int slot_valid, done, did_tx, got_ok; uint8_t cur_ch;
    fh_afh_t afh; fh_ladder_t lad;
    uint32_t pend_ctr, crit_tries_used, crit_id, bulk_id; uint64_t crit_slot0; int crit_pending, cur_kind; uint32_t cur_attempt;
    int ack_pending; uint32_t ack_ctr; uint64_t ack_slot; int32_t last_rssi;
    fh_sink_fn sink, evsink; void *sink_ctx, *ev_ctx;
    fh_stats_t st;
} fh_node_t;
void fh_node_init(fh_node_t *n, int is_master, fh_radio_t *r, const fh_cfg_t *cfg, const uint8_t master_key[16], uint8_t id, uint8_t peer, uint32_t boot, uint64_t t0_us);
void fh_node_poll(fh_node_t *n);
#endif
