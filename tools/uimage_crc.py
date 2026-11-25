#!/usr/bin/env python3
"""uImage header CRC 计算与校验工具。

用法:
    python3 uimage_crc.py <kernel.bin>            # 校验
    python3 uimage_crc.py --fix <kernel.bin>       # 修正 hcrc 字段

海思内核镜像里 uImage header 位于外层头 0x48 字段指向的偏移（通常 0x70a8）。
hcrc 的正确算法是: 把 64 字节 header 的 hcrc 字段清零后算整个 64 字节的 CRC32。
"""
import struct
import sys
import zlib

UIMAGE_MAGIC = 0x27051956


def uimage_offset(data: bytearray) -> int:
    return struct.unpack_from("<I", data, 0x48)[0]


def hcrc(header64: bytes) -> int:
    h = bytearray(header64)
    struct.pack_into(">I", h, 4, 0)
    return zlib.crc32(bytes(h)) & 0xFFFFFFFF


def check(path: str, fix: bool) -> None:
    try:
        with open(path, "rb") as f:
            data = bytearray(f.read())
    except OSError as exc:
        print(f"读取失败: {exc}", file=sys.stderr)
        sys.exit(1)

    off = uimage_offset(data)
    magic, stored_h, ts, size, load, ep, stored_d = struct.unpack_from(">7I", data, off)
    if magic != UIMAGE_MAGIC:
        print(f"非 uImage (magic=0x{magic:x})", file=sys.stderr)
        sys.exit(1)

    calc_h = hcrc(bytes(data[off:off + 64]))
    payload = bytes(data[off + 64:off + 64 + size])
    calc_d = zlib.crc32(payload) & 0xFFFFFFFF

    print(f"uImage @0x{off:x}  size=0x{size:x} load=0x{load:x} ep=0x{ep:x}")
    print(f"hcrc: stored=0x{stored_h:08x} calc=0x{calc_h:08x} "
          f"{'OK' if stored_h == calc_h else 'MISMATCH'}")
    print(f"dcrc: stored=0x{stored_d:08x} calc=0x{calc_d:08x} "
          f"{'OK' if stored_d == calc_d else 'MISMATCH'}")
    print(f"外层头 0x50=0x{struct.unpack_from('<I', data, 0x50)[0]:x} "
          f"(应=0x{len(data) - off:x})")
    print(f"外层头 0x70=0x{struct.unpack_from('<I', data, 0x70)[0]:x} "
          f"(应=0x{len(data):x})")

    if fix and stored_h != calc_h:
        struct.pack_into(">I", data, off + 4, calc_h)
        try:
            with open(path, "wb") as f:
                f.write(data)
        except OSError as exc:
            print(f"写入失败: {exc}", file=sys.stderr)
            sys.exit(1)
        print("已修正 hcrc")


def main() -> None:
    args = sys.argv[1:]
    fix = "--fix" in args
    args = [a for a in args if a != "--fix"]
    if not args:
        print(__doc__)
        sys.exit(1)
    check(args[0], fix)


if __name__ == "__main__":
    main()
