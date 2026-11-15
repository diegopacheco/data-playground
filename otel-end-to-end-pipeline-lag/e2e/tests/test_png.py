import struct
import zlib

import pytest

from harness.png import SIGNATURE, strip


def chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def test_text_and_time_chunks_are_removed_so_screenshots_carry_no_metadata() -> None:
    header = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    pixels = chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
    png = SIGNATURE + header + chunk(b"tEXt", b"Author\x00someone") + chunk(b"tIME", b"\x07\xea\x0b\x07\x00\x00\x00") + pixels + chunk(b"IEND", b"")
    assert strip(png) == SIGNATURE + header + pixels + chunk(b"IEND", b"")


def test_non_png_input_is_rejected() -> None:
    with pytest.raises(ValueError):
        strip(b"GIF89a")
