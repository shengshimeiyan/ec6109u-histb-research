#!/usr/bin/env python3
"""生成 DDR 适配版 U 盘刷机包。

用法:
    python3 patch_firmware.py <官方dmb包.zip> <TTL包.zip> <输出目录>

原理: U 盘包根目录 fastboot.bin 里的 DDR 配置表(0x4a0 起)是 dmb/DDR4-2G,
      对 mv2dma 板需要换成 TTL 包里 dma-6109u fastboot 的表。
      全部 6 套 blob 都要统一, 否则 U-Boot 运行时可能重选回 DDR4。
"""
import os
import shutil
import sys
import zipfile

START = 0x4A0
END = 0x1004
BLOBS = [0x4A0, 0xCBE20, 0xCDE20, 0xCFE20, 0xD3E20, 0xD5E20]


def find_blob_end(buf: bytes, start: int) -> int:
    n = buf.find(b'\x00', start)
    ds = n + 1
    run = 0
    for i in range(ds, min(ds + 0x2000, len(buf))):
        if buf[i] == 0:
            run += 1
            if run >= 64:
                return i - 63 + 64
        else:
            run = 0
    return ds + 0x1000


def extract_src_blob(dma_fastboot: bytes) -> bytes:
    e = find_blob_end(dma_fastboot, START)
    return bytes(dma_fastboot[START:e])


def patch(usb_zip: str, ttl_zip: str, out_dir: str) -> None:
    try:
        if os.path.exists(out_dir):
            shutil.rmtree(out_dir)
        os.makedirs(out_dir)
    except OSError as exc:
        print(f"准备输出目录失败: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        with zipfile.ZipFile(usb_zip) as z:
            z.extractall(out_dir)
        with zipfile.ZipFile(ttl_zip) as z:
            z.extract("fastboot-hi3798mv2dma-6109u-64.bin", out_dir)
    except (OSError, zipfile.BadZipFile) as exc:
        print(f"解包失败: {exc}", file=sys.stderr)
        sys.exit(1)

    src = os.path.join(out_dir, "fastboot-hi3798mv2dma-6109u-64.bin")
    try:
        with open(src, "rb") as f:
            dma_fb = f.read()
    except OSError as exc:
        print(f"读取 DMA fastboot 失败: {exc}", file=sys.stderr)
        sys.exit(1)
    blob = extract_src_blob(dma_fb)

    targets = [
        os.path.join(out_dir, "fastboot.bin"),
        os.path.join(out_dir, "mv200", "fastboot.bin"),
    ]
    for path in targets:
        try:
            with open(path, "rb") as f:
                data = bytearray(f.read())
        except OSError as exc:
            print(f"读取 {path} 失败: {exc}", file=sys.stderr)
            sys.exit(1)
        for s in BLOBS:
            e = find_blob_end(bytes(data), s)
            old_len = e - s
            if len(blob) >= old_len:
                repl = blob[:old_len]
            else:
                repl = blob + b'\x00' * (old_len - len(blob))
            data[s:e] = repl
        try:
            with open(path, "wb") as f:
                f.write(data)
        except OSError as exc:
            print(f"写入 {path} 失败: {exc}", file=sys.stderr)
            sys.exit(1)

    print("已修正:", targets)
    print("DDR 配置:", blob[:60].split(b'\x00')[0].decode())


def main() -> None:
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    patch(sys.argv[1], sys.argv[2], sys.argv[3])


if __name__ == "__main__":
    main()
