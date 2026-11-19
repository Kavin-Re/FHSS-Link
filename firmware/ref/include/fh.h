/* FHSS-Link firmware reference core. Portable C99, no dynamic allocation, no libc beyond <stdint.h>/<stddef.h>/<string.h>.
 * HOST-TESTED ONLY: nothing here has run on an ESP32. Style, SipHash and replay window follow LifeLine-Mesh/c (copied and renamed).
 * Time is always passed in as an argument (microseconds or milliseconds); no module reads a clock. */
#ifndef FH_H
#define FH_H
#include <stddef.h>
#include <stdint.h>

#define FH_VER          1u
#define FH_NCH          13u          /* default channel count (Wi-Fi channels 1..13 mapped to logical 0..12 by the HAL) */
#define FH_NCH_MAX      16u
#define FH_ALL_MASK     ((uint16_t)((1u << FH_NCH) - 1u))
#define FH_SLOT_BITS    56u
#define FH_SLOT_MASK    ((((uint64_t)1) << FH_SLOT_BITS) - 1u)
#define FH_RDV_MAX      4u

enum { FH_OK = 0, FH_E_LEN, FH_E_CRC, FH_E_VER, FH_E_TYPE, FH_E_RSVD, FH_E_PLEN, FH_E_MAC, FH_E_ARG, FH_E_BUSY, FH_E_REPLAY, FH_E_RANGE, FH_E_FORMAT };

/* ---------- primitives ---------- */
uint64_t fh_siphash24(const uint8_t key[16], const uint8_t *in, size_t len);
uint16_t fh_crc16(const uint8_t *data, size_t len);      /* CRC-16/CCITT-FALSE, check("123456789") = 0x29B1 */
uint8_t  fh_crc8(const uint8_t *data, size_t len);       /* poly 0x07 init 0, check("123456789") = 0xF4 */

/* key hierarchy: three independent 128-bit keys derived from one master with SipHash-2-4 in counter mode (domain-separated labels) */
typedef struct { uint8_t hop[16]; uint8_t mac[16]; uint8_t guard[16]; } fh_keys_t;
void fh_derive(uint8_t out[16], const uint8_t master[16], const char label[4]);
void fh_keys_derive(fh_keys_t *k, const uint8_t master[16]);

/* ---------- keyed hop schedule (bit-exact with rtl/hop_engine/model/hop_model.py: hop()) ---------- */
typedef struct { uint32_t M; uint32_t RW; uint32_t NCH; } fh_hopcfg_t;   /* defaults M=13 RW=32 NCH=2; RW*NCH <= 64, RW <= 32 */
uint64_t fh_hop_digest(const uint8_t key[16], uint64_t slot, uint8_t retry);   /* SipHash-2-4 of msg64 = retry<<56 | slot(56) */
int      fh_hop_cfg(const fh_hopcfg_t *c, const uint8_t key[16], uint64_t slot, uint32_t *chan, uint32_t *retries, uint64_t *first_digest);
uint32_t fh_hop(const uint8_t key[16], uint64_t slot, uint32_t M);              /* default RW=32 NCH=2; M in 1..2^31 */
typedef struct { uint16_t mask; uint8_t n; uint8_t list[FH_NCH_MAX]; } fh_chmap_t;
void     fh_chmap_set(fh_chmap_t *m, uint16_t mask);   /* mask & ALL; fewer than 2 channels -> falls back to ALL (never hop on one channel) */
uint32_t fh_hop_mapped(const uint8_t key[16], uint64_t slot, const fh_chmap_t *m);  /* good[fh_hop(key,slot,n)]: unbiased over the good set */
uint64_t fh_slot_extend(uint64_t ref, uint32_t lo32);   /* nearest 56-bit slot to ref whose low 32 bits are lo32 */

/* ---------- replay window (copied from LifeLine-Mesh, renamed; per (origin, class) 64-bit sliding bitmap, LRU eviction) ---------- */
#ifndef FH_REPLAY_CAP
#define FH_REPLAY_CAP 4u
#endif
enum { FH_RP_NEW = 0, FH_RP_DUP = 1, FH_RP_OLD = 2 };
typedef struct { uint16_t origin; uint8_t cls; uint8_t used; uint32_t highest; uint64_t bitmap; uint32_t last_used; } fh_rp_entry_t;
typedef struct { fh_rp_entry_t e[FH_REPLAY_CAP]; uint32_t tick; } fh_replay_t;
void fh_replay_init(fh_replay_t *r);
int  fh_replay_check_and_update(fh_replay_t *r, uint16_t origin, uint8_t cls, uint32_t ctr);   /* call only after the MAC verified */

/* rolling counter: ctr = boot_count << 20 | seq, so a reboot with a bumped (non-volatile) boot_count never goes backwards */
typedef struct { uint32_t boot, seq; } fh_ctr_t;
void     fh_ctr_init(fh_ctr_t *c, uint32_t boot);
uint32_t fh_ctr_next(fh_ctr_t *c);         /* seq overflow rolls into boot (documented: persist boot) */

