"""A bounded, reproducible direct-weight-editing experiment. No training code."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import platform
import random
import re
import statistics
import subprocess
import time

import chess
import chess.pgn

from nnue import BASELINE_SHA256, Network, sha256

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "vendor/stockfish/stockfish/stockfish-windows-x86-64-universal.exe"
FASTCHESS = ROOT / "vendor/fastchess/fastchess-windows-x86-64/fastchess.exe"
FLAGS = (subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS) if platform.system() == "Windows" else 0


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        import hashlib
        return hashlib.file_digest(stream, "sha256").hexdigest()


def checked_write(path: Path, data: bytes) -> None:
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"Refusing to replace different existing artifact: {path}")
    else:
        path.write_bytes(data)


def prepare() -> dict:
    config = read_json(ROOT / "experiment.json")
    baseline = Network.load(ROOT / "nets/original.nnue")
    if sha256(baseline.data) != BASELINE_SHA256 or config["baseline_sha256"] != BASELINE_SHA256:
        raise ValueError("The original network differs from the pinned Stockfish 19 network")
    write_json(ROOT / "nets/original-inspection.json", baseline.inspect())
    manifests = {}
    for candidate in config["candidates"]:
        data, edits = baseline.edit_biases(candidate["bias_deltas"])
        name = candidate["name"]
        if not re.fullmatch(r"[a-z0-9-]+", name):
            raise ValueError("Invalid candidate name")
        checked_write(ROOT / f"nets/{name}.nnue", data)
        manifest = {"name": name, "parent_sha256": BASELINE_SHA256,
                    "sha256": sha256(data), "changed_parameters": len(edits),
                    "total_parameters": baseline.inspect()["parameter_count"],
                    "edits": edits, "hypothesis": config["hypothesis"],
                    "method": config["method"]}
        write_json(ROOT / f"nets/{name}.json", manifest)
        manifests[name] = manifest

    source = ROOT / "openings/source/8moves_v3.pgn"
    split_path = ROOT / "openings/split.json"
    if not split_path.exists():
        unique = {}
        with source.open(encoding="utf-8-sig") as stream:
            while (game := chess.pgn.read_game(stream)) is not None:
                if game.errors:
                    raise ValueError(f"Invalid book game: {game.errors}")
                board = game.end().board()
                if not board.is_valid() or board.is_game_over():
                    continue
                key = " ".join(board.fen().split()[:4])
                unique[key] = key
        positions = sorted(unique)
        random.Random(config["protocol"]["seed"]).shuffle(positions)
        counts = {"screen": config["protocol"]["screen_pairs_per_candidate"],
                  "confirmation": config["protocol"]["confirmation_pairs"], "control": 4}
        if len(positions) < sum(counts.values()):
            raise ValueError("Not enough distinct book positions")
        cursor = 0
        splits = {}
        for label, count in counts.items():
            selected = positions[cursor:cursor + count]
            cursor += count
            data = ("\n".join(selected) + "\n").encode()
            checked_write(ROOT / f"openings/{label}.epd", data)
            splits[label] = {"positions": count, "sha256": sha256(data)}
        write_json(split_path, {"created_utc": utc(), "source": read_json(ROOT / "research/book-source.json"),
                               "source_pgn_sha256": file_hash(source),
                               "seed": config["protocol"]["seed"], "unique_source_positions": len(positions),
                               "splits": splits, "disjoint": True})
    validate_splits()
    print(json.dumps({"prepared": {name: {"sha256": item["sha256"], "changed_parameters": item["changed_parameters"]}
                                   for name, item in manifests.items()},
                      "openings": read_json(split_path)["splits"]}), flush=True)
    return manifests


def validate_splits() -> None:
    split = read_json(ROOT / "openings/split.json")
    seen = set()
    for label, item in split["splits"].items():
        path = ROOT / f"openings/{label}.epd"
        if file_hash(path) != item["sha256"]:
            raise ValueError(f"Opening split changed: {label}")
        positions = path.read_text().splitlines()
        if len(positions) != item["positions"] or len(set(positions)) != len(positions):
            raise ValueError("Opening count or uniqueness mismatch")
        if seen.intersection(positions):
            raise ValueError("Opening splits overlap")
        seen.update(positions)


def validate_net(name: str) -> Path:
    if name == "original":
        expected = BASELINE_SHA256
    else:
        expected = read_json(ROOT / f"nets/{name}.json")["sha256"]
    path = ROOT / f"nets/{name}.nnue"
    if file_hash(path) != expected:
        raise ValueError(f"Network changed since preparation: {name}")
    return path


def smoke() -> dict:
    config = read_json(ROOT / "experiment.json")
    directory = ROOT / "results/smoke"
    directory.mkdir(parents=True, exist_ok=True)
    outcomes = {}
    for name in ["original"] + [x["name"] for x in config["candidates"]]:
        net = validate_net(name)
        exported = directory / f"{name}-roundtrip.nnue"
        commands = (f"uci\nsetoption name EvalFile value {net}\n"
                    f"export_net {exported}\nposition startpos\neval\nquit\n")
        result = subprocess.run([str(ENGINE)], input=commands, text=True,
                                capture_output=True, cwd=ROOT, timeout=45, creationflags=FLAGS)
        (directory / f"{name}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode or "Network saved successfully" not in result.stdout:
            raise RuntimeError(f"Stockfish rejected {name}; see smoke log")
        if file_hash(exported) != file_hash(net):
            raise ValueError(f"Engine serialization round trip changed {name}")
        exported.unlink()
        score = re.search(r"NNUE evaluation\s+([+-]?\d+) \(side to move, internal units\)", result.stdout)
        if not score:
            raise RuntimeError("Missing static evaluation")
        outcomes[name] = {"sha256": file_hash(net), "engine_roundtrip_identical": True,
                          "startpos_nnue_internal": int(score.group(1))}
    original_score = outcomes["original"]["startpos_nnue_internal"]
    if not (outcomes["initiative-plus"]["startpos_nnue_internal"] > original_score
            > outcomes["initiative-minus"]["startpos_nnue_internal"]):
        raise ValueError("The bias edits did not produce their expected static evaluation effect")
    write_json(directory / "summary.json", {"created_utc": utc(), "results": outcomes})
    print(json.dumps(outcomes), flush=True)
    return outcomes


def paired_summary(scores: list[float], seed: int = 7301) -> dict:
    if not scores:
        raise ValueError("No game pairs")
    n = len(scores)
    rng = random.Random(seed)
    # Resample opening pairs, never individual games: colors share an opening.
    bootstrap = sorted(sum(rng.choices(scores, k=n)) / n for _ in range(20000))
    low, high = bootstrap[499], bootstrap[19499]
    mean = statistics.mean(scores)

    def elo(score: float):
        if 0 < score < 1:
            return 400 * math.log10(score / (1 - score))
        return None

    return {"pairs": n, "score_fraction": mean, "score_ci95_pair_bootstrap": [low, high],
            "relative_logistic_elo": elo(mean), "relative_elo_ci95_pair_bootstrap": [elo(low), elo(high)],
            "pentanomial": [sum(x == i / 4 for x in scores) for i in range(5)],
            "positive_exploratory_signal": low > 0.5,
            "interval_method": "Approximate percentile bootstrap, 20000 resamples of opening pairs; small-sample and selection limits apply."}


def summarize_pgn(path: Path, candidate: str, expected_pairs: int, opening_path: Path) -> dict:
    allowed = {" ".join(x.split()[:4]) for x in opening_path.read_text().splitlines()}
    pairs = defaultdict(list)
    wdl = Counter()
    terminations = Counter()
    games = 0
    with path.open(encoding="utf-8-sig") as stream:
        while (game := chess.pgn.read_game(stream)) is not None:
            if game.errors:
                raise ValueError(f"Invalid match PGN: {game.errors}")
            headers = game.headers
            if set((headers["White"], headers["Black"])) != {candidate, "baseline"}:
                raise ValueError("Unexpected players")
            result = headers.get("Result")
            if result not in ("1-0", "0-1", "1/2-1/2"):
                raise ValueError("Unfinished game")
            outcome = game.end().board().outcome(claim_draw=True)
            if outcome is None or outcome.result() != result:
                raise ValueError("PGN result is not supported by the final board")
            termination = headers.get("Termination", "unspecified")
            if re.search(r"time|stall|disconnect|illegal|crash|abandon|error", termination, re.I):
                raise ValueError(f"Invalid engine match termination: {termination}")
            terminations[termination] += 1
            candidate_white = headers["White"] == candidate
            white_score = {"1-0": 1, "0-1": 0, "1/2-1/2": 0.5}[result]
            score = white_score if candidate_white else 1 - white_score
            key = " ".join(game.board().fen().split()[:4])
            if key not in allowed:
                raise ValueError("Game did not use a declared opening")
            pairs[key].append((candidate_white, score))
            wdl[{1: "wins", 0.5: "draws", 0: "losses"}[score]] += 1
            games += 1
    if games != expected_pairs * 2 or len(pairs) != expected_pairs:
        raise ValueError(f"Incomplete match: {games} games, {len(pairs)} openings")
    pair_scores = []
    for entries in pairs.values():
        if len(entries) != 2 or {white for white, score in entries} != {True, False}:
            raise ValueError("Each opening must be played exactly twice with colors reversed")
        pair_scores.append(sum(score for white, score in entries) / 2)
    return {"games": games, "wins": wdl["wins"], "draws": wdl["draws"], "losses": wdl["losses"],
            "terminations": dict(terminations), **paired_summary(pair_scores)}


def verify_saved_match(summary: dict, pgn_path: Path, candidate: str,
                       expected_pairs: int, opening_path: Path) -> None:
    if summary["pgn_sha256"] != file_hash(pgn_path):
        raise ValueError("Saved PGN hash differs from the completed match")
    if summary["stats"] != summarize_pgn(pgn_path, candidate, expected_pairs, opening_path):
        raise ValueError("Saved summary differs from PGN")


def run_match(name: str, phase: str, pairs: int, nodes: int, control: bool = False) -> dict:
    validate_splits()
    protocol = read_json(ROOT / "experiment.json")["protocol"]
    threads = protocol["threads_per_engine"]
    hash_mb = protocol["hash_mb_per_engine"]
    concurrency = protocol["concurrency"]
    baseline = validate_net("original")
    candidate = validate_net("original" if control else name)
    directory = ROOT / "results" / f"{phase}-{name}"
    directory.mkdir(parents=True, exist_ok=True)
    summary_path = directory / "summary.json"
    opening_path = ROOT / f"openings/{phase}.epd"
    identity = {"candidate": name, "phase": phase, "pairs": pairs, "nodes_per_move": nodes,
                "candidate_sha256": file_hash(candidate), "baseline_sha256": file_hash(baseline),
                "opening_sha256": file_hash(opening_path), "engine_sha256": file_hash(ENGINE),
                "fastchess_sha256": file_hash(FASTCHESS),
                "experiment_sha256": file_hash(ROOT / "experiment.json"),
                "threads_per_engine": threads, "hash_mb": hash_mb, "concurrency": concurrency,
                "control_identical_networks": control}
    if summary_path.exists():
        old = read_json(summary_path)
        if old["identity"] != identity:
            raise ValueError("Existing match settings differ; use a fresh run directory")
        verify_saved_match(old, directory / "games.pgn", name, pairs, opening_path)
        print(f"Reusing verified completed match: {phase}-{name}", flush=True)
        return old
    if (directory / "games.pgn").exists():
        raise ValueError(f"Partial run already exists: {directory}; preserve it and use a fresh directory")
    args = [str(FASTCHESS),
            "-engine", f"cmd={ENGINE}", f"name={name}", f"option.EvalFile={candidate}",
            "-engine", f"cmd={ENGINE}", "name=baseline", f"option.EvalFile={baseline}",
            "-each", "proto=uci", "tc=60+0.6", f"nodes={nodes}",
            f"option.Threads={threads}", f"option.Hash={hash_mb}", "option.Ponder=false", "option.UCI_LimitStrength=false",
            "-openings", f"file={opening_path}", "format=epd", "order=sequential",
            "-rounds", str(pairs), "-repeat", "-concurrency", str(concurrency),
            "-pgnout", "file=games.pgn", "append=false", "nodes=true",
            "-log", "file=fastchess.log", "level=warn", "engine=true", "append=false",
            "-ratinginterval", "16", "-report", "penta=true", "-strict"]
    # No evaluation-based adjudication: play to rules-based termination.
    write_json(directory / "command.json", {"created_utc": utc(), "identity": identity,
                                            "argv": args, "cwd": str(directory)})
    print(f"Running {phase}-{name}: {pairs * 2} games, {nodes}-node limit/move, concurrency {concurrency}, {threads} threads/engine", flush=True)
    start = time.monotonic()
    with (directory / "console.log").open("w", encoding="utf-8") as output:
        process = subprocess.Popen(args, cwd=directory, stdout=output, stderr=subprocess.STDOUT,
                                   creationflags=FLAGS)
        try:
            process.wait(timeout=900)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            if platform.system() == "Windows":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
            else:
                process.kill()
            process.wait()
            raise
    if process.returncode:
        raise RuntimeError(f"Fastchess failed ({process.returncode}); see {directory / 'console.log'}")
    console = (directory / "console.log").read_text()
    if re.search(r"\b(?:Warning|ERROR|FATAL)\b", console):
        raise RuntimeError("Match emitted a warning or error; inspect the console log")
    result = {"finished_utc": utc(), "elapsed_seconds": time.monotonic() - start,
              "identity": identity, "pgn_sha256": file_hash(directory / "games.pgn"),
              "stats": summarize_pgn(directory / "games.pgn", name, pairs, opening_path)}
    write_json(summary_path, result)
    print(json.dumps({"match": f"{phase}-{name}", "stats": result["stats"]}), flush=True)
    return result


def experiment() -> None:
    config = read_json(ROOT / "experiment.json")
    p = config["protocol"]
    prepare()
    smoke()
    control = run_match("control", "control", 4, p["screen_nodes_per_move"], control=True)
    screens = [run_match(c["name"], "screen", p["screen_pairs_per_candidate"], p["screen_nodes_per_move"])
               for c in config["candidates"]]
    selected = max(screens, key=lambda s: s["stats"]["score_fraction"])["identity"]["candidate"]
    write_json(ROOT / "results/selection.json", {"created_utc": utc(), "selected": selected,
               "rule": p["selection_rule"], "screen_scores": {s["identity"]["candidate"]: s["stats"]["score_fraction"] for s in screens},
               "confirmation_opening_sha256": file_hash(ROOT / "openings/confirmation.epd")})
    confirmation = run_match(selected, "confirmation", p["confirmation_pairs"], p["confirmation_nodes_per_move"])
    result = {"finished_utc": utc(), "method": config["method"], "control": control,
              "screens": screens, "selected": selected, "confirmation": confirmation,
              "conclusion": ("Positive exploratory signal at this shallow fixed-node setting; a larger independent time-control test is needed."
                             if confirmation["stats"]["positive_exploratory_signal"] else
                             "No statistically convincing improvement demonstrated by this initial direct-edit experiment."),
              "limitations": ["Only two manually chosen output-bias edits were tested, not all possible direct edits.",
                              "The 10000-node search limit is shallow; no absolute or general Elo claim is supported.",
                              "Confirmation uses disjoint positions but the same opening-book source.",
                              "The confidence interval is approximate and the sample is small.",
                              "This is an adaptation to NNUE, not a reproduction of the Qwen experiment."]}
    write_json(ROOT / "results/experiment-summary.json", result)
    lines = ["# Initial direct NNUE weight-editing experiment", "", result["conclusion"], "",
             "Stockfish 19, same executable and settings on both sides; only the NNUE file differs. No gradients or training.", "",
             "Both engines receive a 10,000-node search limit per move with generous clocks. The engine can stop earlier; PGN node annotations can also reflect an earlier exact-score update.", "",
             "| Stage | Candidate | W / D / L | Score | Approximate relative Elo (95% pair bootstrap) |",
             "| --- | --- | --- | --- | --- |"]
    for match in [control] + screens + [confirmation]:
        s = match["stats"]
        low, high = s["relative_elo_ci95_pair_bootstrap"]
        fmt = lambda v: f"{v:+.1f}" if v is not None else "unbounded"
        estimate = ("symmetry check; no rating estimate" if match["identity"]["control_identical_networks"]
                    else f"{fmt(s['relative_logistic_elo'])} [{fmt(low)}, {fmt(high)}]")
        lines.append(f"| {match['identity']['phase']} | {match['identity']['candidate']} | {s['wins']} / {s['draws']} / {s['losses']} | {100*s['score_fraction']:.1f}% | {estimate} |")
    lines += ["", "Screening selects a candidate; it is not evidence of a gain. The confirmation uses different openings, each played twice with colors reversed. Confidence intervals resample entire opening pairs. The identical-network control checks symmetry; its degenerate bootstrap interval is not a precision or equivalence claim.", "",
              "Each candidate changes six int32 final-layer bias parameters, tapered by material. Full byte-level edits and SHA-256 hashes are in `nets/*.json`. Stockfish loaded and re-exported all three networks byte for byte, and the static evaluation moved in the intended directions.", "",
              "## Limits", ""] + [f"- {x}" for x in result["limitations"]]
    (ROOT / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(result["conclusion"], flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "inspect", "smoke", "experiment"])
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "inspect":
        print(json.dumps(Network.load(ROOT / "nets/original.nnue").inspect(), indent=2))
    elif args.command == "smoke":
        smoke()
    else:
        experiment()


if __name__ == "__main__":
    main()
