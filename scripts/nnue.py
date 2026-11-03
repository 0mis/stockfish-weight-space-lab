"""Architecture-checked, byte-preserving editor for Stockfish 19 / SFNNv16.

Serialization and hashes follow the source included with the official sf_19
release. Feature-transformer payloads are copied verbatim, never dequantized.
This parser intentionally rejects other architectures. It checks section
boundaries and compressed byte-size envelopes, not every LEB128 integer. Use
the pinned baseline hash and native-engine round trip for payload validation.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct

MASK = 0xFFFFFFFF
VERSION = 0x6A448AFA
MAGIC = b"COMPRESSED_LEB128"
STACKS = 8
THREATS = 59808
PAIRS = 96 * 95 // 2
PSQ = 64 * (11 * 64) // 2
L1, L2, L3 = 1024, 32, 32
STACK_BYTES = 4 + (4 * L2 + L1 * L2) + (4 * L3 + 2 * L2 * L3) + 4 + 128
BASELINE_SHA256 = "1a298aa575a085434d29027978dc36867fe9c5bcea9376654b7a8eba1e52dfc2"


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def affine_hash(previous: int, outputs: int) -> int:
    return ((0xCC03DAE4 + outputs) ^ (previous >> 1) ^ (previous << 31)) & MASK


def architecture_hash() -> int:
    h = affine_hash(0xEC42E90D ^ (L1 * 2), L2)
    h = (h + 0x538D24C7) & MASK
    h = affine_hash(h, L3)
    h = (h + 0x538D24C7) & MASK
    return affine_hash(h, 1)


def transformer_hash() -> int:
    h = 0
    for component in (0x2E6B9D04, 0x86F2B1DD, 0x7F234CB8):
        h = (((h << 1) | (h >> 31)) ^ component) & MASK
    return h ^ (L1 * 2)


@dataclass(frozen=True)
class OutputLayer:
    bucket: int
    bias_offset: int
    weights_offset: int
    bias: int
    weights: tuple[int, ...]


class Network:
    def __init__(self, data: bytes):
        self.data = data
        self.layers: list[OutputLayer] = []
        self.sections: list[dict] = []
        self._parse()

    @classmethod
    def load(cls, path: str | Path) -> Network:
        return cls(Path(path).read_bytes())

    def _require(self, condition: bool, message: str) -> None:
        if not condition:
            raise ValueError(message)

    def _parse(self) -> None:
        b = self.data
        self._require(len(b) >= 12, "Truncated NNUE header")
        version, header_hash, description_size = struct.unpack_from("<III", b)
        self._require(version == VERSION, "Unsupported NNUE version; expected Stockfish 19")
        self._require(header_hash == (transformer_hash() ^ architecture_hash()),
                      "Unsupported NNUE architecture hash")
        self._require(description_size <= 1048576, "Invalid description size")
        pos = 12 + description_size
        self._require(pos + 4 <= len(b), "Truncated NNUE description")
        self.description = b[12:pos].decode("utf-8")
        self._require(struct.unpack_from("<I", b, pos)[0] == transformer_hash(),
                      "Wrong feature-transformer hash")
        pos += 4

        def raw(name: str, size: int) -> None:
            nonlocal pos
            self._require(pos + size <= len(b), f"Truncated {name}")
            self.sections.append({"name": name, "offset": pos, "bytes": size})
            pos += size

        def compressed(name: str, count: int, width: int) -> None:
            nonlocal pos
            self._require(b[pos:pos + len(MAGIC)] == MAGIC, f"Missing LEB128 marker: {name}")
            pos += len(MAGIC)
            self._require(pos + 4 <= len(b), f"Truncated LEB128 length: {name}")
            size = struct.unpack_from("<I", b, pos)[0]
            pos += 4
            # Each integer needs at least 1 and at most ceil(width / 7) bytes.
            self._require(count <= size <= count * ((width + 6) // 7),
                          f"Invalid compressed payload size: {name}")
            raw(name, size)

        compressed("ft.biases", L1, 16)
        raw("ft.threat_weights", THREATS * L1)
        compressed("ft.threat_psqt", THREATS * STACKS, 32)
        raw("ft.pawn_pair_weights", PAIRS * L1)
        compressed("ft.pawn_pair_psqt", PAIRS * STACKS, 32)
        compressed("ft.psq_weights", PSQ * L1, 16)
        compressed("ft.psqt", PSQ * STACKS, 32)
        self.stacks_offset = pos
        self._require(pos + STACK_BYTES * STACKS == len(b), "Unexpected NNUE stack size or trailing data")
        for bucket in range(STACKS):
            start = pos + bucket * STACK_BYTES
            self._require(struct.unpack_from("<I", b, start)[0] == architecture_hash(),
                          f"Wrong stack hash at bucket {bucket}")
            offset = start + 4 + (4 * L2 + L1 * L2) + (4 * L3 + 2 * L2 * L3)
            self.layers.append(OutputLayer(bucket, offset, offset + 4,
                                           struct.unpack_from("<i", b, offset)[0],
                                           struct.unpack_from("<128b", b, offset + 4)))

    def edit_biases(self, deltas: list[int]) -> tuple[bytes, list[dict]]:
        self._require(len(deltas) == STACKS, "One bias delta required per bucket")
        result = bytearray(self.data)
        edits = []
        for layer, delta in zip(self.layers, deltas):
            self._require(type(delta) is int, "Bias deltas must be integers")
            if delta:
                new = layer.bias + delta
                self._require(-(2**31) <= new < 2**31, "Bias overflow")
                struct.pack_into("<i", result, layer.bias_offset, new)
                edits.append({"parameter": f"stack[{layer.bucket}].fc_2.bias[0]",
                              "offset": layer.bias_offset, "type": "int32_le",
                              "old": layer.bias, "new": new, "delta": delta})
        Network(bytes(result))
        # Audit entire buffers in C, retaining only the explicitly edited fields.
        restored = bytearray(result)
        for edit in edits:
            struct.pack_into("<i", restored, edit["offset"], edit["old"])
        self._require(restored == self.data, "Unexpected bytes changed outside requested parameters")
        return bytes(result), edits

    def inspect(self) -> dict:
        total_parameters = (L1 + (THREATS + PAIRS) * (L1 + STACKS)
                            + PSQ * (L1 + STACKS)
                            + STACKS * (L2 + L1 * L2 + L3 + 2 * L2 * L3 + 1 + 128))
        return {"format": "Stockfish 19 / SFNNv16", "sha256": sha256(self.data),
                "bytes": len(self.data), "description": self.description,
                "architecture_hash": hex(architecture_hash()),
                "parameter_count": total_parameters,
                "stacks_offset": self.stacks_offset, "sections": self.sections,
                "output_layers": [{"bucket": x.bucket, "piece_count_range": [max(2, 4*x.bucket+1), 4*x.bucket+4],
                                   "bias_offset": x.bias_offset, "bias": x.bias,
                                   "weights": list(x.weights)} for x in self.layers]}
