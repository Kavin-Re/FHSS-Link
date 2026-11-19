"""Line protocol between a board (or the emulator) and the laptop. One line per slot:
   $FH,<slot>,<channel>,<ok 0|1>,<retries>,<rssi_dbm>*<CRC8 hex of the text between '$' and '*'>\n
CRC-8 poly 0x07, init 0. Same format will be printed by the firmware over USB serial."""

def crc8(data: bytes, poly=0x07):
    c = 0
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ poly) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c

def encode(slot, ch, ok, retries, rssi):
    body = f"FH,{slot},{ch},{int(ok)},{retries},{rssi}"
    return f"${body}*{crc8(body.encode()):02X}\n"

def parse(line):
    """Returns dict, or None if the line is corrupt/not ours (callers count those as 'serial errors')."""
    line = line.strip()
    if not line.startswith("$") or "*" not in line: return None
    body, _, tag = line[1:].rpartition("*")
    try:
        if int(tag, 16) != crc8(body.encode()): return None
        f = body.split(",")
        if f[0] != "FH" or len(f) != 6: return None
        return dict(slot=int(f[1]), ch=int(f[2]), ok=bool(int(f[3])), retries=int(f[4]), rssi=int(f[5]))
    except ValueError:
        return None
