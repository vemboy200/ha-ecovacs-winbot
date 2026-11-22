"""Turn pklg_att.py output into one line per Winbot JSON message.

Usage: python3 att_to_json.py att.txt [min_seconds]
"""

import re
import sys


def crc8(data: bytes) -> int:
    """CRC-8, poly 0x31, init 0, no reflection (same as winbot_query.crc8, without needing bleak)."""
    c = 0
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x31) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


path = sys.argv[1]
min_t = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
buf: dict[tuple[str, str], bytes] = {}
pat = re.compile(r"^(\S+) \+\s*([\d.]+) (TX|RX) (h\d+) \S+ (WRITE_CMD|NOTIFY) att=\S+ len=\d+ ([0-9a-f]+)")
for line in open(path):
    m = pat.search(line)
    if not m:
        if "CONNECT" in line and float(line.split("+")[1].split()[0]) >= min_t:
            print(line.rstrip())
        continue
    clock, t, d, h, _, hx = m.groups()
    if float(t) < min_t:
        continue
    key = (h, d)
    buf[key] = buf.get(key, b"") + bytes.fromhex(hx)
    while b"\n" in buf[key]:
        msg, buf[key] = buf[key].split(b"\n", 1)
        if not msg.startswith(b"`F"):
            print(f"{clock} +{t} {d} NONFRAME {msg[:80]!r}")
            continue
        crc = "ok" if crc8(msg[3:-1]) == msg[-1] else "BAD"
        i = msg.find(b"{")
        hdr = msg[:i].replace(b"\0", b"|").decode(errors="replace")
        body = msg[i:-1].decode(errors="replace")
        if b"XLog" in msg[:12]:
            body = body[:160]
        print(f"{clock} +{float(t):8.2f} {d} {hdr} crc={crc} {body}")
for k, v in buf.items():
    if v:
        print("INCOMPLETE", k, v[:120])
