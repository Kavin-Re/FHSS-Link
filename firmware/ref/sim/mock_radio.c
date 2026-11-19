#include <string.h>
#include "mock_radio.h"
static uint64_t rnd(mr_world_t *w) { uint64_t x = w->rng; x ^= x >> 12; x ^= x << 25; x ^= x >> 27; w->rng = x; return x * 0x2545F4914F6CDD1DULL; }
uint64_t mr_local(const mr_node_t *n, uint64_t t) {
    int64_t v = (int64_t)t + (int64_t)((long long)((int64_t)t) * n->ppm / 1000000) + n->off_us; return v < 0 ? 0u : (uint64_t)v;
}
static int busy(const mr_world_t *w, uint8_t ch) { return ch < FH_NCH_MAX && w->noise_until[ch] > w->t_us; }
static int m_set_channel(void *c, uint8_t ch) { mr_node_t *n = (mr_node_t *)c; if (ch >= FH_NCH) return FH_E_ARG; n->ch = ch; return FH_OK; }
static int m_set_power(void *c, uint8_t lv) { ((mr_node_t *)c)->power = lv; return FH_OK; }
static int m_tx(void *c, const uint8_t *buf, size_t len) {
    mr_node_t *s = (mr_node_t *)c; mr_world_t *w = s->w; int i, jam; 
    if (len == 0 || len > FH_MAX_FRAME) return FH_E_LEN;
    w->st_tx++;
    if (s->is_jammer) { w->noise_until[s->ch] = w->t_us + w->burst_airtime_us; return FH_OK; }   /* noise burst: occupies the channel, delivered to nobody as a frame */
    jam = busy(w, s->ch);
    for (i = 0; i < w->nn; i++) {
        mr_node_t *r = &w->n[i]; mr_frame_t *f; uint64_t rr;
        if (r == s || r->is_jammer || r->ch != s->ch) continue;
        rr = rnd(w);
        if (jam) {
            if ((rr % 100u) < w->p_jam_pct) { if (((rr >> 20) % 100u) < w->flip_pct) { /* corrupted but delivered */ } else { w->st_jam_drop++; continue; } }
        } else if (((rr >> 8) % 1000u) < w->p_loss_clean_permille) { w->st_clean_drop++; continue; }
        if (r->qn >= MR_QCAP) { w->st_qfull++; continue; }
        f = &r->q[r->qn++]; memcpy(f->buf, buf, len); f->len = (uint8_t)len;
        if (jam && ((rr % 100u) < w->p_jam_pct)) { size_t bit = (size_t)((rr >> 32) % (len * 8u)); f->buf[bit / 8u] = (uint8_t)(f->buf[bit / 8u] ^ (1u << (bit % 8u))); w->st_jam_flip++; }
        f->info.rx_ts_us = mr_local(r, w->t_us); f->info.ch = s->ch;
        { int rs = -62 + (int)((rr >> 48) % 5u) - 2 + (jam ? 14 : 0); f->info.rssi_dbm = (int8_t)rs; }
        w->st_delivered++;
    }
    return FH_OK;
}
static int m_rx(void *c, uint8_t *buf, size_t cap, size_t *len, fh_rxinfo_t *info) {
    mr_node_t *n = (mr_node_t *)c; uint8_t i;
    if (n->qn == 0) return 0;
    if (n->q[0].len > cap) { for (i = 1; i < n->qn; i++) n->q[i - 1] = n->q[i]; n->qn--; return 0; }
    memcpy(buf, n->q[0].buf, n->q[0].len); *len = n->q[0].len; if (info) *info = n->q[0].info;
    for (i = 1; i < n->qn; i++) n->q[i - 1] = n->q[i];
    n->qn--; return 1;
}
static int8_t m_rssi(void *c) { mr_node_t *n = (mr_node_t *)c; return (int8_t)(busy(n->w, n->ch) ? -48 : -95); }
static uint64_t m_now(void *c) { mr_node_t *n = (mr_node_t *)c; return mr_local(n, n->w->t_us); }
void mr_world_init(mr_world_t *w, uint64_t seed) {
    memset(w, 0, sizeof *w); w->rng = seed * 0x9E3779B97F4A7C15ULL + 0x1234567ULL; if (!w->rng) w->rng = 1;
    w->p_jam_pct = 95; w->p_loss_clean_permille = 10; w->flip_pct = 30; w->burst_airtime_us = 1100;   /* 0.95 / 0.01 as sim/emu_device.py */
}
int mr_add_node(mr_world_t *w, fh_radio_t *r, int32_t ppm, int64_t off_us, int is_jammer) {
    mr_node_t *n; if (w->nn >= MR_MAXN) return -1;
    n = &w->n[w->nn]; memset(n, 0, sizeof *n); n->w = w; n->id = w->nn; n->ppm = ppm; n->off_us = off_us; n->is_jammer = is_jammer;
    r->ctx = n; r->set_channel = m_set_channel; r->set_power = m_set_power; r->tx = m_tx; r->rx = m_rx; r->rssi = m_rssi; r->now_us = m_now;
    return w->nn++;
}
void mr_advance(mr_world_t *w, uint64_t t_us) { w->t_us = t_us; }