/* ---------- packets ---------- */
enum { FH_T_BEACON = 0, FH_T_DATA = 1, FH_T_ACK = 2 };
#define FH_HDR          14u
#define FH_MAC_LEN      4u
#define FH_OVERHEAD     (FH_HDR + FH_MAC_LEN + 2u)
#define FH_MAX_PAYLOAD  20u
#define FH_MAX_FRAME    (FH_OVERHEAD + FH_MAX_PAYLOAD)
#define FH_MIN_FRAME    FH_OVERHEAD
typedef struct {
    uint8_t type, src, mode, retry;     /* mode 0..3 (ladder), retry 0..3 */
    uint32_t slot, ctr;                  /* slot = low 32 bits of the slot counter */
    uint16_t map;                        /* channel map to apply at the next superframe */
    uint8_t plen; uint8_t payload[FH_MAX_PAYLOAD];
} fh_frame_t;
/* wire: vt(1) src(1) mode|retry<<2(1) slot32 LE(4) ctr32 LE(4) map16 LE(2) plen(1) payload MAC4 CRC16 LE.  MAC = low 32 bits of SipHash-2-4(mac, everything before it). */
int fh_encode(const uint8_t mackey[16], const fh_frame_t *f, uint8_t *out, size_t cap, size_t *outlen);
int fh_decode(const uint8_t mackey[16], const uint8_t *buf, size_t len, fh_frame_t *out);
int fh_frame_crc_ok(const uint8_t *buf, size_t len);   /* length + CRC only (used by the jam node, which has no link key) */

/* ---------- configuration and slot timing state machine ---------- */
typedef struct {
    uint32_t slot_us, tx_off_us, ack_off_us, ack_end_us, pre_us, guard_us, drift_ppm;
    uint32_t beacon_period;               /* slots; slot % period == 0 is a beacon slot on the rendezvous channel */
    uint8_t  nrdv, rdv[FH_RDV_MAX];       /* rendezvous channel list; beacon k goes on rdv[k % nrdv] */
    uint8_t  miss_lost, sync_miss_max, sync_confirm; uint16_t lost_max;
    uint32_t M; uint8_t hop_enable, fixed_ch;
    uint32_t crit_period, crit_deadline;  /* critical message every crit_period slots, deadline in slots */
} fh_cfg_t;
void fh_cfg_default(fh_cfg_t *c);        /* UNMEASURED timing: see docs/BRINGUP_28OCT.md */

typedef enum { FH_ST_SEARCH = 0, FH_ST_SYNC, FH_ST_TRACK, FH_ST_LOST } fh_state_t;
const char *fh_state_name(fh_state_t s);
typedef struct {
    fh_state_t st; int has_anchor;
    uint64_t anchor_slot, anchor_us;      /* anchor_us = local time at which anchor_slot started */
    uint32_t miss, confirm;
    uint64_t floor_slot; int has_floor;   /* highest beacon slot ever accepted (anti-replay of time) */
    uint8_t rdv_idx; uint64_t dwell_start_us;
    uint32_t n_acq, n_lost, n_search, n_rej;
} fh_sync_t;
void     fh_sync_init(fh_sync_t *s, uint64_t now_us);
uint64_t fh_sync_slot_start(const fh_sync_t *s, const fh_cfg_t *c, uint64_t slot);
uint32_t fh_sync_guard(const fh_sync_t *s, const fh_cfg_t *c);
int      fh_is_beacon_slot(const fh_cfg_t *c, uint64_t slot);
uint8_t  fh_beacon_channel(const fh_cfg_t *c, uint64_t slot);
/* a packet whose MAC and replay check passed; returns 1 if it is accepted for timing purposes */
int      fh_sync_on_packet(fh_sync_t *s, const fh_cfg_t *c, int is_beacon, uint64_t slot, uint64_t t_rx_us);
void     fh_sync_on_miss(fh_sync_t *s, const fh_cfg_t *c, uint64_t now_us);   /* one slot passed with no accepted packet */
uint8_t  fh_sync_search_channel(fh_sync_t *s, const fh_cfg_t *c, uint64_t now_us);

/* ---------- AFH / Thompson-style channel scoring, integer only (Q16) ---------- */
#define FH_Q 65536u
typedef struct { uint32_t a[FH_NCH_MAX], b[FH_NCH_MAX]; uint32_t n; uint64_t rng; } fh_afh_t;
void     fh_afh_init(fh_afh_t *s, uint32_t n, uint32_t seed);
void     fh_afh_update(fh_afh_t *s, uint32_t ch, int ok);          /* discounted Beta counts: gamma = 0.99, floor 0.001 (as sim/adaptive.py Thompson) */
uint32_t fh_afh_mean(const fh_afh_t *s, uint32_t ch);              /* a/(a+b) in Q16 */
int      fh_afh_avoiding(const fh_afh_t *s);                       /* min posterior mean < 0.6 */
uint32_t fh_afh_sample(fh_afh_t *s, uint32_t ch);                  /* Q16 draw: mean + z*sd, z uniform with unit variance (an approximation of a Beta draw) */
uint16_t fh_afh_pick_map(fh_afh_t *s, uint32_t thr_q16, uint32_t min_good);

