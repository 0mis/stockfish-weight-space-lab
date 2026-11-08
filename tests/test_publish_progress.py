"""Small synthetic checks; no engines, real ledger writes, or network calls."""

from pathlib import Path
import json
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import publish_progress as progress


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.stats = progress.load_stats(Path(__file__).resolve().parents[1])
        spec = {"candidate": {"label": "d1-fc2-s102-t128", "engine_sha256": "d" * 64,
                              "network_sha256": "e" * 64},
                "baselines": [{"id": name, "role": role} for name, role in progress.REFERENCES.items()],
                "settings": {"time_control": "60+0.6", "threads_per_engine": 1,
                             "hash_mb_per_engine": 64, "fresh_engines_per_pair": True},
                "min_pairs": 128, "max_pairs": 8192}
        reservation = {"trial_id": progress.TRIAL_ID, "spec": spec,
                       "spec_sha256": self.stats.digest(spec), "trial_alpha": 1 / 1200,
                       "alpha_per_baseline": 1 / 2400}
        directory = self.root / progress.TRIAL_DIRECTORY
        directory.mkdir(parents=True)
        (directory / "reservation.json").write_bytes(progress.json_bytes(reservation))
        pair = {"pair_index": 0, "candidate_white_score": 1, "candidate_black_score": 0.5}
        self.events = [
            {"index": 0, "sha256": "a" * 64, "payload": {"type": "initialize", "protocol": {"statistics": {"familywise_alpha": 0.01}}}},
            {"index": 1, "sha256": "b" * 64, "payload": {"type": "pairs", "trial_id": "trial-0002", "baseline_id": "spcc-261025", "pairs": [pair]}},
            {"index": 2, "sha256": "c" * 64, "payload": {"type": "pairs", "trial_id": progress.TRIAL_ID, "baseline_id": "spcc-261025", "pairs": [pair]}},
        ]
        status = {"closed_reason": None, "statistical_pass": False,
                  "comparisons": {name: self.stats.sequential_evidence(
                      [0, 0, 0, 1, 0] if name == "spcc-261025" else [0] * 5,
                      alpha=1 / 2400) for name in progress.REFERENCES}}
        ledger = SimpleNamespace(_events=lambda: self.events, _trials=lambda events: {progress.TRIAL_ID: reservation},
                                 _status=lambda events, trial_id: status)
        module = SimpleNamespace(AlphaLedger=lambda path: ledger, AUTHORITATIVE_LEDGER="fixture",
                                 digest=self.stats.digest, METHOD=self.stats.METHOD)
        self.loader = patch.object(progress, "load_stats", return_value=module)
        self.loader.start()
        self.addCleanup(self.loader.stop)
        self.snapshot = progress.build_snapshot(self.root)

    def test_aggregate_filters_old_trial_and_handles_empty_reference(self):
        rated, development = self.snapshot["comparisons"]
        self.assertEqual((rated["wins"], rated["draws"], rated["losses"], rated["games"]), (1, 1, 0, 2))
        self.assertEqual((development["pairs"], development["logistic_elo_estimate"]), (0, None))
        self.assertFalse(self.snapshot["completion_verified"])
        encoded = progress.json_bytes(self.snapshot).decode()
        for private in (str(self.root), "opening_id", "artifact", "trial-0002", "pid"):
            self.assertNotIn(private, encoded)
        self.assertEqual(progress.build_snapshot(self.root, self.snapshot), self.snapshot)

    def test_missing_data_and_checkpoint_rollback_refuse(self):
        (self.root / progress.TRIAL_DIRECTORY / "reservation.json").unlink()
        with self.assertRaises(OSError):
            progress.build_snapshot(self.root)
        self.events.pop()
        with self.assertRaises(progress.ProgressError):
            progress.build_snapshot(self.root, self.snapshot)

    def test_render_preserves_prose_and_is_idempotent(self):
        for original in (b"# Example\n\nKeep this prose.\n", b"# Example\r\n\r\nKeep this prose.\r\n"):
            rendered = progress.render_readme(original, self.snapshot)
            self.assertEqual(progress.without_block(rendered), original.rstrip(b"\r\n"))
            self.assertEqual(progress.render_readme(rendered, self.snapshot), rendered)
            self.assertEqual(rendered.count(progress.START), 1)
        with self.assertRaises(progress.ProgressError):
            progress.render_readme(progress.START, self.snapshot)

    def test_concurrent_file_edit_is_preserved(self):
        target = self.root / "file.txt"
        target.write_bytes(b"user edit")
        with self.assertRaises(progress.ProgressError):
            progress.atomic_replace(target, b"old", b"new")
        self.assertEqual(target.read_bytes(), b"user edit")

    def test_commit_is_idempotent_and_preserves_unrelated_staging(self):
        repo = self.root / "publication"
        repo.mkdir()
        progress.git(repo, "init", "--initial-branch=main")
        (repo / "README.md").write_bytes(b"# Example\n")
        (repo / "unrelated.txt").write_bytes(b"original\n")
        progress.git(repo, "add", "README.md", "unrelated.txt")
        progress.git(repo, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                     "commit", "-m", "Fixture")
        (repo / "unrelated.txt").write_bytes(b"staged user edit\n")
        progress.git(repo, "add", "unrelated.txt")
        (repo / "untracked.txt").write_bytes(b"private untracked fixture\n")
        expected = progress.render_files(repo, self.snapshot)
        journal = progress.git_path(repo, "live-progress-publisher.json")
        self.assertTrue(progress.commit_snapshot(repo, "refs/heads/main", expected, journal))
        changed = progress.git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines()
        self.assertEqual(set(changed), set(progress.OUTPUT_PATHS))
        self.assertEqual(progress.git(repo, "show", "HEAD:unrelated.txt"), "original")
        self.assertEqual(progress.git(repo, "show", ":unrelated.txt"), "staged user edit")
        self.assertEqual(progress.git(repo, "show", "-s", "--format=%an <%ae>|%cn <%ce>", "HEAD"),
                         f"{progress.PUBLIC_NAME} <{progress.PUBLIC_EMAIL}>|{progress.PUBLIC_NAME} <{progress.PUBLIC_EMAIL}>")
        self.assertFalse(progress.commit_snapshot(repo, "refs/heads/main", expected, journal))
        self.assertTrue(journal.exists())  # A failed/unattempted push retains the exact commit.
        checkpoint = json.loads(journal.read_bytes())
        original_command = progress.command
        def failed_push(repository, *args, **kwargs):
            if args[:2] == ("git", "push"):
                return subprocess.CompletedProcess(args, 1, b"", b"synthetic failure")
            return original_command(repository, *args, **kwargs)
        with patch.object(progress, "remote_head", return_value=checkpoint["parent"]), \
                patch.object(progress, "command", side_effect=failed_push):
            with self.assertRaisesRegex(progress.ProgressError, "exact pending commit"):
                progress.retry_push(repo, journal, "refs/heads/main")
        self.assertEqual(json.loads(journal.read_bytes())["commit"], checkpoint["commit"])
        with patch.object(progress, "remote_head", return_value=progress.git(repo, "rev-parse", "HEAD")):
            self.assertTrue(progress.retry_push(repo, journal, "refs/heads/main"))
        self.assertFalse(journal.exists())


if __name__ == "__main__":
    unittest.main()
