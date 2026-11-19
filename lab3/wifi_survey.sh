#!/usr/bin/env bash
# wifi_survey.sh - passive 2.4 GHz survey logger for the FHSS-Link project. Run it on YOUR OWN laptop host (not in a VM).
#
# What it does: asks the Wi-Fi stack for the list of access points it already knows/hears and appends ONE CSV LINE PER ACCESS POINT
# PER SCAN:  timestamp, scan_id, channel, freq_mhz, signal_pct, signal_dbm_est
# What it never does: it never reads or stores SSIDs or BSSIDs/MACs (nmcli is asked only for CHAN,SIGNAL,FREQ; the iw fallback parser
# discards the BSS line and every SSID line), never connects, never changes any network setting, never needs sudo.
# scan_id is a per-run random 6-hex salt plus a scan counter ("a3f09c-0007") - it only groups the lines of one scan.
#
# Source 1 (preferred): nmcli -t -f CHAN,SIGNAL,FREQ dev wifi list [ifname IF] [--rescan yes|no|auto]
#   SIGNAL is NetworkManager's 0-100 "quality"; the dBm estimate uses the common NetworkManager mapping dBm = pct/2 - 100
#   (100% = -50 dBm, 0% = -100 dBm). It is only an estimate (coarse, driver dependent).
# Source 2 (fallback when nmcli is missing or fails): iw dev IF scan dump   (reads the kernel's cached scan results; needs no root.
#   It prints real dBm, pct is then computed as 2*(dBm+100) clipped to 0..100). If it prints nothing the cache is empty/old:
#   run the nmcli path once or trigger a scan from your desktop first.
# Only 2.4 GHz (2400-2500 MHz) entries are kept. A scan that sees no 2.4 GHz AP writes one line with channel 0 so that "empty scans" are counted.
#
# usage: ./wifi_survey.sh [-i IFACE] [-n SCANS] [-d SECONDS_BETWEEN] [-o out.csv] [-r yes|no|auto] [-h]
#   e.g. one scan every 10 min for 8 hours:  ./wifi_survey.sh -n 48 -d 600 -o campus_day1.csv
# Then analyse:  python3 wifi_survey.py analyse campus_day1.csv
set -u
IFACE=""; COUNT=1; INTERVAL=60; OUT=""; RESCAN="auto"
usage() { sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; }
while getopts "i:n:d:o:r:h" opt; do
  case "$opt" in
    i) IFACE="$OPTARG" ;; n) COUNT="$OPTARG" ;; d) INTERVAL="$OPTARG" ;; o) OUT="$OPTARG" ;; r) RESCAN="$OPTARG" ;;
    h) usage; exit 0 ;; *) usage >&2; exit 2 ;;
  esac
done
case "$COUNT" in ''|*[!0-9]*) echo "error: -n must be a positive integer" >&2; exit 2 ;; esac
case "$INTERVAL" in ''|*[!0-9]*) echo "error: -d must be a non-negative integer" >&2; exit 2 ;; esac
case "$RESCAN" in yes|no|auto) ;; *) echo "error: -r must be yes, no or auto" >&2; exit 2 ;; esac
[ "$COUNT" -ge 1 ] || { echo "error: -n must be >= 1" >&2; exit 2; }
[ -n "$OUT" ] || OUT="wifi_survey_$(date +%Y%m%d).csv"
command -v awk >/dev/null 2>&1 || { echo "error: awk not found" >&2; exit 2; }
RUN=$(od -An -N3 -tx1 /dev/urandom 2>/dev/null | tr -d ' \n'); [ -n "$RUN" ] || RUN="$$"

if [ ! -s "$OUT" ]; then
  printf '# real 2.4 GHz survey written by wifi_survey.sh; no SSID/BSSID recorded; signal_dbm_est = signal_pct/2-100 when the source is nmcli\n' >> "$OUT"
  printf 'timestamp,scan_id,channel,freq_mhz,signal_pct,signal_dbm_est\n' >> "$OUT"
fi

# prints "chan freq pct dbm" per 2.4 GHz AP; returns non-zero if the source failed
scan_nmcli() {
  command -v nmcli >/dev/null 2>&1 || return 1
  local args=(-t -f CHAN,SIGNAL,FREQ dev wifi list)
  [ -n "$IFACE" ] && args+=(ifname "$IFACE")
  [ "$RESCAN" != "auto" ] && args+=(--rescan "$RESCAN")
  local raw; raw=$(nmcli "${args[@]}" 2>/dev/null) || return 1
  printf '%s\n' "$raw" | awk -F: '
    NF >= 3 { ch=$1+0; pct=$2+0; f=$3; sub(/[^0-9].*$/, "", f); f=f+0
              if (f >= 2400 && f <= 2500 && $2 ~ /^[0-9]+$/) { if (pct > 100) pct = 100; printf "%d %d %d %.1f\n", ch, f, pct, pct/2 - 100 } }'
}
scan_iw() {
  command -v iw >/dev/null 2>&1 || return 1
  local ifc="$IFACE"
  [ -n "$ifc" ] || ifc=$(iw dev 2>/dev/null | awk '$1=="Interface"{print $2; exit}')
  [ -n "$ifc" ] || return 1
  local raw; raw=$(iw dev "$ifc" scan dump 2>/dev/null) || return 1
  printf '%s\n' "$raw" | awk '
    function emit() { if (f > 0 && have) { ch = (f == 2484) ? 14 : int((f - 2407) / 5); pct = int(2 * (s + 100) + 0.5); if (pct < 0) pct = 0; if (pct > 100) pct = 100
                      if (f >= 2400 && f <= 2500) printf "%d %d %d %.1f\n", ch, f, pct, s } f = 0; have = 0 }
    /^BSS / { emit() }                      # BSS line holds the MAC: used only as a separator, never stored
    /^[ \t]+freq:/ { f = int($2) }
    /^[ \t]+signal:/ { s = $2 + 0; have = 1 }
    END { emit() }'
}

n=0
while [ "$n" -lt "$COUNT" ]; do
  n=$((n + 1)); ts=$(date +%Y-%m-%dT%H:%M:%S%z); sid=$(printf '%s-%04d' "$RUN" "$n")
  if rows=$(scan_nmcli); then src=nmcli
  elif rows=$(scan_iw); then src=iw
  else echo "scan $n: neither nmcli nor 'iw dev IF scan dump' gave a result (is Wi-Fi on? is this a VM without a Wi-Fi device?)" >&2; exit 3
  fi
  if [ -z "$rows" ]; then printf '%s,%s,0,0,0,-100.0\n' "$ts" "$sid" >> "$OUT"; k=0
  else printf '%s\n' "$rows" | awk -v ts="$ts" -v sid="$sid" '{ printf "%s,%s,%d,%d,%d,%.1f\n", ts, sid, $1, $2, $3, $4 }' >> "$OUT"; k=$(printf '%s\n' "$rows" | wc -l); fi
  echo "scan $n/$COUNT via $src: $k access points (2.4 GHz) appended to $OUT" >&2
  [ "$n" -lt "$COUNT" ] && sleep "$INTERVAL"
done
exit 0
