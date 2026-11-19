/* Deterministic mock medium for the host demo: N radios (fh_radio_t HAL), one shared air, a seeded PRNG, per-node crystal error,
 * and an interference model: a "jammer" radio that tx()s noise bursts marks the channel busy for the burst length; any frame sent
 * on a busy channel is lost (p_jam) or corrupted by one bit flip (CRC/MAC must catch it). Everything is a function of the seed. */
#ifndef MOCK_RADIO_H
#define MOCK_RADIO_H
#include "fh.h"
#include "fh_radio.h"
#define MR_MAXN 4
#define MR_QCAP 4
typedef struct { uint8_t buf[FH_MAX_FRAME]; uint8_t len; fh_rxinfo_t info; } mr_frame_t;
struct mr_world;
typedef struct { struct mr_world *w; int id; int is_jammer; uint8_t ch, power; int32_t ppm; int64_t off_us; mr_frame_t q[MR_QCAP]; uint8_t qn; } mr_node_t;
typedef struct mr_world {
    uint64_t t_us, rng; mr_node_t n[MR_MAXN]; int nn;
    uint64_t noise_until[FH_NCH_MAX];
    uint32_t p_jam_pct, p_loss_clean_permille, flip_pct, burst_airtime_us;
    uint32_t st_tx, st_delivered, st_jam_drop, st_jam_flip, st_clean_drop, st_qfull;
} mr_world_t;
void mr_world_init(mr_world_t *w, uint64_t seed);
int  mr_add_node(mr_world_t *w, fh_radio_t *r, int32_t ppm, int64_t off_us, int is_jammer);   /* returns node id */
void mr_advance(mr_world_t *w, uint64_t t_us);
uint64_t mr_local(const mr_node_t *n, uint64_t true_us);
#endif
