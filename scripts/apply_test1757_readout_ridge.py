"""Reproduce one experimental test1757 NNUE bias edit with Python's stdlib.

Original network: Shawn Xu (xu-shawn), test1757. Stockfish contributors retain
their upstream credit. Lab recipe and applier: 0mis/stockfish-weight-space-lab,
GPL-3.0-or-later; the original upstream network is CC0. No Elo gain is claimed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile


RECIPE_SHA256 = "4ce6d12f6f79eb7462569e771e86ce1e27ee715d2801605f295dc1dcc0a804d3"
RECIPE = Path(__file__).resolve().parents[1] / "nets/test1757-readout-ridge.json"
WORD = struct.Struct("<i")
BLOCK = 1024 * 1024


def require(ok, message):
    if not ok:
        raise ValueError(message)


def integer(value):
    return type(value) is int


def digest(stream):
    result = hashlib.sha256()
    while block := stream.read(BLOCK):
        result.update(block)
    return result.hexdigest()


def recipe(path):
    raw = Path(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == RECIPE_SHA256, "Recipe SHA-256 differs")
    doc = json.loads(raw)
    require(doc["schema"] == "test1757-readout-ridge-bias-recipe-v1", "Wrong recipe schema")
    require(doc["physical_head_count"] == len(doc["heads"]) == 92 and doc["raw_route_count"] == 192, "Wrong head/route count")
    require(integer(doc["bytes"]) and doc["bytes"] > 0, "Wrong network byte count")
    last_end, routes, changed_heads, changed_bytes = 0, [], 0, 0
    for index, head in enumerate(doc["heads"]):
        require(head["physical_head"] == index and integer(head["physical_head"]), "Wrong physical-head order")
        offset, before, after, delta = (head[key] for key in ("bias_offset", "bias_before", "bias_after", "delta"))
        require(all(integer(value) for value in (offset, before, after, delta)), "Noninteger bias record")
        require(last_end <= offset <= doc["bytes"] - 4, "Overlapping or out-of-range bias")
        require(-(1 << 31) <= before < (1 << 31) and -(1 << 31) <= after < (1 << 31), "Bias overflows signed int32")
        require(after - before == delta and -256 <= delta <= 256 and delta % 16 == 0, "Wrong frozen bias delta")
        expected = [{"offset": offset + i, "before": old, "after": new}
                    for i, (old, new) in enumerate(zip(WORD.pack(before), WORD.pack(after))) if old != new]
        require(head["changed_bytes"] == expected, "Changed-byte declaration differs")
        require(all(integer(value) and 0 <= value < 192 for value in head["raw_routes"])
                and head["raw_routes"] == sorted(set(head["raw_routes"])), "Invalid head raw routes")
        routes.extend(head["raw_routes"])
        changed_heads += bool(delta)
        changed_bytes += len(expected)
        last_end = offset + 4
    require(sorted(routes) == list(range(192)), "Raw routes are missing or duplicated")
    require(changed_heads == doc["changed_head_count"] == 9 and changed_bytes == doc["changed_byte_count"], "Changed head/byte count differs")
    return doc


def transformed(source, doc, reverse):
    position = 0
    for head in doc["heads"]:
        remaining = head["bias_offset"] - position
        while remaining:
            block = source.read(min(remaining, BLOCK))
            require(block, "Source ended before a bias")
            yield block
            remaining -= len(block)
            position += len(block)
        before = head["bias_after" if reverse else "bias_before"]
        after = head["bias_before" if reverse else "bias_after"]
        require(source.read(4) == WORD.pack(before), "Source bias differs")
        yield WORD.pack(after)
        position += 4
    remaining = doc["bytes"] - position
    while remaining:
        block = source.read(min(remaining, BLOCK))
        require(block, "Source ended after the final bias")
        yield block
        remaining -= len(block)
    require(source.read(1) == b"", "Source has trailing bytes")


def reproduce(source_path, output_path=None, *, reverse=False, recipe_path=RECIPE):
    doc = recipe(recipe_path)
    source_path = Path(source_path)
    output = None if output_path is None else Path(output_path)
    require(output is None or not (output.exists() or output.is_symlink()), "Output already exists")
    expected_source = doc["candidate_sha256" if reverse else "parent_sha256"]
    expected_target = doc["parent_sha256" if reverse else "candidate_sha256"]
    with source_path.open("rb") as source:
        require(os.fstat(source.fileno()).st_size == doc["bytes"], "Source byte count differs")
        require(digest(source) == expected_source, "Source SHA-256 differs")
        source.seek(0)
        computed = hashlib.sha256()
        count = 0
        if output is None:
            for block in transformed(source, doc, reverse):
                computed.update(block)
                count += len(block)
        else:
            # Stage beside the output; os.link publishes exclusively and cannot
            # overwrite an existing path. No source file is ever opened to write.
            with tempfile.TemporaryDirectory(dir=output.parent, prefix=".readout-ridge-") as temporary:
                staged = Path(temporary) / "network"
                with staged.open("xb") as target:
                    for block in transformed(source, doc, reverse):
                        target.write(block)
                        computed.update(block)
                        count += len(block)
                require(count == doc["bytes"] and computed.hexdigest() == expected_target, "Target size or SHA-256 differs")
                os.link(staged, output)
        require(count == doc["bytes"] and computed.hexdigest() == expected_target, "Target size or SHA-256 differs")
    return {"source_sha256": expected_source, "target_sha256": expected_target, "bytes": count,
            "physical_heads": 92, "changed_heads": doc["changed_head_count"], "changed_bytes": doc["changed_byte_count"],
            "reverse": reverse, "output_written": output is not None, "verified_gain": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Exact original network, or exact candidate with --reverse")
    parser.add_argument("output", type=Path, nargs="?", help="New output path; must not exist")
    parser.add_argument("--reverse", action="store_true", help="Restore the exact original network")
    parser.add_argument("--verify-only", action="store_true", help="Compute and verify the target hash without writing a network")
    args = parser.parse_args()
    if (args.output is None) != args.verify_only:
        parser.error("provide one output path or --verify-only")
    print(json.dumps(reproduce(args.source, args.output, reverse=args.reverse), sort_keys=True))
