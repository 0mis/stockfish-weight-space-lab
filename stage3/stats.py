"""Paired, anytime-valid evidence and an append-only confirmation alpha ledger.

This is not Fishtest's asymptotic GSPRT. For pair-average scores X in [0, 1]
and a fixed null mean m, each product of (1 + f * (X / m - 1)), 0 < f < 1,
is a nonnegative supermartingale when E[X | past] <= m. A fixed mixture is
also one. Ville's inequality bounds ever crossing 1/alpha by alpha. The
implementation uses the five pair outcomes, without pretending the two
games in a pair are independent. The null and positive effect are on the
score/logistic-Elo scale, NOT the normalized-Elo scale.

The protocol requires IID draws WITH replacement from a frozen clean pool,
fresh engines per pair, and matched stationary conditions. Sampling a finite
book without replacement does not satisfy this precise sampling contract.
Raw PGNs and an independent integrity/provenance audit remain necessary;
this module never converts a statistical pass alone into permission to
publish or a claim about all hardware or time controls.

Theory: https://arxiv.org/abs/2010.09686 (Waudby-Smith and Ramdas).
Pentanomial/nElo definitions: official-stockfish/fishtest,
server/fishtest/stats/LLRcalc.py, especially normalized_elo_practical.pdf.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
from typing import Iterable


METHOD = "pair-betting-mixture-v1"
GAME_RESULT_POLICY = "fastchess-182-clock-forfeit-v1"
AUDIT_CONTRACT = "stage3-authenticated-clock-forfeit-v1"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUTHORITATIVE_LEDGER = PROJECT_ROOT / "stage2/results/alpha-ledger.jsonl"
COMPETING_SUCCESSOR_LEDGER = PROJECT_ROOT / "stage3/results/alpha-ledger.jsonl"
PAIR_VALUES = (0.0, 0.25, 0.5, 0.75, 1.0)
# These fractions and equal weights are fixed BEFORE seeing any outcomes.
BET_FRACTIONS = tuple(2.0 ** -k for k in range(1, 13)) + (0.75, 0.9)
REQUIRED_ROLES = {"strongest_rated", "latest_dev"}
AUDIT_CHECKS = (
    "raw_pgn_hashes_verified",
    "all_pgn_movetext_legally_replayed",
    "normal_terminations_match_board_outcomes",
    "clock_forfeits_referee_side_result_and_clock_evidence_verified",
    "clock_forfeit_evidence_forms_and_late_ply_handling_recorded",
    "all_referee_clock_forfeits_included_without_replay",
    "allowed_timeout_warnings_match_counted_forfeits_one_to_one",
    "scheduled_openings_and_reversed_colors_verified",
    "same_candidate_artifact_in_every_comparison",
    "matched_time_threads_hash_and_hardware_verified",
    "no_unknown_engine_protocol_or_infrastructure_failures",
    "no_evaluation_or_tablebase_adjudication",
    "referee_time_control_margin_and_logging_policy_pinned",
    "clean_confirmation_pools_and_no_outcome_exclusions_verified",
    "official_uho_source_and_pool_membership_verified",
    "baseline_artifacts_and_rating_provenance_verified",
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def file_sha256(path: str | Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _hash(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("Expected a lowercase SHA256 digest")
    return value


def _integer(value: object, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _counts(counts: Iterable[int]) -> tuple[int, ...]:
    counts = tuple(counts)
    if len(counts) != 5:
        raise ValueError("Expected five pentanomial counts: LL, LD, DD/WL, WD, WW")
    return tuple(_integer(x, "count") for x in counts)


def _alpha(alpha: float) -> float:
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not 0 < alpha < 1:
        raise ValueError("alpha must be strictly between zero and one")
    return float(alpha)


def _score(score: float) -> float:
    if isinstance(score, bool) or score not in (0, 0.5, 1):
        raise ValueError("Each completed game score must be 0, 0.5, or 1")
    return float(score)


def update_pentanomial(counts: Iterable[int], candidate_white_score: float,
                       candidate_black_score: float) -> list[int]:
    """Return new counts; BOTH scores must be from the candidate's perspective."""
    result = list(_counts(counts))
    index = int(2 * (_score(candidate_white_score) + _score(candidate_black_score)))
    result[index] += 1
    return result


