# generate_icon.py
import struct
import zlib

def make_png(width, height):
    raw_data = bytearray()
    for y in range(height):
        raw_data.append(0)
        for x in range(width):
            is_edge = x in (0, width - 1) or y in (0, height - 1)
            is_carat = abs((width // 2) - x) == abs(y - (height // 3)) and y > height // 4
            if is_edge:
                raw_data.extend((30, 41, 59, 255))
            elif is_carat:
                raw_data.extend((56, 189, 248, 255))
            else:
                raw_data.extend((15, 23, 42, 255))

    def chunk(tag, data):
        return struct.pack("!I", len(data)) + tag + data + struct.pack("!I", zlib.crc32(tag + data) & 0xffffffff)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack("!IIBBBBB", width, height, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw_data, 9))
    png += chunk(b"IEND", b"")
    return png

with open("assets/icon.png", "wb") as f:
    f.write(make_png(64, 64))
print("assets/icon.png generated.")