"""Parse a PacketLogger .pklg (little-endian variant) and print ATT traffic per connection."""

import struct
import sys
from datetime import datetime

path = sys.argv[1]
data = open(path, "rb").read()

conns: dict[int, str] = {}  # acl handle -> peer address
frag: dict[tuple[int, str], bytearray] = {}
out = []
pos = 0
t_first = None
ATT_OPS = {0x01: "ERR", 0x02: "MTU_REQ", 0x03: "MTU_RSP", 0x08: "RD_TYPE_REQ", 0x09: "RD_TYPE_RSP",
           0x0A: "READ_REQ", 0x0B: "READ_RSP", 0x10: "RD_GRP_REQ", 0x11: "RD_GRP_RSP",
           0x04: "FIND_INFO_REQ", 0x05: "FIND_INFO_RSP", 0x12: "WRITE_REQ", 0x13: "WRITE_RSP",
           0x52: "WRITE_CMD", 0x1B: "NOTIFY", 0x1D: "INDICATE", 0x1E: "CONFIRM"}

while pos + 4 <= len(data):
    (ln,) = struct.unpack_from("<I", data, pos)
    rec = data[pos + 4: pos + 4 + ln]
    pos += 4 + ln
    if len(rec) < 9:
        continue
    secs, usecs = struct.unpack_from("<II", rec, 0)
    ts = secs + usecs / 1e6
    if t_first is None:
        t_first = ts
    typ = rec[8]
    p = rec[9:]
    if typ == 0x01 and len(p) >= 2 and p[0] == 0x3E:  # LE meta event
        sub = p[2]
        if sub in (0x01, 0x0A) and p[3] == 0:
            h = struct.unpack_from("<H", p, 4)[0] & 0x0FFF
            addr = ":".join(f"{b:02X}" for b in reversed(p[8:14]))
            conns[h] = addr
            out.append((ts, f"CONNECT handle={h} peer={addr}"))
    elif typ == 0x01 and len(p) >= 6 and p[0] == 0x05:  # disconnect complete
        h = struct.unpack_from("<H", p, 3)[0] & 0x0FFF
        out.append((ts, f"DISCONNECT handle={h} peer={conns.get(h)} reason=0x{p[5]:02x}"))
    elif typ in (0x02, 0x03) and len(p) >= 4:
        hf, alen = struct.unpack_from("<HH", p, 0)
        h, pb = hf & 0x0FFF, (hf >> 12) & 0x3
        direction = "TX" if typ == 0x02 else "RX"
        body = p[4:4 + alen]
        key = (h, direction)
        if pb == 0x1:  # continuation
            if key not in frag:
                continue
            frag[key] += body
        else:
            frag[key] = bytearray(body)
        buf = frag[key]
        if len(buf) < 4:
            continue
        l2len, cid = struct.unpack_from("<HH", buf, 0)
        if len(buf) - 4 < l2len:
            continue  # wait for more fragments
        frag.pop(key)
        pdu = bytes(buf[4:4 + l2len])
        if cid != 0x0004 or not pdu:
            continue
        op = pdu[0]
        name = ATT_OPS.get(op, f"OP{op:02x}")
        if op in (0x52, 0x12, 0x1B, 0x1D, 0x0A, 0x0B) and len(pdu) >= 3 and op not in (0x0B,):
            ah = struct.unpack_from("<H", pdu, 1)[0]
            val = pdu[3:]
            out.append((ts, f"{direction} h{h} {conns.get(h, '?')} {name} att=0x{ah:04x} len={len(val)} {val.hex()}"))
        else:
            out.append((ts, f"{direction} h{h} {conns.get(h, '?')} {name} {pdu[1:].hex()}"))

for ts, line in out:
    print(f"{datetime.fromtimestamp(ts).strftime('%H:%M:%S.%f')[:-3]} +{ts - t_first:8.3f} {line}")
