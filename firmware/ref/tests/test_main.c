/* Host tests for the FHSS-Link firmware reference. usage: test_main <vectors_dir> */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fh.h"
static int fails = 0, checks = 0;
#define CHECK(c) do { checks++; if (!(c)) { fails++; printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)
static const char *vdir;

static int hexn(char c) { return (c >= '0' && c <= '9') ? c - '0' : (c >= 'a' && c <= 'f') ? c - 'a' + 10 : (c >= 'A' && c <= 'F') ? c - 'A' + 10 : -1; }
static int read_lines(const char *name, char lines[][80], int maxn) {
    char p[512]; FILE *f; int n = 0;
    snprintf(p, sizeof p, "%s/%s", vdir, name); f = fopen(p, "r");
    if (!f) { printf("cannot open %s\n", p); return -1; }
    while (n < maxn && fgets(lines[n], 80, f)) { size_t l = strlen(lines[n]); while (l && (lines[n][l-1]=='\n'||lines[n][l-1]=='\r')) lines[n][--l] = 0; if (l) n++; }
    fclose(f); return n;
}
static uint64_t hex64(const char *s) { uint64_t v = 0; while (*s) v = (v << 4) | (uint64_t)hexn(*s++); return v; }
/* key128 hex (python int, big-endian text) -> 16 key bytes little-endian */
static void key_from_hex(const char *s, uint8_t key[16]) {
    size_t n = strlen(s), i; uint8_t be[16]; memset(be, 0, 16);
    for (i = 0; i < n; i++) { size_t pos = 32 - n + i; be[pos / 2] = (uint8_t)(be[pos / 2] | (hexn(s[i]) << ((pos % 2) ? 0 : 4))); }
    for (i = 0; i < 16; i++) key[i] = be[15 - i];
}
static char L[60005][80];
static void vec_run(const char *vfile, const char *kfile, const char *sfile, uint32_t M, uint32_t RW, uint32_t NCH, int per_key, int nkeys_expected) {
    static char K[8][80], S[8][80]; int nk = read_lines(kfile, K, 8), ns = read_lines(sfile, S, 8), nv = read_lines(vfile, L, 60005), k, i; long bad = 0, tot = 0;
    CHECK(nk == nkeys_expected); CHECK(ns == nkeys_expected); CHECK(nv == per_key * nkeys_expected);
    if (nk != nkeys_expected || nv != per_key * nkeys_expected) return;
    for (k = 0; k < nk; k++) {
        uint8_t key[16]; uint64_t start = hex64(S[k]); fh_hopcfg_t c; c.M = M; c.RW = RW; c.NCH = NCH; key_from_hex(K[k], key);
        for (i = 0; i < per_key; i++) {
            uint32_t ch = 99, r = 0; int rc = fh_hop_cfg(&c, key, (start + (uint64_t)i) & FH_SLOT_MASK, &ch, &r, NULL);
            tot++; if (rc != FH_OK || ((r << 8) | ch) != (uint32_t)hex64(L[k * per_key + i])) bad++;
        }
    }
    printf("  %-22s M=%u RW=%u NCH=%u: %ld hops (word = retries<<8 | channel), %ld mismatches\n", vfile, M, RW, NCH, tot, bad);
    CHECK(bad == 0);
}
static void test_primitives(void) {
    uint8_t key[16]; unsigned i; uint8_t in[15]; uint8_t k2[16];
    for (i = 0; i < 16; i++) key[i] = (uint8_t)i;
    for (i = 0; i < 15; i++) in[i] = (uint8_t)i;
    CHECK(fh_siphash24(key, in, 15) == 0xa129ca6149be45e5ULL);                       /* SipHash paper appendix A */
    CHECK(fh_siphash24(key, in, 0) == 0x726fdb47dd0e0e31ULL);                         /* reference vectors.h, len 0 (bytes 31 0e 0e dd 47 db 6f 72 LE) */
    CHECK(fh_siphash24(key, in, 8) == 0x93f5f5799a932462ULL);                         /* len 8 (62 24 93 9a 79 f5 f5 93 LE) */
    CHECK(fh_crc16((const uint8_t *)"123456789", 9) == 0x29B1u);
    CHECK(fh_crc8((const uint8_t *)"123456789", 9) == 0xF4u);
    fh_derive(k2, key, "hop1"); { uint8_t k3[16]; fh_derive(k3, key, "mac1"); CHECK(memcmp(k2, k3, 16) != 0); fh_derive(k3, key, "hop1"); CHECK(memcmp(k2, k3, 16) == 0); }
}
static void test_hop(void) {
    uint8_t key[16]; 
    { unsigned i; fh_chmap_t m; int cnt[13] = {0}; uint32_t ch; for (i = 0; i < 16; i++) key[i] = (uint8_t)(i * 7 + 1);
      CHECK(fh_slot_extend(0x1000000005ULL, 7u) == 0x1000000007ULL); CHECK(fh_slot_extend(0x00FFFFFFF0ULL, 5u) == 0x0100000005ULL);
      CHECK(fh_slot_extend(0x0100000002ULL, 0xFFFFFFFEu) == 0x00FFFFFFFEULL); CHECK(fh_slot_extend(3u, 0xFFFFFFFFu) == 0xFFFFFFFFULL);
      fh_chmap_set(&m, 0); CHECK(m.n == 13u); fh_chmap_set(&m, 0x0001); CHECK(m.n == 13u); fh_chmap_set(&m, 0x1FFC); CHECK(m.n == 11u && m.list[0] == 2u);
      for (i = 0; i < 20000; i++) { ch = fh_hop_mapped(key, i, &m); CHECK(ch >= 2u && ch < 13u); cnt[ch]++; }
      CHECK(cnt[0] == 0 && cnt[1] == 0);
    }
}
static void test_vectors(void) {
    printf("hop_engine vectors (%s):\n", vdir);
    vec_run("vec_m13.mem", "keys_m13.mem", "starts_m13.mem", 13, 32, 2, 20000, 3);
    vec_run("vec_m13_rw8.mem", "keys_m13_rw8.mem", "starts_m13_rw8.mem", 13, 8, 1, 20000, 1);
    vec_run("vec_m13_rw8n4.mem", "keys_m13_rw8n4.mem", "starts_m13_rw8n4.mem", 13, 8, 4, 20000, 1);
    vec_run("vec_m16.mem", "keys_m16.mem", "starts_m16.mem", 16, 32, 2, 3000, 1);
    vec_run("vec_m37.mem", "keys_m37.mem", "starts_m37.mem", 37, 32, 2, 3000, 1);
}
static void test_packet(void) {
    uint8_t mk[16], wire[64], w2[64]; fh_frame_t f, g; size_t n, i; unsigned b; int rc; fh_replay_t rp; fh_ctr_t c;
    for (i = 0; i < 16; i++) mk[i] = (uint8_t)(0xA0 + i);
    memset(&f, 0, sizeof f); f.type = FH_T_DATA; f.src = 1; f.mode = 2; f.retry = 3; f.slot = 0xDEADBEEFu; f.ctr = 0x00100007u; f.map = 0x1ABC; f.plen = 5; memcpy(f.payload, "hello", 5);
    CHECK(fh_encode(mk, &f, wire, sizeof wire, &n) == FH_OK && n == FH_OVERHEAD + 5u);
    CHECK(fh_decode(mk, wire, n, &g) == FH_OK && g.type == f.type && g.src == 1 && g.mode == 2 && g.retry == 3 && g.slot == f.slot && g.ctr == f.ctr && g.map == f.map && g.plen == 5 && memcmp(g.payload, "hello", 5) == 0);
    /* every single-bit flip is rejected (CRC16 detects all single-bit errors; MAC backs it up) */
    { int accepted = 0; for (i = 0; i < n; i++) for (b = 0; b < 8; b++) { memcpy(w2, wire, n); w2[i] = (uint8_t)(w2[i] ^ (1u << b)); if (fh_decode(mk, w2, n, &g) == FH_OK) accepted++; } CHECK(accepted == 0); }
    /* a forger who fixes CRC but lacks the key is stopped by the MAC */
    memcpy(w2, wire, n); w2[3] ^= 1; { uint16_t crc = fh_crc16(w2, n - 2); w2[n - 2] = (uint8_t)crc; w2[n - 1] = (uint8_t)(crc >> 8); }
    CHECK(fh_decode(mk, w2, n, &g) == FH_E_MAC); CHECK(fh_frame_crc_ok(w2, n) == 1);
    { uint8_t wk[16]; memcpy(wk, mk, 16); wk[0] ^= 1; CHECK(fh_decode(wk, wire, n, &g) == FH_E_MAC); }
    CHECK(fh_decode(mk, wire, FH_MIN_FRAME - 1u, &g) == FH_E_LEN); CHECK(fh_decode(mk, wire, n - 1u, &g) != FH_OK);
    f.plen = 21; CHECK(fh_encode(mk, &f, wire, sizeof wire, &n) == FH_E_PLEN); f.plen = 0; f.type = 3; CHECK(fh_encode(mk, &f, wire, sizeof wire, &n) == FH_E_TYPE);
    f.type = FH_T_ACK; rc = fh_encode(mk, &f, wire, 5, &n); CHECK(rc == FH_E_LEN);
    /* replay window + rolling counter */
    fh_replay_init(&rp);
    CHECK(fh_replay_check_and_update(&rp, 1, 1, 10) == FH_RP_NEW); CHECK(fh_replay_check_and_update(&rp, 1, 1, 10) == FH_RP_DUP);
    CHECK(fh_replay_check_and_update(&rp, 1, 1, 8) == FH_RP_NEW); CHECK(fh_replay_check_and_update(&rp, 1, 1, 8) == FH_RP_DUP);
    CHECK(fh_replay_check_and_update(&rp, 1, 1, 200) == FH_RP_NEW); CHECK(fh_replay_check_and_update(&rp, 1, 1, 10) == FH_RP_OLD);
    CHECK(fh_replay_check_and_update(&rp, 2, 1, 5) == FH_RP_NEW);
    fh_ctr_init(&c, 5); CHECK(fh_ctr_next(&c) == (5u << 20)); CHECK(fh_ctr_next(&c) == (5u << 20) + 1u);
    c.seq = (1u << 20) - 1u; { uint32_t a = fh_ctr_next(&c), bb = fh_ctr_next(&c); CHECK(bb == a + 1u); }
    fh_ctr_init(&c, 4096); CHECK(fh_ctr_next(&c) == 0xFFFFFFFFu);
}
static void test_serial(void) {
    char buf[64]; size_t n; fh_serial_rec_t r; int rc;
    n = fh_serial_encode(buf, sizeof buf, 42, 7, 1, 0, -61); CHECK(n > 0 && buf[n - 1] == '\n'); CHECK(strncmp(buf, "$FH,42,7,1,0,-61*", 17) == 0);
    rc = fh_serial_parse(buf, n, &r); CHECK(rc == FH_OK && r.slot == 42 && r.ch == 7 && r.ok == 1 && r.retries == 0 && r.rssi == -61);
    CHECK(fh_serial_encode(buf, 10, 42, 7, 1, 0, -61) == 0);
    CHECK(fh_serial_parse("$FH,0,10,1,0,-60*EE\n", 20, &r) == FH_OK);             /* line from logs/demo_static.log */
    CHECK(fh_serial_parse("$FH,0,10,1,0,-60*EF\n", 20, &r) == FH_E_CRC);
    CHECK(fh_serial_parse("garbage", 7, &r) == FH_E_FORMAT); CHECK(fh_serial_parse("$FH,1,2,3*00", 12, &r) == FH_E_FORMAT);
    for (rc = 0; rc < 4; rc++) { n = fh_serial_encode(buf, sizeof buf, 0xFFFFFFFFu, 255, rc & 1, 255, rc < 2 ? -128 : 127); CHECK(n > 0 && fh_serial_parse(buf, n, &r) == FH_OK && r.slot == 0xFFFFFFFFu); }
}
extern void test_state(void(*chk)(int, const char *, int));
static void chk_cb(int ok, const char *e, int line) { checks++; if (!ok) { fails++; printf("FAIL tests/test_state.c:%d: %s\n", line, e); } }
int main(int argc, char **argv) {
    vdir = argc > 1 ? argv[1] : "../../rtl/hop_engine/vectors";
    test_primitives(); test_hop(); test_vectors(); test_packet(); test_serial();
    test_state(chk_cb);
    printf("%d checks, %d failures\n", checks, fails);
    return fails ? 1 : 0;
}
