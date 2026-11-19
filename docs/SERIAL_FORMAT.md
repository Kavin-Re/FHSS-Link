# Serial line format (board -> laptop, and emulator -> dashboard)
One line per slot, ASCII, 115200 baud later:

    $FH,<slot>,<channel>,<ok>,<retries>,<rssi_dbm>*<CRC8>

Example: `$FH,42,7,1,0,-61*1F` (CRC value illustrative; `sim/serial_proto.py` computes it).
- ok: 1 delivered, 0 lost. retries: extra transmissions used. rssi_dbm: measured on that channel.
- CRC-8 (poly 0x07, init 0) over the text between `$` and `*`. Bad lines are counted and skipped, never crash the reader.
- Same parser in Python (`sim/serial_proto.py`) and JavaScript (dashboard Replay source). Test vector: CRC-8 of "123456789" = 0xF4.
- Logs in `logs/*.log` are produced by `sim/emu_device.py`; load them with Source = Replay in the dashboard.
