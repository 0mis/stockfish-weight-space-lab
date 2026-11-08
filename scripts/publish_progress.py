"""Publish aggregate confirmation progress, never engines or raw research data.

The research worktree is read only.  The publication worktree receives just a
JSON snapshot and a bounded README block.  Network access requires --publish;
--watch polls every 30 seconds and publishes reversals as well as increases.
Statistical success always remains pending independent terminal integrity audit.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


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


class ProgressError(Exception):
    """A bounded, public-safe diagnostic; raw paths and subprocess logs stay out."""


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def build_snapshot(research_repo: Path, previous: dict | None = None) -> dict:
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
    return {
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


def elo_text(value: float | None, boundary: str | None) -> str:
    if boundary == "negative_infinity":
        return "−∞"
    if boundary == "positive_infinity":
        return "+∞"
    return "pending" if value is None else f"{value:+.2f}"


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
              f"SHA-256 `{snapshot['ledger_prefix']['head_sha256']}`. [Aggregate JSON](results/live-status.json).",
              END.decode()]
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
    parser.add_argument("--stdout", action="store_true", help="Print aggregate JSON only; do not write files or use the network.")
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
        while True:
            try:
                if args.stdout:
                    snapshot = build_snapshot(research_repo, previous_snapshot(publication_repo))
                    sys.stdout.buffer.write(json_bytes(snapshot))
                    return 0
                # Serialize snapshot+render as well as publishing, so an older
                # sampler cannot overwrite a newer snapshot between processes.
                with exclusive_lock(git_path(publication_repo, "live-progress-render.lock")):
                    snapshot = build_snapshot(research_repo, previous_snapshot(publication_repo))
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
