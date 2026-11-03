"""Recheck the completed experiment against its saved evidence."""

import json
import platform
import sys

import chess

from lab import (ENGINE, FASTCHESS, ROOT, file_hash, read_json, utc,
                 validate_net, validate_splits, verify_saved_match, write_json)


def main():
    validate_splits()
    result = read_json(ROOT / "results/experiment-summary.json")
    config = read_json(ROOT / "experiment.json")
    expected = {"engine_sha256": file_hash(ENGINE),
                "fastchess_sha256": file_hash(FASTCHESS),
                "experiment_sha256": file_hash(ROOT / "experiment.json")}
    records = [result["control"], *result["screens"], result["confirmation"]]
    count = 0
    for record in records:
        identity = record["identity"]
        name, phase = identity["candidate"], identity["phase"]
        directory = ROOT / "results" / f"{phase}-{name}"
        if read_json(directory / "summary.json") != record:
            raise ValueError("Top-level result differs from the per-match record")
        for key, value in expected.items():
            if identity[key] != value:
                raise ValueError(f"Provenance mismatch: {key}")
        net = validate_net("original" if identity["control_identical_networks"] else name)
        opening = ROOT / f"openings/{phase}.epd"
        if identity["candidate_sha256"] != file_hash(net):
            raise ValueError("Candidate hash mismatch")
        if identity["baseline_sha256"] != file_hash(validate_net("original")):
            raise ValueError("Baseline hash mismatch")
        if identity["opening_sha256"] != file_hash(opening):
            raise ValueError("Opening hash mismatch")
        verify_saved_match(record, directory / "games.pgn", name, identity["pairs"], opening)
        count += record["stats"]["games"]
    selected = max(result["screens"], key=lambda r: r["stats"]["score_fraction"])["identity"]["candidate"]
    if result["selected"] != selected or read_json(ROOT / "results/selection.json")["selected"] != selected:
        raise ValueError("Selection does not follow the frozen score rule")
    expected_games = 8 + 2 * len(config["candidates"]) * config["protocol"]["screen_pairs_per_candidate"] + 2 * config["protocol"]["confirmation_pairs"]
    if count != expected_games:
        raise ValueError("Unexpected number of games")
    smoke = read_json(ROOT / "results/smoke/summary.json")["results"]
    for name, record in smoke.items():
        if not record["engine_roundtrip_identical"] or record["sha256"] != file_hash(validate_net(name)):
            raise ValueError("Native-engine round-trip record mismatch")
    audit = {"audited_utc": utc(), "passed": True, "matches": len(records), "games": count,
             "checks": ["saved PGN SHA256 hashes", "game counts and completed results",
                        "declared openings and reversed-color pairs", "disjoint opening splits",
                        "recomputed paired statistics", "native network round trips",
                        "current executable/network/protocol hashes", "frozen selection rule"],
             "python": sys.version, "platform": platform.platform(), "chess": chess.__version__,
             "source_sha256": {str(p.relative_to(ROOT)): file_hash(p)
                               for p in [ROOT / "scripts/nnue.py", ROOT / "scripts/lab.py", ROOT / "scripts/audit.py"]}}
    write_json(ROOT / "results/audit.json", audit)
    print(json.dumps({"passed": True, "matches": len(records), "games": count}), flush=True)


if __name__ == "__main__":
    main()
