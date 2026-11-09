"""Small synthetic checks; no engines, real ledger writes, or network calls."""

from pathlib import Path
import copy
import json
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

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

    def test_farm_outage_keeps_local_result_separate_and_publishable(self):
        farm = progress.FishtestObserver(progress.FISHTEST_RUN_ID, fetch=Mock(side_effect=OSError), clock=lambda: 0)
        combined = progress.build_snapshot(self.root, fishtest=farm)
        self.assertEqual(combined["comparisons"], self.snapshot["comparisons"])
        self.assertEqual(combined["candidate"], self.snapshot["candidate"])
        self.assertFalse(combined["completion_verified"])
        self.assertEqual(combined["fishtest"]["availability"], "unavailable")
        self.assertIn("separate NNUE-only experiment", progress.marker_block(combined))

    def test_farm_sprt_acceptance_never_sets_overall_verified_gain(self):
        run = FishtestTests.run_fixture()
        run["finished"] = True
        run["args"]["sprt"].update(state="accepted", llr=3.1)
        run["elo"] = {"elo": 1.25, "ci": [-2.5, 5.0]}
        farm = progress.FishtestObserver(progress.FISHTEST_RUN_ID, fetch=Mock(return_value=run), clock=lambda: 0)
        combined = progress.build_snapshot(self.root, fishtest=farm)
        self.assertEqual(combined["fishtest"]["observation"]["status"], "sprt_accepted")
        self.assertEqual(combined["comparisons"], self.snapshot["comparisons"])
        self.assertFalse(combined["completion_verified"])
        self.assertFalse(combined["statistical_pass"])

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


class FishtestTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.run = self.run_fixture()
        self.responses = {"get_run": self.run, "get_elo": {**copy.deepcopy(self.run), "elo": {"elo": 1.25, "ci": [-2.5, 5.0]}}}
        def fetch(endpoint, run_id):
            self.assertEqual(run_id, progress.FISHTEST_RUN_ID)
            value = self.responses[endpoint]
            if isinstance(value, Exception):
                raise value
            return copy.deepcopy(value)
        self.fetch = Mock(side_effect=fetch)
        self.observer = progress.FishtestObserver(progress.FISHTEST_RUN_ID, fetch=self.fetch, clock=lambda: self.now)

    @staticmethod
    def run_fixture(games=8):
        return {"_id": progress.FISHTEST_RUN_ID, "approved": True, "finished": False,
                "failed": False, "deleted": False,
                "args": {**copy.deepcopy(progress.FISHTEST_ARGS), "num_games": 800000,
                         "sprt": {**progress.FISHTEST_SPRT, "state": "", "llr": 0.2},
                         "username": "private fixture identity", "info": "C:\\private\\fixture"},
                "results": {"wins": 0, "draws": games, "losses": 0,
                            "pentanomial": [0, 0, games // 2, 0, 0], "crashes": 0, "time_losses": 0},
                "last_updated": "an observation clock", "tasks": [{"worker_info": "private fixture host"}]}

    def test_zero_games_are_null_and_pending_approval_is_explicit(self):
        self.responses["get_run"] = self.run_fixture(0)
        self.responses["get_run"]["approved"] = False
        farm = self.observer.observe()
        observation = farm["observation"]
        self.assertEqual(observation["status"], "pending_approval")
        self.assertEqual(observation["results"]["games"], 0)
        self.assertEqual(observation["reported_elo"]["availability"], "no_games")
        self.assertEqual(observation["reported_elo"]["estimate_scale"], "logistic")
        self.assertEqual(observation["reported_elo"]["confidence_percent"], 95)
        self.assertIsNone(observation["reported_elo"]["estimate"])
        self.assertIsNone(observation["reported_elo"]["confidence_interval"])
        self.fetch.assert_called_once_with("get_run", progress.FISHTEST_RUN_ID)

    def test_logistic_estimate_and_nominal_interval_have_distinct_sprt_labels(self):
        farm = self.observer.observe()
        elo = farm["observation"]["reported_elo"]
        self.assertEqual((elo["estimate_scale"], elo["confidence_percent"]), ("logistic", 95))
        self.assertEqual((elo["model"], elo["model_scope"]), ("normalized", "SPRT"))
        self.assertEqual(elo["label"], "Fishtest logistic Elo and nominal 95% CI")
        rendered = "\n".join(progress.farm_marker(farm))
        self.assertIn("Fishtest logistic Elo", rendered)
        self.assertIn("Fishtest nominal 95% CI", rendered)
        self.assertIn("SPRT/Brownian approximation, distinct from the local anytime lower bound", rendered)
        self.assertIn("normalized SPRT", rendered)

    def test_farm_throttle_and_clock_changes_leave_identical_output(self):
        first = self.observer.observe()
        self.assertEqual(self.fetch.call_count, 2)
        self.now = 30
        self.assertEqual(self.observer.observe(), first)
        self.assertEqual(self.fetch.call_count, 2)
        self.now = 60
        self.responses["get_run"]["last_updated"] = "a different clock"
        self.responses["get_elo"]["last_updated"] = "another clock"
        self.assertEqual(progress.json_bytes(self.observer.observe()), progress.json_bytes(first))
        self.assertEqual(self.fetch.call_count, 4)
        encoded = progress.json_bytes(first).decode()
        for private in ("private fixture", "C:\\", "last_updated", "worker_info", '"tasks"', '"username"'):
            self.assertNotIn(private, encoded)

    def test_pinned_configuration_and_wdl_penta_are_validated(self):
        mutations = [
            lambda r: r.update(_id="0" * 24),
            lambda r: r["args"].update(resolved_new="0" * 40),
            lambda r: r["args"].update(resolved_base="0" * 40),
            lambda r: r["args"].update(new_nets=["nn-000000000000.nnue"]),
            lambda r: r["args"].update(base_nets=["nn-000000000000.nnue"]),
            lambda r: r["args"].update(tc="60+0.6"),
            lambda r: r["args"].update(new_tc="60+0.6"),
            lambda r: r["args"].update(threads=True),
            lambda r: r["args"].update(new_options="Hash=64"),
            lambda r: r["args"].update(base_options="Hash=64"),
            lambda r: r["args"].update(new_signature="0"),
            lambda r: r["args"]["sprt"].update(elo_model="logistic"),
            lambda r: r["results"].update(wins=-1),
            lambda r: r["results"].update(pentanomial=[0, 0, 1, 0, 0]),
            lambda r: r["results"].update(wins=8, draws=0),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutations.index(mutate)):
                run = copy.deepcopy(self.run)
                mutate(run)
                with self.assertRaises(progress.ProgressError):
                    progress.farm_observation(run)

    def test_actual_terminal_states_remain_distinct(self):
        cases = [({"approved": False}, "", "pending_approval"),
                 ({}, "", "approved_open"),
                 ({"finished": True}, "accepted", "sprt_accepted"),
                 ({"finished": True}, "rejected", "sprt_rejected"),
                 ({"finished": True}, "", "stopped_without_sprt_decision"),
                 ({"finished": True, "deleted": True}, "", "cancelled_deleted"),
                 ({"finished": True, "failed": True}, "", "failed")]
        for flags, state, expected in cases:
            with self.subTest(status=expected):
                run = copy.deepcopy(self.run)
                run.update(flags)
                run["args"]["sprt"]["state"] = state
                self.assertEqual(progress.farm_observation(run)["status"], expected)
        run["failed"] = False
        run["args"]["num_games"] = 8
        self.assertEqual(progress.farm_observation(run)["status"], "inconclusive_game_cap")

    def test_outage_retains_last_valid_observation_and_recovers(self):
        first = self.observer.observe()
        self.responses["get_run"] = OSError("synthetic public API outage")
        self.now = 60
        stale = self.observer.observe()
        self.assertEqual(stale["availability"], "stale")
        self.assertEqual(stale["observation"]["results"], first["observation"]["results"])
        self.assertEqual(stale["observation"]["reported_elo"]["availability"], "stale")
        self.now = 120
        self.assertEqual(self.observer.observe(), stale)
        self.responses["get_run"] = self.run
        self.now = 180
        self.assertEqual(self.observer.observe(), first)

    def test_purged_counts_decrease_and_mismatched_or_failed_elo_is_not_reused(self):
        first = self.observer.observe()
        self.responses["get_elo"] = OSError("synthetic Elo outage")
        self.now = 60
        stale_elo = self.observer.observe()
        self.assertEqual(stale_elo["availability"], "current")
        self.assertEqual(stale_elo["observation"]["reported_elo"]["estimate"], 1.25)
        self.assertEqual(stale_elo["observation"]["reported_elo"]["availability"], "stale")
        self.responses["get_run"] = self.run_fixture(2)
        self.responses["get_elo"] = {**copy.deepcopy(self.run), "elo": {"elo": 99, "ci": [90, 100]}}
        self.now = 120
        purged = self.observer.observe()
        self.assertLess(purged["observation"]["results"]["games"], first["observation"]["results"]["games"])
        self.assertEqual(purged["observation"]["results"]["games"], 2)
        self.assertIsNone(purged["observation"]["reported_elo"]["estimate"])
        self.responses["get_elo"] = {**self.run_fixture(2), "elo": {"elo": float("nan"), "ci": [-1, 1]}}
        self.now = 180
        self.assertIsNone(self.observer.observe()["observation"]["reported_elo"]["estimate"])

    def test_saved_observation_is_revalidated_and_extra_fields_are_discarded(self):
        previous = self.observer.observe()
        previous["observation"]["private_path"] = "C:\\private\\fixture"
        previous["observation"]["reported_elo"]["label"] = "private fixture label"
        # Older saved feeds lack the explicit estimate-scale/coverage metadata.
        previous["observation"]["reported_elo"].pop("estimate_scale")
        previous["observation"]["reported_elo"].pop("confidence_percent")
        restored = progress.FishtestObserver(progress.FISHTEST_RUN_ID, previous,
                                            fetch=Mock(side_effect=OSError), clock=lambda: 0).observe()
        self.assertEqual(restored["availability"], "stale")
        self.assertEqual(restored["observation"]["results"]["games"], 8)
        elo = restored["observation"]["reported_elo"]
        self.assertEqual((elo["estimate_scale"], elo["confidence_percent"]), ("logistic", 95))
        self.assertEqual((elo["model"], elo["model_scope"]), ("normalized", "SPRT"))
        self.assertEqual(elo["label"], "Fishtest logistic Elo and nominal 95% CI")
        self.assertEqual(elo["availability"], "stale")
        self.assertNotIn("private", progress.json_bytes(restored).decode())
        previous["observation"]["results"]["wins"] = -1
        invalid = progress.FishtestObserver(progress.FISHTEST_RUN_ID, previous,
                                           fetch=Mock(side_effect=OSError), clock=lambda: 0).observe()
        self.assertEqual(invalid["availability"], "unavailable")


if __name__ == "__main__":
    unittest.main()
