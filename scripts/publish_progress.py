"""Publish aggregate confirmation progress, never engines or raw research data.

The research worktree is read only.  The publication worktree receives just a
JSON snapshot and a bounded README block.  Git network access requires --publish;
Each optional farm flag enables only public Fishtest GETs for its pinned run.
Local watch polls every 30 seconds and each enabled farm run every 60 seconds.
Statistical success always remains pending independent terminal integrity audit.
"""

from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.request


TRIAL_ID = "trial-0003"
TRIAL_DIRECTORY = "stage4/conservative_confirmation/trials/d1-fc2-confirmation-002"
REFERENCES = {"spcc-261025": "strongest_rated", "dev-261106": "latest_dev"}
PUBLIC_REPOSITORY = "0mis/stockfish-weight-space-lab"
PUBLIC_NAME = "0mis"
PUBLIC_EMAIL = "67492572+0mis@users.noreply.github.com"
STATUS_PATH = "results/live-status.json"
README_PATH = "README.md"
OUTPUT_PATHS = (STATUS_PATH, README_PATH)
START = b"<!-- live-status:start -->"
END = b"<!-- live-status:end -->"
BLOCK = re.compile(re.escape(START) + rb".*?" + re.escape(END), re.DOTALL)
FISHTEST_RUN_ID = "6af10a258e7fb2e78bc1ca5c"
SOURCE_FISHTEST_RUN_ID = "6af16e648e7fb2e78bc1cb09"
DONOR_FISHTEST_RUN_ID = "6af19afb8e7fb2e78bc1cb30"
FISHTEST_ORIGIN = "https://tests.stockfishchess.org"
FISHTEST_ARGS = {
    "tests_repo": "https://github.com/0mis/Stockfish",
    "resolved_new": "9579e56ec2926265abe40ca20ba069d6463a66b6",
    "resolved_base": "7cdd5e89a39fe3071b67d91c7bb07d712044bf76",
    "new_nets": ["nn-fcbaf7d2197c.nnue"], "base_nets": ["nn-d1ee674a62ca.nnue"],
    "new_signature": "2261721", "base_signature": "1556650",
    "tc": "10+0.1", "new_tc": "10+0.1", "threads": 1,
    "new_options": "Hash=16", "base_options": "Hash=16",
}
SOURCE_FISHTEST_ARGS = {
    **copy.deepcopy(FISHTEST_ARGS),
    "resolved_new": "de342a301195b34b7da76374fe3fadf29352de8d",
    "new_nets": ["nn-18cd32e11a9c.nnue"], "new_signature": "3464885",
    "book": "UHO_Lichess_4852_v1.epd", "book_depth": "8",
    "adjudication": True, "auto_purge": False, "num_games": 800000,
}
DONOR_FISHTEST_ARGS = {
    **copy.deepcopy(SOURCE_FISHTEST_ARGS),
    "resolved_new": "d7155994d192b4e723866360ae9285b42e122790",
    "resolved_base": "de342a301195b34b7da76374fe3fadf29352de8d",
    "new_nets": ["nn-d5c257728ba5.nnue"], "base_nets": ["nn-18cd32e11a9c.nnue"],
    "new_signature": "2376690", "base_signature": "3464885", "username": PUBLIC_NAME,
}
FISHTEST_CONFIGS = {FISHTEST_RUN_ID: FISHTEST_ARGS, SOURCE_FISHTEST_RUN_ID: SOURCE_FISHTEST_ARGS,
                    DONOR_FISHTEST_RUN_ID: DONOR_FISHTEST_ARGS}
SOURCE_TREE = "8e3164caf60d281cb4b1d00a699364e04b354451"
SOURCE_TESTED_COMMIT = "7a17b53bcaf93f54a23ad65f309c413585500c82"
FISHTEST_SPRT = {"elo_model": "normalized", "elo0": 0.0, "elo1": 2.0,
                 "alpha": 0.05, "beta": 0.05,
                 "lower_bound": -math.log(19), "upper_bound": math.log(19)}


