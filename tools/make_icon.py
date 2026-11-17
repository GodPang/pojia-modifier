#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成破甲修改器的 Windows 图标（纯标准库，无第三方依赖）。

风格对齐程序界面：深蓝圆角方块（--accent #2b3f6b → #1d2c4d）+ 米白盾牌
（--surface #fdfcf8），盾面一道斜向裂缝表示「破甲」。按 4 倍超采样绘制后
盒式缩小，16px 也清晰。同时输出 256px PNG（预览）与多尺寸 ICO（16…256）。

用法：
    python tools/make_icon.py
"""
import os
import struct
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")


def rgb(h):
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5))


BG_LIGHT = rgb("#2b3f6b")
BG_DARK = rgb("#1d2c4d")
FACE = rgb("#fdfcf8")
SHADOW = rgb("#9aa6c4")
CRACK = rgb("#15213c")
HILITE = rgb("#8fa6d8")

# 盾牌（归一化坐标）
SHIELD = [(0.50, 0.16), (0.78, 0.27), (0.78, 0.50), (0.75, 0.61),
          (0.67, 0.73), (0.50, 0.85), (0.33, 0.73), (0.25, 0.61),
          (0.22, 0.50), (0.22, 0.27)]
# 主裂缝 + 分叉
CRACK_MAIN = [(0.625, 0.18), (0.71, 0.22), (0.45, 0.82), (0.375, 0.78)]
CRACK_BRANCH = [(0.545, 0.47), (0.61, 0.49), (0.685, 0.39), (0.63, 0.355)]


def in_poly(x, y, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            if x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                inside = not inside
        j = i
    return inside


def in_rounded(x, y, r):
    cx = min(max(x, r), 1.0 - r)
    cy = min(max(y, r), 1.0 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def blend(dst, src, a=1.0):
    return tuple(dst[i] * (1 - a) + src[i] * a for i in range(3)) + (1.0,)


def pixel(x, y):
    if not in_rounded(x, y, 0.19):
        return (0.0, 0.0, 0.0, 0.0)
    t = min(1.0, max(0.0, x * 0.35 + (1.0 - y) * 0.65))
    col = tuple(BG_LIGHT[i] * (1 - t) + BG_DARK[i] * t for i in range(3)) + (1.0,)
    # 盾牌投影
    if in_poly(x + 0.018, y + 0.022, SHIELD):
        col = blend(col, SHADOW, 0.45)
    if in_poly(x, y, SHIELD):
        col = FACE + (1.0,)
        # 盾面顶部高光
        if y < 0.30 and in_poly(x, y + 0.02, SHIELD):
            col = blend(col, rgb("#ffffff"), 0.35)
        # 裂缝高光边（先画，主裂缝覆盖其上）
        if in_poly(x + 0.012, y + 0.010, CRACK_MAIN) or \
           in_poly(x + 0.012, y + 0.010, CRACK_BRANCH):
            col = HILITE + (1.0,)
        if in_poly(x, y, CRACK_MAIN) or in_poly(x, y, CRACK_BRANCH):
            col = CRACK + (1.0,)
    # 方块顶部细高光
    if y < 0.035 and in_rounded(x, y + 0.02, 0.19):
        col = blend(col, rgb("#ffffff"), 0.12)
    return col


def render(size, ss=4):
    s = size * ss
    buf = bytearray(s * s * 4)
    for yy in range(s):
        y = (yy + 0.5) / s
        for xx in range(s):
            x = (xx + 0.5) / s
            r, g, b, a = pixel(x, y)
            i = (yy * s + xx) * 4
            buf[i] = int(r * a * 255 + 0.5)
            buf[i + 1] = int(g * a * 255 + 0.5)
            buf[i + 2] = int(b * a * 255 + 0.5)
            buf[i + 3] = int(a * 255 + 0.5)
    # 盒式缩小（预乘 alpha，避免边缘黑边）
    out = bytearray(size * size * 4)
    inv = 1.0 / (ss * ss)
    for y in range(size):
        for x in range(size):
            ar = ag = ab = aa = 0.0
            for dy in range(ss):
                for dx in range(ss):
                    i = ((y * ss + dy) * s + (x * ss + dx)) * 4
                    ar += buf[i]; ag += buf[i + 1]; ab += buf[i + 2]; aa += buf[i + 3]
            if aa > 0:
                o = (y * size + x) * 4
                out[o] = min(255, int(ar / aa * 255 + 0.5))
                out[o + 1] = min(255, int(ag / aa * 255 + 0.5))
                out[o + 2] = min(255, int(ab / aa * 255 + 0.5))
                out[o + 3] = min(255, int(aa * inv + 0.5))
    return bytes(out)


def png(size, rgba):
    raw = b"".join(b"\x00" + rgba[y * size * 4:(y + 1) * size * 4]
                   for y in range(size))
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def dib(size, rgba):
    hdr = struct.pack("<IiiHHIIiiII", 40, size, 2 * size,
                      1, 32, 0, 0, 0, 0, 0, 0)
    xor = bytearray()
    for y in range(size - 1, -1, -1):          # DIB 自下而上
        row = rgba[y * size * 4:(y + 1) * size * 4]
        for i in range(0, len(row), 4):
            r, g, b, a = row[i:i + 4]
            xor += bytes((b, g, r, a))         # BGRA
    stride = ((size + 31) // 32) * 4
    return hdr + bytes(xor) + b"\x00" * (stride * size)


def ico(entries, path):
    n = len(entries)
    out = bytearray(struct.pack("<HHH", 0, 1, n))
    offset = 6 + 16 * n
    meta = []
    for size, data in entries:
        meta.append((size, len(data), offset))
        offset += len(data)
    for size, length, off in meta:
        b = size % 256                          # 256 记为 0
        out += struct.pack("<BBBBHHII", b, b, 0, 0, 1, 32, length, off)
    for _size, data in entries:
        out += data
    with open(path, "wb") as f:
        f.write(out)


def main():
    os.makedirs(ASSETS, exist_ok=True)
    sizes = [16, 24, 32, 40, 48, 64, 128, 256]
    entries = []
    big = None
    for s in sizes:
        rgba = render(s)
        entries.append((s, dib(s, rgba)))
        if s == 256:
            big = rgba
    ico(entries, os.path.join(ASSETS, "pojia-modifier.ico"))
    with open(os.path.join(ASSETS, "icon-preview.png"), "wb") as f:
        f.write(png(256, big))
    for name in ("pojia-modifier.ico", "icon-preview.png"):
        p = os.path.join(ASSETS, name)
        print("[icon] %s  %d bytes" % (p, os.path.getsize(p)))


if __name__ == "__main__":
    main()