/* ---------- degradation ladder with hysteresis (controller of sim/ladder.py) ---------- */
enum { FH_M_NORMAL = 0, FH_M_ADAPT, FH_M_CODED, FH_M_SURVIVAL };
const char *fh_mode_name(int m);
uint32_t fh_crit_tries(int mode);                                  /* 1, 3, 5, 10 */
typedef struct {
    int mode; uint8_t hist[50]; uint32_t nh, pos, nlost; uint32_t calm, switches;
    uint8_t lostch[50]; uint32_t nl, lpos;
} fh_ladder_t;
typedef struct { uint64_t slot; int from, to; uint32_t loss_pct, nlost, nwin; uint8_t top[2]; int upgrade; } fh_ladder_event_t;
void fh_ladder_init(fh_ladder_t *l);
/* feed one slot outcome; returns 1 and fills *ev when the mode changed */
int  fh_ladder_step(fh_ladder_t *l, uint64_t slot, int ok, uint32_t ch, int avoiding, fh_ladder_event_t *ev);
size_t fh_ladder_event_text(const fh_ladder_event_t *ev, char *out, size_t cap);

/* ---------- serial line protocol: $FH,slot,ch,ok,retries,rssi*CRC8\n  (sim/serial_proto.py) ---------- */
typedef struct { uint32_t slot, ch, retries; int ok; int32_t rssi; } fh_serial_rec_t;
size_t fh_serial_encode(char *out, size_t cap, uint32_t slot, uint32_t ch, int ok, uint32_t retries, int32_t rssi);   /* 0 if cap too small; includes the '\n' */
int    fh_serial_parse(const char *line, size_t len, fh_serial_rec_t *rec);     /* FH_OK or FH_E_FORMAT/FH_E_CRC/FH_E_RANGE */
typedef void (*fh_sink_fn)(void *ctx, const char *s, size_t n);

/* ---------- safety guard (policy logic of sim/safety.py, integer milliseconds) ---------- */
#ifdef FH_SIM_UNSAFE_LIMITS            /* host simulation only; never defined by the ESP32 build */
#define FH_HARD_DUTY_PCT 100u
#define FH_HARD_POWER    3u
#define FH_HARD_BURST_MS 60000u
#else
#define FH_HARD_DUTY_PCT 10u
#define FH_HARD_POWER    1u
#define FH_HARD_BURST_MS 2000u
#endif
#define FH_GUARD_WINDOW_MS 10000u
#define FH_GUARD_RING 128u
enum { FH_G_ALLOW = 0, FH_G_KILLED, FH_G_NOTOKEN, FH_G_CHANNEL, FH_G_POWER, FH_G_DUTY, FH_G_BURST, FH_G_LOGFULL, FH_G_ARG };
const char *fh_guard_reason(int r);
typedef struct { uint16_t allowed_mask; uint8_t max_power, max_duty_pct; uint32_t max_burst_ms, token_ttl_ms, gap_reset_ms; } fh_guard_cfg_t;
typedef void (*fh_guard_log_fn)(void *ctx, uint64_t now_ms, const char *kind, int reason, uint32_t ch, uint32_t power);
typedef struct {
    fh_guard_cfg_t cfg; uint8_t key[16];
    int has_ctr; uint64_t last_ctr; int has_token; uint64_t token_ms; int killed;
    uint32_t burst_ms; uint64_t last_end_ms;
    uint64_t t[FH_GUARD_RING]; uint32_t d[FH_GUARD_RING]; uint32_t head, count;
    fh_guard_log_fn log; void *log_ctx;
    uint32_t n_allow, n_deny; int clamped;
} fh_guard_t;
void     fh_guard_init(fh_guard_t *g, const fh_guard_cfg_t *cfg, const uint8_t key[16]);   /* cfg is CLAMPED to the FH_HARD_* limits */
uint64_t fh_guard_token_tag(const uint8_t key[16], uint64_t ctr);
int      fh_guard_accept_token(fh_guard_t *g, uint64_t now_ms, uint64_t ctr, uint64_t tag);   /* 1 accepted */
void     fh_guard_kill(fh_guard_t *g, uint64_t now_ms);
int      fh_guard_request(fh_guard_t *g, uint64_t now_ms, uint32_t ch, uint32_t power, uint32_t dt_ms);   /* FH_G_ALLOW or a denial reason */

#endif