class ProgressError(Exception):
    """A bounded, public-safe diagnostic; raw paths and subprocess logs stay out."""


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def count(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ProgressError("Fishtest returned an invalid aggregate count.")
    return value


def number(value: object) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ProgressError("Fishtest returned a nonfinite statistic.")
    return float(value)


def farm_results(results: dict) -> dict:
    wins, draws, losses = (count(results[key]) for key in ("wins", "draws", "losses"))
    penta = [count(value) for value in results["pentanomial"]]
    if len(penta) != 5 or wins + draws + losses != 2 * sum(penta):
        raise ProgressError("Fishtest game and pair totals differ.")
    middle_wl = wins - penta[3] - 2 * penta[4]
    if (not 0 <= middle_wl <= penta[2] or losses != 2 * penta[0] + penta[1] + middle_wl
            or draws != penta[1] + penta[3] + 2 * (penta[2] - middle_wl)):
        raise ProgressError("Fishtest WDL and pentanomial scores differ.")
    return {"wins": wins, "draws": draws, "losses": losses, "pentanomial": penta,
            "games": wins + draws + losses, "pairs": sum(penta),
            "candidate_points": wins + draws / 2, "reference_points": losses + draws / 2,
            **{key: count(results[key]) for key in ("crashes", "time_losses") if key in results}}


def farm_observation(run: dict, expected_run_id: str | None = None) -> dict:
    run_id = run["_id"]
    if run_id not in FISHTEST_CONFIGS or expected_run_id is not None and run_id != expected_run_id:
        raise ProgressError("Fishtest returned an unexpected run identity.")
    expected_args = FISHTEST_CONFIGS[run_id]
    args = run["args"]
    if any(type(args.get(key)) is not type(value) or args[key] != value for key, value in expected_args.items()):
        raise ProgressError("Fishtest run identity or pinned configuration differs.")
    for key, expected in (("new_net", expected_args["new_nets"][0]), ("base_net", expected_args["base_nets"][0])):
        if key in args and args[key] != expected:
            raise ProgressError("Fishtest network identity differs.")
    sprt = args["sprt"]
    for key, expected in FISHTEST_SPRT.items():
        valid = sprt[key] == expected if isinstance(expected, str) else abs(number(sprt[key]) - expected) <= 1e-9
        if not valid:
            raise ProgressError("Fishtest SPRT parameters differ from the submitted test.")
    state = sprt["state"]
    if state not in ("", "accepted", "rejected"):
        raise ProgressError("Fishtest returned an unknown SPRT state.")
    flags = {key: run[key] for key in ("approved", "finished", "failed", "deleted")}
    if any(type(value) is not bool for value in flags.values()) or state and not flags["finished"]:
        raise ProgressError("Fishtest returned inconsistent run-state flags.")
    results = farm_results(run["results"])
    maximum_games = count(args["num_games"])
    if maximum_games < 1:
        raise ProgressError("Fishtest returned an invalid game cap.")
    if flags["deleted"]:
        status = "cancelled_deleted"
    elif flags["failed"]:
        status = "failed"
    elif state:
        status = "sprt_" + state
    elif flags["finished"]:
        status = "inconclusive_game_cap" if results["games"] >= maximum_games else "stopped_without_sprt_decision"
    else:
        status = "approved_open" if flags["approved"] else "pending_approval"
    return {**flags, "status": status, "maximum_games": maximum_games, "results": results,
            "sprt": {**FISHTEST_SPRT, "state": state, "llr": number(sprt["llr"])}}


def result_key(observation: dict) -> tuple:
    results = observation["results"]
    return (results["wins"], results["draws"], results["losses"], tuple(results["pentanomial"]))


def null_farm_elo(availability: str) -> dict:
    # Normalized hypotheses do not change the API estimate/interval's Elo scale.
    return {"availability": availability, "model": "normalized", "model_scope": "SPRT",
            "estimate_scale": "logistic", "confidence_percent": 95,
            "estimate": None, "confidence_interval": None, "label": "Fishtest logistic Elo and nominal 95% CI"}


def reported_farm_elo(estimate: object, interval: object) -> dict:
    if not isinstance(interval, list) or len(interval) != 2:
        raise ProgressError("Fishtest returned an invalid Elo interval.")
    lower, upper = map(number, interval)
    if lower > upper:
        raise ProgressError("Fishtest returned a reversed Elo interval.")
    return {**null_farm_elo("current"), "estimate": number(estimate), "confidence_interval": [lower, upper]}


def fetch_fishtest_json(endpoint: str, run_id: str) -> dict:
    if endpoint not in ("get_run", "get_elo") or run_id not in FISHTEST_CONFIGS:
        raise ProgressError("Only the reviewed public Fishtest endpoints and runs are supported.")
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise ProgressError("A public Fishtest endpoint redirected unexpectedly.")
    request = urllib.request.Request(f"{FISHTEST_ORIGIN}/api/{endpoint}/{run_id}", method="GET",
                                     headers={"Accept": "application/json", "User-Agent": "0mis-stockfish-progress/1"})
    with urllib.request.build_opener(NoRedirect).open(request, timeout=10) as response:
        data = response.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        raise ProgressError("The public Fishtest response exceeded its bounded size.")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ProgressError("The public Fishtest response was not an object.")
    return value


class FishtestObserver:
    """Only whitelisted aggregates survive; polling clocks never enter output."""

    def __init__(self, run_id: str, previous: dict | None = None, *, fetch=None, clock=None):
        if run_id not in FISHTEST_CONFIGS:
            raise ProgressError("Only the reviewed submitted Fishtest runs are supported.")
        configuration = FISHTEST_CONFIGS[run_id]
        self.run_id, self.fetch, self.clock = run_id, fetch or fetch_fishtest_json, clock or time.monotonic
        self.next_poll = 0.0
        self.view = {"run_id": run_id, "url": f"{FISHTEST_ORIGIN}/tests/view/{run_id}",
                     "experiment": "Public NNUE-only test; independent of local trial-0003.",
                     "configuration": copy.deepcopy(configuration), "availability": "unavailable", "observation": None}
        if run_id == SOURCE_FISHTEST_RUN_ID:
            self.view.update(experiment="Public test1757 prefetch source with the original 18cd network.",
                             source_tree=SOURCE_TREE, same_tree_tested_commit=SOURCE_TESTED_COMMIT)
        elif run_id == DONOR_FISHTEST_RUN_ID:
            self.view.update(experiment="Public nine-bias NNUE edit versus its test1757 donor parent.",
                             comparison_scope="donor_parent_only",
                             source_relationship="Same prefetch source except the default network filename.",
                             reference_label="test1757 donor parent with original 18cd NNUE")
        # Revalidate and project prior public aggregates instead of copying an
        # arbitrary prior object, which could contain unrelated user fields.
        try:
            if previous and previous["run_id"] == run_id and previous["configuration"] == configuration:
                prior = previous["observation"]
                observation = farm_observation({"_id": run_id,
                    "args": {**previous["configuration"], "num_games": prior["maximum_games"], "sprt": prior["sprt"]},
                    "results": prior["results"], **{key: prior[key] for key in ("approved", "finished", "failed", "deleted")}},
                    run_id)
                observation["reported_elo"] = self.previous_elo(prior, observation)
                self.view.update(availability="stale", observation=observation)
        except (ProgressError, KeyError, TypeError, ValueError, OverflowError):
            pass

    @staticmethod
    def previous_elo(previous: dict | None, observation: dict) -> dict:
        if observation["results"]["games"] == 0:
            return null_farm_elo("no_games")
        try:
            elo = previous["reported_elo"]
            if result_key(previous) == result_key(observation) and elo["model"] == "normalized":
                return {**reported_farm_elo(elo["estimate"], elo["confidence_interval"]), "availability": "stale"}
        except (ProgressError, KeyError, TypeError, ValueError, OverflowError):
            pass
        return null_farm_elo("unavailable")

    def observe(self) -> dict:
        now = self.clock()
        if now < self.next_poll:
            return copy.deepcopy(self.view)
        self.next_poll = now + 60
        previous = self.view["observation"]
        try:
            observation = farm_observation(self.fetch("get_run", self.run_id), self.run_id)
        except (ProgressError, OSError, KeyError, TypeError, ValueError, OverflowError):
            self.view["availability"] = "stale" if previous else "unavailable"
            if previous and previous["reported_elo"]["availability"] == "current":
                previous["reported_elo"]["availability"] = "stale"
            return copy.deepcopy(self.view)
        observation["reported_elo"] = self.previous_elo(previous, observation)
        if observation["results"]["games"]:
            try:
                response = self.fetch("get_elo", self.run_id)
                elo_observation = farm_observation(response, self.run_id)
                if result_key(elo_observation) != result_key(observation):
                    raise ProgressError("The two Fishtest endpoints observed different result prefixes.")
                observation["reported_elo"] = reported_farm_elo(response["elo"]["elo"], response["elo"]["ci"])
            except (ProgressError, OSError, KeyError, TypeError, ValueError, OverflowError):
                pass  # Valid current counts remain publishable without current Elo.
        self.view.update(availability="current", observation=observation)
        return copy.deepcopy(self.view)


def load_stats(research_repo: Path):
    source = research_repo / "stage3/stats.py"
    spec = importlib.util.spec_from_file_location("_public_progress_stats", source)
    if spec is None or spec.loader is None:
        raise ProgressError("The frozen statistics module is unavailable.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_optional(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


def previous_snapshot(publication_repo: Path) -> dict | None:
    data = read_optional(publication_repo / STATUS_PATH)
    if data is None:
        return None
    value = json.loads(data)
    if value.get("schema_version") != 1 or value.get("trial_id") != TRIAL_ID:
        raise ProgressError("The existing status file is not this publisher's snapshot.")
    return value


def build_snapshot(research_repo: Path, previous: dict | None = None, *, fishtest: FishtestObserver | None = None,
                   source_fishtest: FishtestObserver | None = None,
                   donor_fishtest: FishtestObserver | None = None) -> dict:
    stats = load_stats(research_repo)
    ledger = stats.AlphaLedger(stats.AUTHORITATIVE_LEDGER)
    # One validated prefix backs every number.  Public methods reread a live
    # ledger independently, so use their existing pure prefix helpers together.
    events = ledger._events()
    if previous is not None:
        checkpoint = previous["ledger_prefix"]
        index = checkpoint["event_index"]
        if (type(index) is not int or index < 0 or index >= len(events)
                or events[index]["sha256"] != checkpoint["head_sha256"]):
            raise ProgressError("The ledger no longer extends the last public checkpoint.")
    trial = ledger._trials(events)[TRIAL_ID]
    reservation = json.loads((research_repo / TRIAL_DIRECTORY / "reservation.json").read_bytes())
    if (reservation["trial_id"] != TRIAL_ID or reservation["spec_sha256"] != trial["spec_sha256"]
            or stats.digest(reservation["spec"]) != trial["spec_sha256"]):
        raise ProgressError("The frozen trial directory differs from the ledger reservation.")
    spec = trial["spec"]
    if {b["id"]: b["role"] for b in spec["baselines"]} != REFERENCES:
        raise ProgressError("The reserved references differ from the frozen public comparison.")
    settings = spec["settings"]
    if (settings["time_control"] != "60+0.6" or settings["threads_per_engine"] != 1
            or settings["hash_mb_per_engine"] != 64 or not settings["fresh_engines_per_pair"]):
        raise ProgressError("The reserved match settings differ from the public protocol.")
    status = ledger._status(events, TRIAL_ID)
    wdl = {name: [0, 0, 0] for name in REFERENCES}
    pairs = {name: 0 for name in REFERENCES}
    for event in events:
        payload = event["payload"]
        if payload.get("trial_id") != TRIAL_ID or payload["type"] != "pairs":
            continue
        name = payload["baseline_id"]
        for pair in payload["pairs"]:
            if type(pair["pair_index"]) is not int or pair["pair_index"] != pairs[name]:
                raise ProgressError("The trial's recorded pair sequence is incomplete or duplicated.")
            for key in ("candidate_white_score", "candidate_black_score"):
                score = pair[key]
                if type(score) not in (int, float) or score not in (0, 0.5, 1):
                    raise ProgressError("A recorded game score is invalid.")
                wdl[name][0 if score == 1 else 1 if score == 0.5 else 2] += 1
            pairs[name] += 1
    comparisons = []
    for name, role in REFERENCES.items():
        evidence = status["comparisons"][name]
        wins, draws, losses = wdl[name]
        if pairs[name] != evidence["pairs"] or wins + draws + losses != evidence["games"]:
            raise ProgressError("Aggregate game counts differ from the paired statistics.")
        comparisons.append({
            "reference": name, "role": role, "wins": wins, "draws": draws, "losses": losses,
            "candidate_points": wins + draws / 2, "reference_points": losses + draws / 2,
            "games": evidence["games"], "pairs": evidence["pairs"],
            "score_fraction": evidence["score_fraction"],
            "logistic_elo_estimate": evidence["relative_logistic_elo"],
            "estimate_boundary": evidence["elo_boundary"],
            "anytime_lower_logistic_elo": evidence["anytime_lower_logistic_elo"],
            "lower_bound_boundary": evidence["lower_elo_boundary"],
            "one_sided_confidence_percent": 100 * (1 - evidence["alpha"]),
            "log_e_value": evidence["log_e_value"],
            "log_gain_threshold": evidence["log_gain_threshold"],
            "statistical_decision": evidence["decision"],
            "minimum_pairs": evidence["min_pairs"],
            "minimum_pairs_reached": evidence["pairs"] >= evidence["min_pairs"],
            "maximum_pairs": evidence["max_pairs"],
        })
    snapshot = {
        "schema_version": 1, "trial_id": TRIAL_ID,
        "candidate": {key: spec["candidate"][key]
                      for key in ("label", "engine_sha256", "network_sha256")},
        "ledger_prefix": {"event_index": events[-1]["index"], "head_sha256": events[-1]["sha256"]},
        "protocol": {
            "method": stats.METHOD, "time_control": "60+0.6", "threads_per_engine": 1,
            "hash_mb_per_engine": 64, "fresh_engines_per_pair": True,
            "familywise_confidence_percent": 100 * (1 - events[0]["payload"]["protocol"]["statistics"]["familywise_alpha"]),
            "trial_confidence_percent": 100 * (1 - trial["trial_alpha"]),
            "confidence_interpretation": "Fixed protocol coverage under its assumptions, not a probability of superiority.",
        },
        "trial_closed": status["closed_reason"] is not None,
        "statistical_pass": status["statistical_pass"],
        "completion_verified": False,
        "integrity_audit": "independent_terminal_audit_pending",
        "sampler_state": "not_inferred_from_ledger",
        "comparisons": comparisons,
        "interpretation": "Provisional estimates. Statistical gain requires both reference gates and an independent terminal integrity audit before verified-gain wording. A statistical continue decision does not report sampler liveness.",
        "scope": "This frozen candidate and references at the declared time control and test hardware only.",
    }
    for key, observer, run_id in (("fishtest", fishtest, FISHTEST_RUN_ID),
                                  ("source_fishtest", source_fishtest, SOURCE_FISHTEST_RUN_ID),
                                  ("donor_fishtest", donor_fishtest, DONOR_FISHTEST_RUN_ID)):
        if observer is not None:
            view = observer.observe()
            if view["run_id"] != run_id or view["configuration"] != FISHTEST_CONFIGS[run_id]:
                raise ProgressError("Fishtest observation does not belong to this public snapshot field.")
            snapshot[key] = view
    return snapshot


def elo_text(value: float | None, boundary: str | None) -> str:
    if boundary == "negative_infinity":
        return "−∞"
    if boundary == "positive_infinity":
        return "+∞"
    return "pending" if value is None else f"{value:+.2f}"


def farm_marker(farm: dict, expected_run_id: str | None = None) -> list[str]:
    run_id = farm["run_id"]
    if run_id not in FISHTEST_CONFIGS or expected_run_id is not None and run_id != expected_run_id:
        raise ProgressError("Fishtest section received an unexpected run identity.")
    config = FISHTEST_CONFIGS[run_id]
    if farm["configuration"] != config:
        raise ProgressError("Fishtest section received an unexpected configuration.")
    source = run_id == SOURCE_FISHTEST_RUN_ID
    donor = run_id == DONOR_FISHTEST_RUN_ID
    title = ("Public Fishtest NNUE edit vs donor parent" if donor else
             "Public Fishtest test1757 source and network test" if source else "Public Fishtest NNUE-only test")
    description = ("The test1757 prefetch source and original 18cd network face official Stockfish with the D1 network. "
                   "The Elo estimate below applies only to this run." if source else
                   "This is a separate NNUE-only experiment. Its executable, clocks, normalized SPRT and results remain separate from local trial-0003's paired e-process.")
    if donor:
        description = ("The nine-bias d5 NNUE edit faces its test1757 donor parent with the original 18cd network. "
                       "Both sides use the same prefetch source except the default network filename. "
                       "This estimates only the NNUE edit relative to its donor parent; it is not an official-Stockfish comparison. "
                       "Its results remain separate from both earlier farm runs and local trial-0003.")
    url = f"{FISHTEST_ORIGIN}/tests/view/{run_id}"
    lines = ["", f"### {title}", "",
             f"[{'Fishtest' if donor else 'Official'} run `{run_id}`]({url}) · `10+0.1 / T1 / H16` · API **{farm['availability']}**", "", description]
    if source:
        lines += ["", f"The submitted source `{config['resolved_new']}` shares tree `{SOURCE_TREE}` "
                  f"with the tested commit `{SOURCE_TESTED_COMMIT}`. It uses `{config['new_nets'][0]}` "
                  f"(bench `{config['new_signature']}`). The base is `{config['resolved_base']}` with "
                  f"`{config['base_nets'][0]}` (bench `{config['base_signature']}`)."]
    elif donor:
        lines += ["", f"Candidate `{config['resolved_new']}` uses `{config['new_nets'][0]}` "
                  f"(bench `{config['new_signature']}`). Donor parent `{config['resolved_base']}` uses "
                  f"`{config['base_nets'][0]}` (bench `{config['base_signature']}`)."]
    observation = farm["observation"]
    if observation is None:
        return lines + ["", "Official aggregate status and Elo are unavailable; no result is inferred."]
    results, elo, sprt = observation["results"], observation["reported_elo"], observation["sprt"]
    if (source or donor) and results["games"] == 0:
        lines += ["", "Zero games have been reported. Elo and its interval are pending."]
    estimate = "unavailable" if elo["estimate"] is None else f"{elo['estimate']:+.2f}"
    interval = "unavailable" if elo["confidence_interval"] is None else "[" + ", ".join(f"{value:+.2f}" for value in elo["confidence_interval"]) + "]"
    lines += ["", f"Official state: **{observation['status']}**; approved: **{'yes' if observation['approved'] else 'no'}**; "
              f"finished: **{'yes' if observation['finished'] else 'no'}**. "
              "A stale API label means these are the last validated official aggregates.", "",
              "| W / D / L | Points | Games (pairs) | Fishtest logistic Elo | Fishtest nominal 95% CI | Elo availability | SPRT state | LLR |",
              "| ---: | ---: | ---: | ---: | --- | --- | --- | ---: |",
              f"| {results['wins']} / {results['draws']} / {results['losses']} | "
              f"{results['candidate_points']:g}–{results['reference_points']:g} | {results['games']} ({results['pairs']}) | "
              f"{estimate} | {interval} | `{elo['availability']}` | `{sprt['state'] or 'undecided'}` | {sprt['llr']:.6f} |", "",
              "Fishtest's normalized SPRT uses **[0, 2]**, **α = β = 0.05**, and LLR bounds **[−2.944439, +2.944439]**. "
              "Fishtest's nominal 95% CI is an SPRT/Brownian approximation, distinct from the local anytime lower bound. "
              "Official purges can lower the reported counts; this feed follows those counts. "
              "A finished run without an SPRT decision remains stopped/inconclusive. "
              "No farm decision automatically establishes an overall verified gain."]
    if not source and not donor:
        lines += ["", f"Candidate network: `{config['new_nets'][0]}`; reference: `{config['base_nets'][0]}`. "
                  f"Source revisions: `{config['resolved_new']}` / `{config['resolved_base']}`."]
    return lines


def marker_block(snapshot: dict) -> str:
    lines = [START.decode(), "## Live confirmation progress", "",
             f"Trial `{snapshot['trial_id']}` · **provisional, independently unverified** · `60+0.6 / T1 / H64`", "",
             "| Reference | W / D / L | Points | Games (pairs) | Logistic Elo estimate | Anytime lower Elo bound | Statistical decision | Minimum pairs |",
             "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |"]
    for c in snapshot["comparisons"]:
        estimate = elo_text(c["logistic_elo_estimate"], c["estimate_boundary"])
        lower = elo_text(c["anytime_lower_logistic_elo"], c["lower_bound_boundary"])
        minimum = "reached" if c["minimum_pairs_reached"] else "pending"
        lines.append(f"| `{c['reference']}` | {c['wins']} / {c['draws']} / {c['losses']} | "
                     f"{c['candidate_points']:g}–{c['reference_points']:g} | {c['games']} ({c['pairs']}) | "
                     f"{estimate} | {lower} | `{c['statistical_decision']}` | {c['pairs']}/{c['minimum_pairs']} ({minimum}) |")
    confidence = snapshot["comparisons"][0]["one_sided_confidence_percent"]
    threshold = snapshot["comparisons"][0]["log_gain_threshold"]
    lines += ["", f"The paired, one-sided anytime lower bounds use **{confidence:.6f}%** coverage per reference "
              f"(trial allocation: **{snapshot['protocol']['trial_confidence_percent']:.6f}%**; "
              f"whole research family: **{snapshot['protocol']['familywise_confidence_percent']:g}%**). "
              "These are fixed protocol coverage levels under its assumptions, not probabilities that the candidate is stronger.", "",
              f"Each reference needs at least **{snapshot['comparisons'][0]['minimum_pairs']} pairs** and "
              f"log-evidence ≥ **{threshold:.5f}**. Both gates must pass; an independent terminal integrity audit is still required. "
              "Point estimates can rise or fall. Every completed pair in this trial's ledger prefix is retained; interrupted earlier trials are excluded. "
              "`continue` is a statistical decision and does not indicate whether the sampler is running.", "",
              f"Trial ledger state: **{'closed' if snapshot['trial_closed'] else 'open'}**. "
              f"Both statistical gates passed: **{'yes' if snapshot['statistical_pass'] else 'no'}**. "
              "Verified gain: **not established by this progress feed**.", "",
              f"Ledger checkpoint: event `{snapshot['ledger_prefix']['event_index']}`, "
              f"SHA-256 `{snapshot['ledger_prefix']['head_sha256']}`. [Aggregate JSON](results/live-status.json)."]
    if "fishtest" in snapshot:
        lines += farm_marker(snapshot["fishtest"], FISHTEST_RUN_ID)
    if "source_fishtest" in snapshot:
        lines += farm_marker(snapshot["source_fishtest"], SOURCE_FISHTEST_RUN_ID)
    if "donor_fishtest" in snapshot:
        lines += farm_marker(snapshot["donor_fishtest"], DONOR_FISHTEST_RUN_ID)
    lines.append(END.decode())
    return "\n".join(lines)


def without_block(data: bytes) -> bytes:
    if data.count(START) != data.count(END) or data.count(START) > 1:
        raise ProgressError("README progress markers are missing, duplicated, or unbalanced.")
    if START in data and BLOCK.search(data) is None:
        raise ProgressError("README progress markers are out of order.")
    return BLOCK.sub(b"", data).rstrip(b"\r\n")


def render_readme(original: bytes, snapshot: dict) -> bytes:
    without_block(original)  # Validate before editing, retaining all prose bytes.
    newline = b"\r\n" if b"\r\n" in original else b"\n"
    block = marker_block(snapshot).encode("utf-8").replace(b"\n", newline)
    return BLOCK.sub(lambda _: block, original) if START in original else original.rstrip(b"\r\n") + newline * 2 + block + newline


def atomic_replace(path: Path, expected: bytes | None, content: bytes) -> bool:
    if expected == content:
        if read_optional(path) != expected:
            raise ProgressError("An output changed concurrently; no commit was created.")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".live-progress-", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if read_optional(path) != expected:
            raise ProgressError("An output changed concurrently; its edit was preserved.")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return True


def render_files(publication_repo: Path, snapshot: dict) -> dict[str, bytes]:
    before = {name: read_optional(publication_repo / name) for name in OUTPUT_PATHS}
    if before[README_PATH] is None:
        raise ProgressError("The publication worktree needs its reviewed README first.")
    expected = {STATUS_PATH: json_bytes(snapshot), README_PATH: render_readme(before[README_PATH], snapshot)}
    for name in OUTPUT_PATHS:
        atomic_replace(publication_repo / name, before[name], expected[name])
    return expected


def command(repo: Path, *args: str, env: dict | None = None, data: bytes | None = None,
            check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(args, cwd=repo, input=data, capture_output=True, env=env)
    if check and result.returncode:
        raise ProgressError("A publication command failed; no force-push or automatic repair was attempted.")
    return result


def git(repo: Path, *args: str, **kwargs) -> str:
    return command(repo, "git", *args, **kwargs).stdout.decode("utf-8").strip()


def git_path(repo: Path, name: str) -> Path:
    path = Path(git(repo, "rev-parse", "--git-path", name))
    return path if path.is_absolute() else repo / path


@contextmanager
def exclusive_lock(path: Path):
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ProgressError("A publication or Git index lock exists; concurrent work was preserved.") from exc
    os.close(descriptor)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def assert_outputs(repo: Path, expected: dict[str, bytes]) -> None:
    if any(read_optional(repo / name) != content for name, content in expected.items()):
        raise ProgressError("An output changed during publication; the edit was preserved.")


def remote_head(repo: Path, branch: str) -> str:
    result = git(repo, "ls-remote", "--exit-code", "origin", branch).split()
    if len(result) != 2 or result[1] != branch:
        raise ProgressError("The public branch could not be identified safely.")
    return result[0]


def retry_push(repo: Path, journal: Path, branch: str) -> bool:
    if not journal.exists():
        return False
    pending = json.loads(journal.read_bytes())
    head = git(repo, "rev-parse", "HEAD")
    if pending["branch"] != branch:
        raise ProgressError("A pending publication belongs to a different branch.")
    if head == pending["parent"]:
        # A crash before the compare-and-swap never attached the prepared commit.
        journal.unlink()
        return False
    if head != pending["commit"]:
        raise ProgressError("HEAD changed after a failed publication; pending work was preserved.")
    if git(repo, "rev-parse", f"{head}^") != pending["parent"]:
        raise ProgressError("The pending publication's parent differs from its checkpoint.")
    names = git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", head).splitlines()
    if not names or not set(names).issubset(OUTPUT_PATHS):
        raise ProgressError("The pending commit contains files outside the aggregate publication.")
    for name, digest in pending["files"].items():
        blob = command(repo, "git", "show", f"{head}:{name}").stdout
        if sha256(blob) != digest:
            raise ProgressError("The pending publication content differs from its checkpoint.")
    remote = remote_head(repo, branch)
    if remote != head:
        if remote != pending["parent"]:
            raise ProgressError("The public branch advanced independently; a normal manual reconciliation is required.")
        result = command(repo, "git", "push", "origin", f"{head}:{branch}", check=False)
        if result.returncode:
            raise ProgressError("Push failed; the exact pending commit is retained for a normal retry.")
    journal.unlink()
    return True


def commit_snapshot(repo: Path, branch: str, expected: dict[str, bytes], journal: Path) -> bool:
    parent = git(repo, "rev-parse", "HEAD")
    head_readme = command(repo, "git", "show", f"{parent}:{README_PATH}").stdout
    if without_block(head_readme) != without_block(expected[README_PATH]):
        raise ProgressError("Commit reviewed README prose separately before automatic publication.")
    changed = any(command(repo, "git", "show", f"{parent}:{name}", check=False).stdout != content
                  for name, content in expected.items())
    if not changed:
        return False
    index = git_path(repo, "index")
    with exclusive_lock(index.with_name(index.name + ".lock")):
        if command(repo, "git", "diff", "--cached", "--quiet", "--", *OUTPUT_PATHS, check=False).returncode:
            raise ProgressError("An output already has staged edits; its staging was preserved.")
        assert_outputs(repo, expected)
        descriptor, name = tempfile.mkstemp(prefix=".progress-index-", dir=index.parent)
        os.close(descriptor)
        temporary = Path(name)
        temporary.unlink()
        environment = {**os.environ, "GIT_INDEX_FILE": str(temporary),
                       "GIT_AUTHOR_NAME": PUBLIC_NAME, "GIT_AUTHOR_EMAIL": PUBLIC_EMAIL,
                       "GIT_COMMITTER_NAME": PUBLIC_NAME, "GIT_COMMITTER_EMAIL": PUBLIC_EMAIL}
        try:
            blobs = {path: git(repo, "hash-object", "-w", "--stdin", data=data) for path, data in expected.items()}
            def stage_outputs():
                for path, blob in blobs.items():
                    git(repo, "update-index", "--add", "--cacheinfo", f"100644,{blob},{path}", env=environment)
            git(repo, "read-tree", parent, env=environment)
            stage_outputs()
            tree = git(repo, "write-tree", env=environment)
            commit = git(repo, "commit-tree", tree, "-p", parent, env=environment,
                         data=f"Update aggregate confirmation progress ({TRIAL_ID})\n".encode())
            pending = {"branch": branch, "parent": parent, "commit": commit,
                       "files": {path: sha256(data) for path, data in expected.items()}}
            atomic_replace(journal, None, json_bytes(pending))
            # Preserve every unrelated staged entry, updating just our two entries.
            if index.exists():
                temporary.write_bytes(index.read_bytes())
            else:
                temporary.unlink(missing_ok=True)
                git(repo, "read-tree", parent, env=environment)
            stage_outputs()
            assert_outputs(repo, expected)
            git(repo, "update-ref", branch, commit, parent)
            os.replace(temporary, index)
        finally:
            temporary.unlink(missing_ok=True)
    return True


def publish(research_repo: Path, publication_repo: Path, expected: dict[str, bytes]) -> str:
    if research_repo == publication_repo:
        raise ProgressError("Use a separate publication worktree; the research branch stays read only.")
    branch = git(publication_repo, "symbolic-ref", "--quiet", "HEAD")
    if branch != "refs/heads/main":
        raise ProgressError("Automatic publication is restricted to the public main branch.")
    url = git(publication_repo, "remote", "get-url", "origin")
    if url not in {f"https://github.com/{PUBLIC_REPOSITORY}.git", f"https://github.com/{PUBLIC_REPOSITORY}",
                   f"git@github.com:{PUBLIC_REPOSITORY}.git", f"ssh://git@github.com/{PUBLIC_REPOSITORY}.git"}:
        raise ProgressError("Origin is not the authorized public repository.")
    info = json.loads(command(publication_repo, "gh", "repo", "view", PUBLIC_REPOSITORY,
                              "--json", "nameWithOwner,isPrivate").stdout)
    if info.get("nameWithOwner") != PUBLIC_REPOSITORY or info.get("isPrivate") is not False:
        raise ProgressError("The authorized repository has not been confirmed public.")
    with exclusive_lock(git_path(publication_repo, "live-progress-publisher.lock")):
        journal = git_path(publication_repo, "live-progress-publisher.json")
        retried = retry_push(publication_repo, journal, branch)
        if remote_head(publication_repo, branch) != git(publication_repo, "rev-parse", "HEAD"):
            raise ProgressError("The local and public branches differ; unrelated commits will not be pushed.")
        created = commit_snapshot(publication_repo, branch, expected, journal)
        if created:
            retry_push(publication_repo, journal, branch)
        return "Published aggregate progress." if created or retried else "Aggregate progress is unchanged."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--publication-repo", type=Path, required=True)
    parser.add_argument("--stdout", action="store_true", help="Print aggregate JSON only; no file writes or Git publication. An enabled farm still uses public GETs.")
    parser.add_argument("--fishtest-run-id", choices=(FISHTEST_RUN_ID,), help="Include the reviewed public NNUE-only run via unauthenticated official GETs.")
    parser.add_argument("--source-fishtest-run-id", choices=(SOURCE_FISHTEST_RUN_ID,),
                        help="Include the reviewed public test1757 source run via unauthenticated official GETs.")
    parser.add_argument("--donor-fishtest-run-id", choices=(DONOR_FISHTEST_RUN_ID,),
                        help="Include the pinned nine-bias NNUE-versus-donor-parent run via public GETs; not an official-Stockfish comparison.")
    parser.add_argument("--publish", action="store_true", help="Commit just the two generated outputs and push normally.")
    parser.add_argument("--watch", action="store_true", help="Repeat every 30 seconds, including reversals and unchanged checks.")
    args = parser.parse_args(argv)
    if args.stdout and (args.publish or args.watch):
        parser.error("--stdout cannot be combined with --publish or --watch")
    research_repo, publication_repo = args.research_repo.resolve(), args.publication_repo.resolve()
    try:
        if research_repo == publication_repo and not args.stdout:
            raise ProgressError("Use a separate publication worktree; the research branch stays read only.")
        if not args.stdout and Path(git(publication_repo, "rev-parse", "--show-toplevel")).resolve() != publication_repo:
            raise ProgressError("The publication path must be the worktree root.")
        previous = ((previous_snapshot(publication_repo) or {})
                    if args.fishtest_run_id or args.source_fishtest_run_id or args.donor_fishtest_run_id else {})
        fishtest = FishtestObserver(args.fishtest_run_id, previous.get("fishtest")) if args.fishtest_run_id else None
        source_fishtest = (FishtestObserver(args.source_fishtest_run_id, previous.get("source_fishtest"))
                           if args.source_fishtest_run_id else None)
        donor_fishtest = (FishtestObserver(args.donor_fishtest_run_id, previous.get("donor_fishtest"))
                          if args.donor_fishtest_run_id else None)
        while True:
            try:
                if args.stdout:
                    snapshot = build_snapshot(research_repo, previous_snapshot(publication_repo),
                                              fishtest=fishtest, source_fishtest=source_fishtest, donor_fishtest=donor_fishtest)
                    sys.stdout.buffer.write(json_bytes(snapshot))
                    return 0
                # Serialize snapshot+render as well as publishing, so an older
                # sampler cannot overwrite a newer snapshot between processes.
                with exclusive_lock(git_path(publication_repo, "live-progress-render.lock")):
                    snapshot = build_snapshot(research_repo, previous_snapshot(publication_repo),
                                              fishtest=fishtest, source_fishtest=source_fishtest, donor_fishtest=donor_fishtest)
                    expected = render_files(publication_repo, snapshot)
                    message = publish(research_repo, publication_repo, expected) if args.publish else "Rendered aggregate progress locally."
                print(message, flush=True)
            except (ProgressError, OSError, ValueError, KeyError, TypeError) as exc:
                # Native exceptions can contain private source paths or raw data.
                print(str(exc) if isinstance(exc, ProgressError) else "Progress unavailable; inputs were not complete and valid.", file=sys.stderr, flush=True)
                if not args.watch:
                    return 1
            if not args.watch:
                return 0
            time.sleep(30)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
