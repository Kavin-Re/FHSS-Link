from serial_proto import encode, parse, crc8
from emu_device import emulate
def check(n, c): print(("PASS " if c else "FAIL ") + n); assert c
check("CRC-8 check value for '123456789' is 0xF4", crc8(b"123456789") == 0xF4)
l = encode(42, 7, True, 0, -61); check("round trip", parse(l) == dict(slot=42, ch=7, ok=True, retries=0, rssi=-61))
bad = l.replace(",7,", ",8,"); check("corrupted line rejected", parse(bad) is None)
check("garbage rejected", parse("hello") is None and parse("$FH,1*ZZ") is None)
rows = [parse(x[0]) for x in emulate("blind", "static", slots=500)]
check("emulator output all parses", all(r is not None for r in rows) and rows[-1]["slot"] == 499)
print("ALL PASSED")