def logistic_elo(score: float) -> float | None:
    """None means an infinite boundary estimate; it never means zero Elo."""
    if not 0 <= score <= 1:
        raise ValueError("Score must be in [0, 1]")
    return 400 * math.log10(score / (1 - score)) if 0 < score < 1 else None


def pentanomial_summary(counts: Iterable[int]) -> dict:
    counts = _counts(counts)
    n = sum(counts)
    mean = sum(x * c for x, c in zip(PAIR_VALUES, counts)) / n if n else None
    variance = (sum(c * (x - mean) ** 2 for x, c in zip(PAIR_VALUES, counts)) / n
                if n else None)
    # Fishtest's per-game standard deviation is sqrt(2 * Var(pair mean)).
    nelo = ((800 / math.log(10)) * (mean - 0.5) / math.sqrt(2 * variance)
            if variance else None)
    return {
        "pentanomial": list(counts), "pairs": n, "games": 2 * n,
        "score_fraction": mean,
        "relative_logistic_elo": logistic_elo(mean) if n else None,
        "relative_normalized_elo_descriptive": nelo,
        "pair_variance_mle": variance,
        "elo_boundary": ("negative_infinity" if mean == 0 else
                         "positive_infinity" if mean == 1 else None),
        "estimate_warning": "Point estimates after selection or optional stopping may be biased; nElo is not logistic Elo.",
    }


def log_e_value(counts: Iterable[int], null_score: float = 0.5) -> float:
    """Log of the fixed positive-direction mixture; invariant to pair order."""
    counts = _counts(counts)
    if not 0 < null_score < 1:
        raise ValueError("null_score must be strictly between zero and one")
    components = [sum(c * math.log1p(f * (x / null_score - 1))
                      for x, c in zip(PAIR_VALUES, counts) if c)
                  for f in BET_FRACTIONS]
    largest = max(components)
    return largest + math.log(sum(math.exp(x - largest) for x in components)) - math.log(len(components))


def anytime_lower_score(counts: Iterable[int], alpha: float) -> float:
    """One-sided, time-uniform (1-alpha) lower score bound under the model."""
    counts = _counts(counts)
    threshold = -math.log(_alpha(alpha))
    if not sum(counts[1:]):
        return 0.0
    low, high = 0.0, 1.0
    for _ in range(60):
        mid = (low + high) / 2
        if log_e_value(counts, mid) >= threshold:
            low = mid
        else:
            high = mid
    return low


def sequential_evidence(counts: Iterable[int], *, alpha: float,
                        min_pairs: int = 128, max_pairs: int = 8192) -> dict:
    counts = _counts(counts)
    alpha = _alpha(alpha)
    _integer(min_pairs, "min_pairs", 1)
    _integer(max_pairs, "max_pairs", min_pairs)
    n = sum(counts)
    if n > max_pairs:
        raise ValueError("Pairs exceed the predeclared cap; do not extend a spent trial")
    positive = log_e_value(counts)
    negative = log_e_value(reversed(counts))
    threshold = -math.log(alpha)
    lower = anytime_lower_score(counts, alpha)
    if n >= min_pairs and positive >= threshold:
        decision = "gain"
    elif n >= min_pairs and negative >= -math.log(0.01):
        # Conservative resource stop only; this is not a separately advertised claim.
        decision = "stop_regression"
    elif n >= max_pairs:
        decision = "inconclusive_cap"
    else:
        decision = "continue"
    return {
        **pentanomial_summary(counts), "method": METHOD, "alpha": alpha,
        "null": "mean pair score <= 0.5 (logistic Elo <= 0)",
        "log_e_value": positive, "log_gain_threshold": threshold,
        "log_regression_e_value": negative,
        "anytime_lower_score": lower,
        "anytime_lower_logistic_elo": logistic_elo(lower),
        "lower_elo_boundary": "negative_infinity" if lower == 0 else None,
        "one_sided_confidence_level": 1 - alpha,
        "decision": decision, "min_pairs": min_pairs, "max_pairs": max_pairs,
        "interpretation": "Only gain rejects the nonpositive-effect null. A cap or regression resource stop does not prove equivalence.",
    }


