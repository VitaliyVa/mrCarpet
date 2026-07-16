"""Build a carpet GLB (flat plane + embedded texture). Port of testAr/make-glb.js."""

from __future__ import annotations

import json
import struct
from typing import Literal

AlphaMode = Literal["auto", "opaque", "mask", "blend", "OPAQUE", "MASK", "BLEND"]

LIFT = 0.005  # metres above floor — avoid z-fighting
PNG_SIG = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])


def detect_image(buf: bytes) -> tuple[str, bool]:
    """Return (mime_type, has_alpha)."""
    if len(buf) >= 8 and buf[:8] == PNG_SIG:
        # IHDR colorType at offset 25
        color_type = buf[25] if len(buf) > 25 else 0
        has_alpha = color_type in (4, 6)  # GA / RGBA
        if color_type == 3:
            offset = 8
            while offset + 12 <= len(buf):
                length = struct.unpack(">I", buf[offset : offset + 4])[0]
                chunk = buf[offset + 4 : offset + 8]
                if chunk == b"tRNS":
                    has_alpha = True
                    break
                if chunk in (b"IDAT", b"IEND"):
                    break
                offset += 12 + length
        return "image/png", has_alpha
    if len(buf) >= 2 and buf[0] == 0xFF and buf[1] == 0xD8:
        return "image/jpeg", False
    # fallback by sniffing
    if buf[:4] == b"RIFF":
        return "image/webp", False
    return "image/jpeg", False


def _resolve_alpha_mode(mode: str, has_alpha: bool) -> str:
    m = (mode or "auto").lower()
    if m == "auto":
        return "BLEND" if has_alpha else "OPAQUE"
    if m in ("opaque", "mask", "blend"):
        return m.upper()
    raise ValueError(f"Невідомий alphaMode {mode!r}. Дозволено: auto|opaque|mask|blend")


def _f32(arr: list[float]) -> bytes:
    return struct.pack(f"<{len(arr)}f", *arr)


def _u16(arr: list[int]) -> bytes:
    return struct.pack(f"<{len(arr)}H", *arr)


def _pad4(data: bytes, fill: int = 0x00) -> bytes:
    rem = len(data) % 4
    if rem == 0:
        return data
    return data + bytes([fill]) * (4 - rem)


def build_carpet_glb(
    texture_bytes: bytes,
    width_m: float,
    length_m: float,
    alpha_mode: AlphaMode = "auto",
) -> bytes:
    """
    Create a double-sided carpet plane on XZ with texture.

    width_m → axis X, length_m → axis Z. Units are metres (glTF).
    """
    w = float(width_m)
    length = float(length_m)
    if w <= 0 or length <= 0:
        raise ValueError("width_m і length_m мають бути > 0")

    mime_type, has_alpha = detect_image(texture_bytes)
    resolved_alpha = _resolve_alpha_mode(alpha_mode, has_alpha)

    hx, hz, y = w / 2.0, length / 2.0, LIFT
    positions = [-hx, y, -hz, hx, y, -hz, hx, y, hz, -hx, y, hz]
    normals = [0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0]
    uvs = [0, 1, 1, 1, 1, 0, 0, 0]
    indices = [0, 2, 1, 0, 3, 2]
    pos_min = [-hx, y, -hz]
    pos_max = [hx, y, hz]

    pos_buf = _f32(positions)
    norm_buf = _f32(normals)
    uv_buf = _f32(uvs)
    idx_buf = _pad4(_u16(indices))
    img_buf = texture_bytes

    offset = 0
    pos_off = offset
    offset += len(pos_buf)
    norm_off = offset
    offset += len(norm_buf)
    uv_off = offset
    offset += len(uv_buf)
    idx_off = offset
    offset += len(idx_buf)
    img_off = offset
    offset += len(img_buf)
    bin_length = offset
    binary = pos_buf + norm_buf + uv_buf + idx_buf + img_buf

    material: dict = {
        "name": "carpet",
        "pbrMetallicRoughness": {
            "baseColorTexture": {"index": 0},
            "metallicFactor": 0,
            "roughnessFactor": 0.9,
        },
        "doubleSided": True,
    }
    if resolved_alpha == "MASK":
        material["alphaMode"] = "MASK"
        material["alphaCutoff"] = 0.5
    elif resolved_alpha == "BLEND":
        material["alphaMode"] = "BLEND"

    gltf = {
        "asset": {"version": "2.0", "generator": "mrCarpet make_glb"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "carpet"}],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {
                            "POSITION": 0,
                            "NORMAL": 1,
                            "TEXCOORD_0": 2,
                        },
                        "indices": 3,
                        "material": 0,
                    }
                ]
            }
        ],
        "materials": [material],
        "textures": [{"sampler": 0, "source": 0}],
        "images": [{"bufferView": 4, "mimeType": mime_type}],
        "samplers": [
            {"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 4,
                "type": "VEC3",
                "min": pos_min,
                "max": pos_max,
            },
            {"bufferView": 1, "componentType": 5126, "count": 4, "type": "VEC3"},
            {"bufferView": 2, "componentType": 5126, "count": 4, "type": "VEC2"},
            {"bufferView": 3, "componentType": 5123, "count": 6, "type": "SCALAR"},
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": pos_off, "byteLength": len(pos_buf), "target": 34962},
            {"buffer": 0, "byteOffset": norm_off, "byteLength": len(norm_buf), "target": 34962},
            {"buffer": 0, "byteOffset": uv_off, "byteLength": len(uv_buf), "target": 34962},
            {"buffer": 0, "byteOffset": idx_off, "byteLength": len(idx_buf), "target": 34963},
            {"buffer": 0, "byteOffset": img_off, "byteLength": len(img_buf)},
        ],
        "buffers": [{"byteLength": bin_length}],
    }

    json_chunk = _pad4(json.dumps(gltf, separators=(",", ":")).encode("utf-8"), 0x20)
    bin_chunk_data = _pad4(binary, 0x00)

    json_header = struct.pack("<I", len(json_chunk)) + b"JSON"
    bin_header = struct.pack("<I", len(bin_chunk_data)) + b"BIN\x00"

    total = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk_data)
    header = b"glTF" + struct.pack("<II", 2, total)

    return header + json_header + json_chunk + bin_header + bin_chunk_data
