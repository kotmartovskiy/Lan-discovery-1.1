#!/usr/bin/env python3
"""Генерация простых PNG-иконок для аддонов (без Pillow, только stdlib).

Использование: make_icons.py <wifi_icon.png> <sdr_icon.png>
"""
import struct
import sys
import zlib


def write_png(path, width, height, pixels):
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b""
    for y in range(height):
        raw += b"\x00"
        for x in range(width):
            r, g, b = pixels[y][x]
            raw += bytes((r, g, b))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", ihdr))
        f.write(chunk(b"IDAT", zlib.compress(raw, 9)))
        f.write(chunk(b"IEND", b""))


def wifi_icon(size=256):
    cx, cy = size // 2, int(size * 0.82)
    bg = (13, 42, 86)
    fg = (235, 245, 255)
    rings = [(int(size * 0.16), 7), (int(size * 0.30), 8), (int(size * 0.44), 9)]
    px = [[bg for _ in range(size)] for _ in range(size)]
    for y in range(size):
        for x in range(size):
            dx, dy = x - cx, y - cy
            if dy > 4:
                continue
            d = (dx * dx + dy * dy) ** 0.5
            for r, w in rings:
                if abs(d - r) <= w:
                    px[y][x] = fg
                    break
            if d <= int(size * 0.06):
                px[y][x] = fg
    return px


def sdr_icon(size=256):
    bg = (24, 12, 48)
    bars = (0, 220, 160)
    px = [[bg for _ in range(size)] for _ in range(size)]
    n_bars = 22
    bw = size // n_bars
    for i in range(n_bars):
        h = int(size * (0.25 + 0.55 * abs(((i * 37) % 17) / 16.0 * ((i * 13) % 11) / 10.0)))
        x0 = i * bw + 3
        for y in range(size // 2 + size // 4 - h, min(size // 2 + size // 4, size - 8)):
            for x in range(x0, min(x0 + bw - 6, size)):
                px[y][x] = bars
    return px


def retro_icon(size=256):
    bg = (16, 28, 16)
    body = (200, 200, 205)
    dark = (40, 40, 45)
    accent = (230, 80, 60)
    px = [[bg for _ in range(size)] for _ in range(size)]
    x0, x1 = int(size * 0.12), int(size * 0.88)
    y0, y1 = int(size * 0.32), int(size * 0.62)
    for y in range(size):
        for x in range(size):
            if x0 <= x < x1 and y0 <= y < y1:
                px[y][x] = body
            if x0 - 14 <= x < x0 and int(size * 0.42) <= y < y1 + 14:
                px[y][x] = body
    cx, cy = int(size * 0.24), (y0 + y1) // 2
    for y in range(cy - 7, cy + 8):
        for x in range(cx - 22, cx + 23):
            if y < cy - 3 or y > cy + 3:
                px[y][x] = dark
    for y in range(cy - 22, cy + 23):
        for x in range(cx - 7, cx + 8):
            if x < cx - 3 or x > cx + 3:
                px[y][x] = dark
    for (bx, by) in ((int(size * 0.62), int(size * 0.42)), (int(size * 0.74), int(size * 0.42)),
                     (int(size * 0.68), int(size * 0.34)), (int(size * 0.68), int(size * 0.50))):
        for y in range(by - 10, by + 11):
            for x in range(bx - 10, bx + 11):
                if (x - bx) ** 2 + (y - by) ** 2 <= 100:
                    px[y][x] = accent
    return px


def main():
    if len(sys.argv) != 4:
        sys.exit("usage: make_icons.py <wifi.png> <sdr.png> <retro.png>")
    write_png(sys.argv[1], 256, 256, wifi_icon())
    write_png(sys.argv[2], 256, 256, sdr_icon())
    write_png(sys.argv[3], 256, 256, retro_icon())
    print("icons ok")


if __name__ == "__main__":
    main()