def sample_schedule(opening_ids: Iterable[str], seed: int, count: int) -> list[str]:
    """IID draws WITH replacement. Freeze pool, seed, and count before games."""
    pool = sorted(opening_ids)
    if not pool or len(pool) != len(set(pool)):
        raise ValueError("Opening pool must be nonempty and unique")
    for opening in pool:
        _hash(opening)
    _integer(seed, "seed")
    _integer(count, "count")
    rng = random.Random(seed)
    return [pool[rng.randrange(len(pool))] for _ in range(count)]


def _artifact(artifact: dict) -> dict:
    path = Path(artifact["path"]).resolve(strict=True)
    expected = _hash(artifact["sha256"])
    if not path.is_file() or file_sha256(path) != expected:
        raise ValueError("Raw artifact is missing or differs from its SHA256")
    return {"path": str(path), "sha256": expected}


@contextmanager
def _lock(path: Path):
    lock = path.with_name(path.name + ".lock")
    try:
        handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ValueError("Ledger is locked; do not bypass a writer or an unresolved crashed writer") from exc
    try:
        os.write(handle, str(os.getpid()).encode("ascii"))
        os.close(handle)
        yield
    finally:
        lock.unlink()


class AlphaLedger:
    """Single-writer, hash-chained JSONL ledger. Never reset/recycle spent alpha.

    The chain detects edits and interior deletions, not deliberate rollback to
    a valid earlier prefix. Retain external checkpoints of `head_sha256`, and
    preserve the ledger with raw evidence. It is an audit aid, not security
    against a person intentionally deleting unfavorable experiments.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        if self.path != AUTHORITATIVE_LEDGER.resolve() or COMPETING_SUCCESSOR_LEDGER.exists():
            raise ValueError("Use the one global alpha ledger; a competing ledger requires explicit review, never a reset")
        self._events()  # Existing, intact ledger required; no implicit reset.

    @classmethod
    def create(cls, path: str | Path, protocol: dict) -> "AlphaLedger":
        path = Path(path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        if protocol.get("version") != 3 or protocol.get("game_result_policy", {}).get("id") != GAME_RESULT_POLICY:
            raise ValueError("Stage 3 requires its prospective clock-forfeit policy")
        if (path != AUTHORITATIVE_LEDGER.resolve() or COMPETING_SUCCESSOR_LEDGER.exists()
                or protocol.get("authoritative_ledger") != "stage2/results/alpha-ledger.jsonl"):
            raise ValueError("Use the one global alpha ledger; never allocate a second 0.01 family budget")
        if protocol["statistics"]["method"] != METHOD:
            raise ValueError("Protocol method differs from the implemented method")
        if _alpha(protocol["statistics"]["familywise_alpha"]) > 0.01:
            raise ValueError("The completion familywise error budget cannot exceed 0.01")
        if protocol["statistics"]["bet_fractions"] != list(BET_FRACTIONS):
            raise ValueError("Protocol fractions differ from the fixed mixture")
        confirmation = protocol["confirmation"]
        _integer(confirmation["min_pairs"], "min_pairs", 128)
        _integer(confirmation["max_pairs"], "max_pairs", confirmation["min_pairs"])
        _integer(confirmation["minimum_clean_pool_positions"], "minimum_clean_pool_positions", 2048)
        settings = confirmation["settings"]
        tc = re.fullmatch(r"(\d+(?:\.\d+)?)\+(\d+(?:\.\d+)?)", settings["time_control"])
        if not tc or float(tc[1]) < 60 or float(tc[2]) < 0.6:
            raise ValueError("Completion requires at least the declared realistic 60+0.6 wall-clock control")
        if (settings["nodes_per_move"] is not None or settings["depth_limit"] is not None
                or any(settings[k] is not False for k in ("ponder", "strength_limit", "evaluation_adjudication", "tablebases"))
                or settings["fresh_engines_per_pair"] is not True):
            raise ValueError("Confirmation must use unrestricted real-time play with fresh engine state")
        payload = {"type": "initialize", "protocol": protocol, "audit_contract": AUDIT_CONTRACT,
                   "protocol_sha256": digest(protocol), "method": METHOD,
                   "stats_implementation_sha256": file_sha256(__file__)}
        event = {"index": 0, "previous_sha256": "0" * 64, "payload": payload}
        event["sha256"] = digest(event)
        with _lock(path):
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(_canonical(event).decode() + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        return cls(path)

    def _events(self) -> list[dict]:
        data = self.path.read_bytes()
        if not data or not data.endswith(b"\n"):
            raise ValueError("Missing or partially written ledger; preserve and audit it")
        events = []
        previous = "0" * 64
        for index, line in enumerate(data.splitlines()):
            event = json.loads(line)
            claimed = event.pop("sha256")
            if event["index"] != index or event["previous_sha256"] != previous or digest(event) != claimed:
                raise ValueError("Ledger hash chain or event ordering is invalid")
            event["sha256"] = claimed
            events.append(event)
            previous = claimed
        first = events[0]["payload"]
        if first.get("audit_contract") != AUDIT_CONTRACT:
            raise ValueError("This is not a stage-3 policy ledger; never reset or migrate spent alpha implicitly")
        if first["type"] != "initialize" or first["method"] != METHOD or digest(first["protocol"]) != first["protocol_sha256"]:
            raise ValueError("Ledger initialization is invalid")
        if first["stats_implementation_sha256"] != file_sha256(__file__):
            raise ValueError("Statistics implementation changed; use the frozen source or an independently audited migration")
        return events

    def _append(self, events: list[dict], payload: dict) -> None:
        event = {"index": len(events), "previous_sha256": events[-1]["sha256"], "payload": payload}
        event["sha256"] = digest(event)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(_canonical(event).decode() + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    @staticmethod
    def _trials(events: list[dict]) -> dict[str, dict]:
        trials = {}
        for event in events[1:]:
            p = event["payload"]
            if p["type"] == "reserve":
                trials[p["trial_id"]] = p
        return trials

    def reserve_trial(self, spec: dict) -> dict:
        """Reserve alpha before ANY confirmation; spec schema is in protocol.json."""
        # A JSON round-trip detaches all mutable references supplied by callers.
        spec = json.loads(_canonical(spec))
        with _lock(self.path):
            events = self._events()
            protocol = events[0]["payload"]["protocol"]
            trials = self._trials(events)
            self._validate_spec(spec, protocol, list(trials.values()))
            k = len(trials) + 1
            alpha = protocol["statistics"]["familywise_alpha"] / (k * (k + 1))
            trial = {"type": "reserve", "trial_id": f"trial-{k:04d}", "trial_index": k,
                     "spec": spec, "spec_sha256": digest(spec), "trial_alpha": alpha,
                     "alpha_per_baseline": alpha / len(spec["baselines"])}
            self._append(events, trial)
        return trial

    @staticmethod
    def _validate_spec(spec: dict, protocol: dict, previous: list[dict]) -> None:
        if spec["protocol_sha256"] != digest(protocol):
            raise ValueError("Trial is not bound to this ledger's frozen protocol")
        if (spec.get("game_result_policy_id") != GAME_RESULT_POLICY
                or spec.get("game_result_policy_sha256") != digest(protocol["game_result_policy"])):
            raise ValueError("Trial is not bound to the prospective game-result policy")
        for key in ("engine_sha256", "network_sha256"):
            _hash(spec["candidate"][key])
        _hash(spec["screening_evidence_sha256"])
        baseline_ids = [b["id"] for b in spec["baselines"]]
        if len(baseline_ids) != 2 or len(set(baseline_ids)) != 2 or {b["role"] for b in spec["baselines"]} != REQUIRED_ROLES:
            raise ValueError("Exactly the strongest-rated reference and latest-dev incumbent are required")
        for b in spec["baselines"]:
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", b["id"]):
                raise ValueError("Invalid baseline ID")
            for key in ("engine_sha256", "network_sha256", "provenance_sha256"):
                _hash(b[key])
        settings = spec["settings"]
        allowed = protocol["confirmation"]["settings"]
        if settings != allowed:
            raise ValueError("Confirmation settings must exactly match the frozen protocol")
        _hash(spec["hardware_identity_sha256"])
        for key in ("min_pairs", "max_pairs"):
            if spec[key] != protocol["confirmation"][key]:
                raise ValueError("Pair bounds differ from the frozen protocol")
        sampling = spec["sampling"]
        if sampling["method"] != "iid_with_replacement":
            raise ValueError("This e-process requires the declared IID sampling contract")
        if set(sampling["pools"]) != set(baseline_ids):
            raise ValueError("Need a separate confirmation pool for each baseline")
        used = set(spec["screen_opening_ids"])
        if len(used) != len(spec["screen_opening_ids"]):
            raise ValueError("Duplicate screening opening IDs")
        for opening in used:
            _hash(opening)
        for trial in previous:
            used.update(trial["spec"]["screen_opening_ids"])
            for pool in trial["spec"]["sampling"]["pools"].values():
                used.update(pool["opening_ids"])
        for pool in sampling["pools"].values():
            ids = pool["opening_ids"]
            if len(ids) < protocol["confirmation"]["minimum_clean_pool_positions"] or len(ids) != len(set(ids)):
                raise ValueError("Confirmation pool is too small or has duplicate positions")
            for opening in ids:
                _hash(opening)
            _hash(pool["source_sha256"])
            if used.intersection(ids):
                raise ValueError("Confirmation pool overlaps screening, another baseline, or a previous trial")
            used.update(ids)
            expected = sample_schedule(ids, pool["seed"], spec["max_pairs"])
            if pool["schedule_sha256"] != digest(expected):
                raise ValueError("Confirmation schedule is not the committed IID draw sequence")

    def record_pairs(self, trial_id: str, baseline_id: str, pairs: list[dict], artifact: dict) -> dict:
        """Record a contiguous batch of fully validated, color-reversed pairs.

        The runner must replay PGNs and validate colors/results before calling.
        This method verifies sample order, scores, counts and the raw PGN hash.
        A game error invalidates the trial; never silently omit or replay an
        unfavorable completed pair. Preserve all partial/error artifacts too.
        """
        if not pairs:
            raise ValueError("No complete pairs supplied")
        artifact = _artifact(artifact)
        with _lock(self.path):
            events = self._events()
            if any(e["payload"].get("artifact", {}).get("sha256") == artifact["sha256"]
                   or e["payload"].get("artifact", {}).get("path") == artifact["path"]
                   for e in events):
                raise ValueError("Raw PGN artifact already recorded; reconcile the existing pair instead of reusing games")
            trial = self._trials(events)[trial_id]
            status = self._status(events, trial_id)
            if status["closed_reason"]:
                raise ValueError("This trial is closed")
            comparison = status["comparisons"][baseline_id]
            if comparison["decision"] != "continue":
                raise ValueError("This comparison has already reached a stopping decision")
            spec = trial["spec"]
            pool = spec["sampling"]["pools"][baseline_id]
            schedule = sample_schedule(pool["opening_ids"], pool["seed"], spec["max_pairs"])
            counts = comparison["pentanomial"]
            start = comparison["pairs"]
            clean = []
            if start + len(pairs) > spec["max_pairs"]:
                raise ValueError("Batch exceeds the frozen pair cap")
            for index, pair in enumerate(pairs, start):
                if pair["pair_index"] != index or type(pair["pair_index"]) is not int:
                    raise ValueError("Duplicate, missing, or out-of-order pair index")
                if pair["opening_id"] != schedule[index]:
                    raise ValueError("Pair does not follow the precommitted opening schedule")
                white = _score(pair["candidate_white_score"])
                black = _score(pair["candidate_black_score"])
                counts = update_pentanomial(counts, white, black)
                clean.append({"pair_index": index, "opening_id": schedule[index],
                              "candidate_white_score": white, "candidate_black_score": black})
            self._append(events, {"type": "pairs", "trial_id": trial_id,
                                  "baseline_id": baseline_id, "pairs": clean, "artifact": artifact})
        return self.trial_status(trial_id)["comparisons"][baseline_id]

    def abandon_trial(self, trial_id: str, reason: str) -> None:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("An explicit abandonment/invalidation reason is required")
        with _lock(self.path):
            events = self._events()
            if self._status(events, trial_id)["closed_reason"]:
                raise ValueError("Trial already closed")
            self._append(events, {"type": "close", "trial_id": trial_id, "reason": reason})

    def _status(self, events: list[dict], trial_id: str) -> dict:
        trial = self._trials(events)[trial_id]
        spec = trial["spec"]
        counts = {b["id"]: [0] * 5 for b in spec["baselines"]}
        artifacts = []
        closed = None
        for event in events:
            p = event["payload"]
            if p.get("trial_id") != trial_id:
                continue
            if p["type"] == "pairs":
                for pair in p["pairs"]:
                    counts[p["baseline_id"]] = update_pentanomial(counts[p["baseline_id"]],
                        pair["candidate_white_score"], pair["candidate_black_score"])
                artifacts.append(p["artifact"])
            elif p["type"] == "close":
                closed = p["reason"]
        comparisons = {name: sequential_evidence(c, alpha=trial["alpha_per_baseline"],
                        min_pairs=spec["min_pairs"], max_pairs=spec["max_pairs"])
                       for name, c in counts.items()}
        statistical = not closed and all(c["decision"] == "gain" for c in comparisons.values())
        return {"trial_id": trial_id, "spec_sha256": trial["spec_sha256"],
                "candidate": spec["candidate"], "baselines": spec["baselines"],
                "trial_alpha": trial["trial_alpha"], "alpha_per_baseline": trial["alpha_per_baseline"],
                "head_sha256": events[-1]["sha256"], "closed_reason": closed,
                "comparisons": comparisons, "artifacts": artifacts,
                "statistical_pass": bool(statistical), "completion_verified": False,
                "claim_scope": "This exact candidate against the frozen baselines at the declared wall-clock control and local hardware only.",
                "next_gate": "Independent raw-PGN, settings and strongest-baseline provenance audit is required before a completion claim."}

    def trial_status(self, trial_id: str, *, verify_artifacts: bool = False) -> dict:
        status = self._status(self._events(), trial_id)
        if verify_artifacts:
            for artifact in status["artifacts"]:
                _artifact(artifact)
        return status

    def trial_record(self, trial_id: str) -> dict:
        """Return the immutable reservation/spec for runner recovery."""
        return self._trials(self._events())[trial_id]

    def recorded_batches(self, trial_id: str, baseline_id: str) -> list[dict]:
        """Return chronological recorded pair events and raw artifacts for recovery."""
        events = self._events()
        spec = self._trials(events)[trial_id]["spec"]
        if baseline_id not in {b["id"] for b in spec["baselines"]}:
            raise ValueError("Unknown baseline for this trial")
        return [event["payload"] for event in events
                if event["payload"].get("type") == "pairs"
                and event["payload"].get("trial_id") == trial_id
                and event["payload"].get("baseline_id") == baseline_id]

    def completion_gate(self, trial_id: str, audit_path: str | Path) -> dict:
        """Check a separately produced audit; no publication action is authorized."""
        status = self.trial_status(trial_id, verify_artifacts=True)
        audit_path = Path(audit_path).resolve(strict=True)
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        spec = self.trial_record(trial_id)["spec"]
        if (audit.get("audit_contract") != AUDIT_CONTRACT
                or audit.get("game_result_policy_id") != GAME_RESULT_POLICY
                or audit.get("game_result_policy_sha256") != spec["game_result_policy_sha256"]):
            raise ValueError("Audit uses a different game-result policy/contract")
        if audit.get("trial_id") != trial_id or audit.get("spec_sha256") != status["spec_sha256"]:
            raise ValueError("Audit is not bound to this exact trial")
        if audit.get("ledger_head_sha256") != status["head_sha256"]:
            raise ValueError("Audit was produced for a different ledger state")
        expected = sorted({a["sha256"] for a in status["artifacts"]})
        if audit.get("raw_pgn_sha256") != expected:
            raise ValueError("Audit does not cover all recorded raw PGNs")
        if any(audit.get("checks", {}).get(check) is not True for check in AUDIT_CHECKS):
            raise ValueError("Independent audit has missing or failing mandatory checks")
        status["completion_verified"] = status["statistical_pass"]
        status["audit"] = {"path": str(audit_path), "sha256": file_sha256(audit_path)}
        return status
