#include "fh.h"
#include "fh_fmt.h"
const char *fh_mode_name(int m) { static const char *n[] = { "NORMAL", "ADAPT", "CODED", "SURVIVAL" }; return (m >= 0 && m < 4) ? n[m] : "?"; }
uint32_t fh_crit_tries(int mode) { static const uint32_t t[] = { 1u, 3u, 5u, 10u }; return (mode >= 0 && mode < 4) ? t[mode] : 1u; }
void fh_ladder_init(fh_ladder_t *l) {
    uint32_t i; l->mode = FH_M_NORMAL; l->nh = l->pos = l->nlost = l->calm = l->switches = l->nl = l->lpos = 0;
    for (i = 0; i < 50u; i++) { l->hist[i] = 0; l->lostch[i] = 0; }
}
int fh_ladder_step(fh_ladder_t *l, uint64_t slot, int ok, uint32_t ch, int avoiding, fh_ladder_event_t *ev) {
    uint32_t loss_pct = 0, want, cnt[FH_NCH_MAX], i, t0 = 0, t1 = 1; int cur = l->mode, to = cur, upgrade = 0;
    /* 50-attempt sliding window of lost flags */
    if (l->nh == 50u) l->nlost -= l->hist[l->pos]; else l->nh++;
    l->hist[l->pos] = (uint8_t)(ok ? 0u : 1u); l->nlost += l->hist[l->pos]; l->pos = (l->pos + 1u) % 50u;
    if (!ok) { l->lostch[l->lpos] = (uint8_t)(ch & 0xFFu); l->lpos = (l->lpos + 1u) % 50u; if (l->nl < 50u) l->nl++; }
    /* integer compare of loss = nlost/nh against 8% / 25% / 55%; below 20 samples loss counts as 0 (as ladder.py) */
    if (l->nh >= 20u) {
        loss_pct = (l->nlost * 100u) / l->nh;
        want = (l->nlost * 100u < 8u * l->nh) ? 0u : (l->nlost * 100u < 25u * l->nh) ? 1u : (l->nlost * 100u < 55u * l->nh) ? 2u : 3u;
    } else want = 0u;
    if ((int)want > cur) { to = (int)want; upgrade = 1; l->calm = 0; }
    else if ((int)want < cur) {
        int still = (cur == FH_M_ADAPT) && avoiding;
        l->calm = still ? 0u : l->calm + 1u;
        if (l->calm >= 100u) { to = (int)want; l->calm = 0; }
    } else l->calm = 0;
    if (to == cur) return 0;
    for (i = 0; i < FH_NCH_MAX; i++) cnt[i] = 0;
    for (i = 0; i < l->nl; i++) cnt[l->lostch[i] % FH_NCH_MAX]++;
    for (i = 1; i < FH_NCH_MAX; i++) if (cnt[i] > cnt[t0]) t0 = i;
    t1 = (t0 == 0u) ? 1u : 0u; for (i = 0; i < FH_NCH_MAX; i++) if (i != t0 && cnt[i] > cnt[t1]) t1 = i;
    if (ev) { ev->slot = slot; ev->from = cur; ev->to = to; ev->loss_pct = loss_pct; ev->nlost = l->nlost; ev->nwin = l->nh; ev->top[0] = (uint8_t)t0; ev->top[1] = (uint8_t)t1; ev->upgrade = upgrade; }
    l->mode = to; l->switches++; return 1;
}
size_t fh_ladder_event_text(const fh_ladder_event_t *ev, char *out, size_t cap) {
    fh_wbuf_t w; fh_wb_init(&w, out, cap);
    fh_wb_s(&w, "slot "); fh_wb_u(&w, ev->slot); fh_wb_s(&w, ": "); fh_wb_s(&w, fh_mode_name(ev->from)); fh_wb_s(&w, " -> "); fh_wb_s(&w, fh_mode_name(ev->to));
    if (ev->upgrade) { fh_wb_s(&w, " because loss "); fh_wb_u(&w, ev->loss_pct); fh_wb_s(&w, "% over the last "); fh_wb_u(&w, ev->nwin); fh_wb_s(&w, " attempts; most-hit channels [");
        fh_wb_u(&w, ev->top[0]); fh_wb_s(&w, ", "); fh_wb_u(&w, ev->top[1]); fh_wb_c(&w, ']'); }
    else { fh_wb_s(&w, " because loss fell to "); fh_wb_u(&w, ev->loss_pct); fh_wb_s(&w, "% and stayed low for 100 slots"); }
    if (w.over || w.n >= cap) return 0;
    w.p[w.n] = 0; return w.n;
}
