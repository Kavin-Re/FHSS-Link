/* tiny bounded text writer (no libc formatting); used by serial.c, ladder.c and the guard log text */
#ifndef FH_FMT_H
#define FH_FMT_H
#include <stddef.h>
#include <stdint.h>
#if defined(__GNUC__)
#define FH_UNUSED __attribute__((unused))
#else
#define FH_UNUSED
#endif
typedef struct { char *p; size_t cap, n; int over; } fh_wbuf_t;
static FH_UNUSED void fh_wb_init(fh_wbuf_t *w, char *p, size_t cap) { w->p = p; w->cap = cap; w->n = 0; w->over = 0; }
static FH_UNUSED void fh_wb_c(fh_wbuf_t *w, char c) { if (w->n + 1u < w->cap + 1u && w->n < w->cap) w->p[w->n++] = c; else w->over = 1; }
static FH_UNUSED void fh_wb_s(fh_wbuf_t *w, const char *s) { while (*s) fh_wb_c(w, *s++); }
static FH_UNUSED void fh_wb_u(fh_wbuf_t *w, uint64_t v) {
    char t[24]; unsigned n = 0;
    do { t[n++] = (char)('0' + (unsigned)(v % 10u)); v /= 10u; } while (v);
    while (n) fh_wb_c(w, t[--n]);
}
static FH_UNUSED void fh_wb_i(fh_wbuf_t *w, int32_t v) {
    if (v < 0) { fh_wb_c(w, '-'); fh_wb_u(w, (uint64_t)(-(int64_t)v)); } else fh_wb_u(w, (uint64_t)v);
}
static FH_UNUSED void fh_wb_hex2(fh_wbuf_t *w, unsigned v) { static const char H[] = "0123456789ABCDEF"; fh_wb_c(w, H[(v >> 4) & 15u]); fh_wb_c(w, H[v & 15u]); }
#endif
