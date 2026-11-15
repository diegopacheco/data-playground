import struct
import sys
from pathlib import Path

SIGNATURE = b"\x89PNG\r\n\x1a\n"
KEEP = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"sRGB"}


def strip(data: bytes) -> bytes:
    if not data.startswith(SIGNATURE):
        raise ValueError("not a png")
    out = bytearray(SIGNATURE)
    pos = len(SIGNATURE)
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind = data[pos + 4 : pos + 8]
        end = pos + 12 + length
        if kind in KEEP:
            out += data[pos:end]
        pos = end
    return bytes(out)


def main(paths: list[str]) -> None:
    for name in paths:
        path = Path(name)
        path.write_bytes(strip(path.read_bytes()))


if __name__ == "__main__":
    main(sys.argv[1:])
