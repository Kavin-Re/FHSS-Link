/* Radio HAL: the ONLY thing the link/jam code needs from the platform. Implemented by sim/mock_radio.c on the host; the ESP32 implementation does NOT exist yet (bring-up item, docs/BRINGUP_28OCT.md). All calls are non-blocking. */
#ifndef FH_RADIO_H
#define FH_RADIO_H
#include <stddef.h>
#include <stdint.h>
typedef struct { uint64_t rx_ts_us; int8_t rssi_dbm; uint8_t ch; } fh_rxinfo_t;   /* rx_ts_us: local time at START of frame reception */
typedef struct fh_radio {
    void *ctx;
    int      (*set_channel)(void *ctx, uint8_t ch);                  /* logical channel 0..12; HAL maps to the physical channel */
    int      (*set_power)(void *ctx, uint8_t level);                 /* 0 = lowest. Extra to the 5 required ops: needed by the safety guard */
    int      (*tx)(void *ctx, const uint8_t *buf, size_t len);       /* start a transmission; 0 ok, FH_E_BUSY if the radio cannot send now */
    int      (*rx)(void *ctx, uint8_t *buf, size_t cap, size_t *len, fh_rxinfo_t *info);   /* pop one received frame: 1 if got one, 0 if none */
    int8_t   (*rssi)(void *ctx);                                     /* energy on the current channel now, dBm */
    uint64_t (*now_us)(void *ctx);                                   /* free-running local microsecond clock */
} fh_radio_t;
#endif
