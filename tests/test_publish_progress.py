"""Small synthetic checks; no engines, real ledger writes, or network calls."""

from pathlib import Path
import copy
import io
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

    def test_two_farms_keep_their_own_slots_and_pending_markers(self):
        old = FishtestTests.run_fixture(8)
        old["elo"] = {"elo": -1.5, "ci": [-3, 1]}
        new = SourceFishtestTests.source_fixture(0)
        new["approved"] = False
        d1 = progress.FishtestObserver(progress.FISHTEST_RUN_ID, fetch=Mock(return_value=old), clock=lambda: 0)
        source_fetch = Mock(return_value=new)
        source = progress.FishtestObserver(progress.SOURCE_FISHTEST_RUN_ID, fetch=source_fetch, clock=lambda: 0)
        combined = progress.build_snapshot(self.root, fishtest=d1, source_fishtest=source)
        self.assertEqual({k: combined[k] for k in self.snapshot}, self.snapshot)
        self.assertEqual(combined["fishtest"], progress.build_snapshot(self.root, fishtest=d1)["fishtest"])
        self.assertNotIn("source_fishtest", progress.build_snapshot(self.root, fishtest=d1))
        self.assertNotIn("fishtest", progress.build_snapshot(self.root, source_fishtest=source))
        self.assertEqual(combined["fishtest"]["observation"]["reported_elo"]["estimate"], -1.5)
        pending = combined["source_fishtest"]["observation"]
        self.assertEqual(pending["status"], "pending_approval")
        self.assertEqual(pending["results"]["games"], 0)
        self.assertEqual(pending["reported_elo"], progress.null_farm_elo("no_games"))
        source_fetch.assert_called_once_with("get_run", progress.SOURCE_FISHTEST_RUN_ID)
        d1_section, source_section = progress.marker_block(combined).split("### Public Fishtest test1757 source and network test")
        self.assertIn(progress.FISHTEST_RUN_ID, d1_section)
        self.assertNotIn(progress.SOURCE_FISHTEST_RUN_ID, d1_section)
        for value in (progress.SOURCE_FISHTEST_RUN_ID, "pending_approval", "Elo and its interval are pending",
                      "nn-18cd32e11a9c.nnue", "3464885", "1556650", progress.SOURCE_TREE, progress.SOURCE_TESTED_COMMIT):
            self.assertIn(value, source_section)
        self.assertNotIn(progress.FISHTEST_RUN_ID, source_section)
        self.assertNotIn("nn-fcbaf7d2197c.nnue", source_section)
        with self.assertRaises(progress.ProgressError):
            progress.build_snapshot(self.root, fishtest=source)
        with self.assertRaises(progress.ProgressError):
            progress.build_snapshot(self.root, source_fishtest=d1)
        with self.assertRaises(progress.ProgressError):
            progress.marker_block({**combined, "source_fishtest": combined["fishtest"]})

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

    def test_third_donor_run_preserves_both_prior_runs_and_formal_snapshot(self):
        old_run = FishtestTests.run_fixture()
        old_run["elo"] = {"elo": -1.5, "ci": [-3, 1]}
        source_run = SourceFishtestTests.source_fixture()
        source_run["elo"] = {"elo": 2.0, "ci": [-2, 6]}
        old = progress.FishtestObserver(progress.FISHTEST_RUN_ID, fetch=Mock(return_value=old_run), clock=lambda: 0)
        source = progress.FishtestObserver(progress.SOURCE_FISHTEST_RUN_ID, fetch=Mock(return_value=source_run), clock=lambda: 0)
        before = progress.build_snapshot(self.root, fishtest=old, source_fishtest=source)
        donor = progress.FishtestObserver(progress.DONOR_FISHTEST_RUN_ID,
                                         fetch=Mock(return_value=DonorFishtestTests.donor_fixture()), clock=lambda: 0)
        combined = progress.build_snapshot(self.root, fishtest=old, source_fishtest=source, donor_fishtest=donor)
        self.assertEqual({key: combined[key] for key in before}, before)
        self.assertEqual({key: combined[key] for key in self.snapshot}, self.snapshot)
        self.assertEqual(set(combined) - set(before), {"donor_fishtest"})
        rendered = progress.marker_block(combined)
        prefix, donor_section = rendered.split("### Public Fishtest NNUE edit vs donor parent")
        self.assertEqual(prefix.rstrip(), progress.marker_block(before).removesuffix(progress.END.decode()).rstrip())
        for value in ("donor parent", "not an official-Stockfish comparison", "2376690", "3464885",
                      "nn-d5c257728ba5.nnue", "nn-18cd32e11a9c.nnue", "Elo and its interval are pending"):
            self.assertIn(value, donor_section)
        for other_run in (progress.FISHTEST_RUN_ID, progress.SOURCE_FISHTEST_RUN_ID):
            self.assertNotIn(other_run, donor_section)
        self.assertNotIn("donor_fishtest", progress.build_snapshot(self.root, fishtest=old, source_fishtest=source))
        with self.assertRaises(progress.ProgressError):
            progress.build_snapshot(self.root, donor_fishtest=source)
        with self.assertRaises(progress.ProgressError):
            progress.build_snapshot(self.root, fishtest=donor)
        with self.assertRaises(progress.ProgressError):
            progress.marker_block({**combined, "donor_fishtest": combined["source_fishtest"]})

    def test_donor_sprt_decision_does_not_alter_local_formal_status(self):
        run = DonorFishtestTests.donor_fixture(8)
        run.update(finished=True, approved=True)
        run["args"]["sprt"].update(state="accepted", llr=3.1)
        run["elo"] = {"elo": 1.5, "ci": [-1, 4]}
        donor = progress.FishtestObserver(progress.DONOR_FISHTEST_RUN_ID, fetch=Mock(return_value=run), clock=lambda: 0)
        snapshot = progress.build_snapshot(self.root, donor_fishtest=donor)
        self.assertEqual(snapshot["donor_fishtest"]["observation"]["status"], "sprt_accepted")
        self.assertEqual({key: snapshot[key] for key in self.snapshot}, self.snapshot)
        self.assertFalse(snapshot["completion_verified"])
        self.assertFalse(snapshot["statistical_pass"])

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


class SourceFishtestTests(unittest.TestCase):
    @staticmethod
    def source_fixture(games=8):
        run = FishtestTests.run_fixture(games)
        run["_id"] = progress.SOURCE_FISHTEST_RUN_ID
        run["args"].update(copy.deepcopy(progress.SOURCE_FISHTEST_ARGS))
        return run

    def test_pins_and_redirect_target_allowlist(self):
        self.assertEqual(progress.SOURCE_FISHTEST_RUN_ID, "6af16e648e7fb2e78bc1cb09")
        self.assertEqual(set(progress.FISHTEST_CONFIGS), {progress.FISHTEST_RUN_ID, progress.SOURCE_FISHTEST_RUN_ID,
                                                        progress.DONOR_FISHTEST_RUN_ID})
        self.assertEqual(progress.SOURCE_FISHTEST_ARGS["resolved_new"], "de342a301195b34b7da76374fe3fadf29352de8d")
        self.assertEqual(progress.SOURCE_FISHTEST_ARGS["resolved_base"], "7cdd5e89a39fe3071b67d91c7bb07d712044bf76")
        self.assertEqual(progress.SOURCE_FISHTEST_ARGS["base_nets"], ["nn-d1ee674a62ca.nnue"])
        self.assertEqual(progress.farm_observation(self.source_fixture())["results"]["games"], 8)
        for key, bad in (("resolved_new", progress.FISHTEST_ARGS["resolved_new"]), ("new_nets", progress.FISHTEST_ARGS["new_nets"]),
                         ("new_signature", "2261721"), ("base_nets", []), ("book", "different.epd"),
                         ("book_depth", 8), ("auto_purge", 0), ("adjudication", 1), ("num_games", 8),
                         ("new_net", "nn-fcbaf7d2197c.nnue"), ("threads", True)):
            with self.subTest(key=key):
                run = self.source_fixture()
                run["args"][key] = bad
                with self.assertRaises(progress.ProgressError):
                    progress.farm_observation(run, progress.SOURCE_FISHTEST_RUN_ID)
        with patch.object(progress.urllib.request, "build_opener") as http:
            for endpoint, run_id in (("get_run", "0" * 24), ("get_elo?redirect=1", progress.SOURCE_FISHTEST_RUN_ID)):
                with self.assertRaises(progress.ProgressError):
                    progress.fetch_fishtest_json(endpoint, run_id)
            http.assert_not_called()

    def test_other_run_or_result_prefix_never_supplies_source_elo(self):
        source_id = progress.SOURCE_FISHTEST_RUN_ID
        source = self.source_fixture()
        old = FishtestTests.run_fixture()
        elo = {"elo": 17.0, "ci": [10, 20]}
        for wrong in (old, self.source_fixture(2)):
            fetch = Mock(side_effect=[source, {**wrong, "elo": elo}])
            view = progress.FishtestObserver(source_id, fetch=fetch, clock=lambda: 0).observe()
            self.assertEqual(view["availability"], "current")
            self.assertEqual(view["observation"]["reported_elo"], progress.null_farm_elo("unavailable"))
        for requested, returned in ((source_id, old), (progress.FISHTEST_RUN_ID, source)):
            view = progress.FishtestObserver(requested, fetch=Mock(return_value=returned), clock=lambda: 0).observe()
            self.assertIsNone(view["observation"])
            self.assertEqual(view["availability"], "unavailable")

    def test_cache_validation_and_per_run_throttling(self):
        runs = {progress.FISHTEST_RUN_ID: FishtestTests.run_fixture(),
                progress.SOURCE_FISHTEST_RUN_ID: self.source_fixture()}
        expected = {progress.FISHTEST_RUN_ID: -3.0, progress.SOURCE_FISHTEST_RUN_ID: 7.0}
        def fetch(endpoint, run_id):
            return {**runs[run_id], "elo": {"elo": expected[run_id], "ci": [-5, 10]}}
        calls = Mock(side_effect=fetch)
        now = 0
        observers = {k: progress.FishtestObserver(k, fetch=calls, clock=lambda: now) for k in runs}
        old = observers[progress.FISHTEST_RUN_ID].observe()
        now = 30
        source = observers[progress.SOURCE_FISHTEST_RUN_ID].observe()
        self.assertEqual(calls.call_count, 4)
        now = 60
        observers[progress.FISHTEST_RUN_ID].observe()
        self.assertEqual(observers[progress.SOURCE_FISHTEST_RUN_ID].observe(), source)
        self.assertEqual(calls.call_count, 6)
        now = 90
        calls.side_effect = OSError("fixture outage")
        stale = observers[progress.SOURCE_FISHTEST_RUN_ID].observe()
        self.assertEqual(stale["availability"], "stale")
        self.assertEqual(stale["observation"]["reported_elo"]["estimate"], 7.0)
        self.assertEqual(observers[progress.FISHTEST_RUN_ID].observe()["availability"], "current")
        def restored(run_id, prior):
            return progress.FishtestObserver(run_id, prior, fetch=Mock(side_effect=OSError), clock=lambda: 0).observe()
        for run_id, own, other in ((progress.FISHTEST_RUN_ID, old, source), (progress.SOURCE_FISHTEST_RUN_ID, source, old)):
            self.assertIsNone(restored(run_id, other)["observation"])
            cache = copy.deepcopy(own)
            cache["private"] = "private fixture"
            cache["observation"]["private"] = "private fixture"
            checked = restored(run_id, cache)
            self.assertEqual(checked["observation"]["reported_elo"]["estimate"], expected[run_id])
            self.assertNotIn("private fixture", progress.json_bytes(checked).decode())
            cache["configuration"]["threads"] = True
            self.assertIsNone(restored(run_id, cache)["observation"])


class DonorFishtestTests(unittest.TestCase):
    @staticmethod
    def donor_fixture(games=0):
        run = FishtestTests.run_fixture(games)
        run["_id"] = progress.DONOR_FISHTEST_RUN_ID
        run["approved"] = games > 0
        run["args"].update(copy.deepcopy(progress.DONOR_FISHTEST_ARGS))
        return run

    def test_donor_pins_owner_source_nets_signatures_and_protocol(self):
        self.assertEqual(progress.DONOR_FISHTEST_RUN_ID, "6af19afb8e7fb2e78bc1cb30")
        self.assertEqual(progress.DONOR_FISHTEST_ARGS["resolved_new"], "d7155994d192b4e723866360ae9285b42e122790")
        self.assertEqual(progress.DONOR_FISHTEST_ARGS["resolved_base"], progress.SOURCE_FISHTEST_ARGS["resolved_new"])
        self.assertEqual(progress.DONOR_FISHTEST_ARGS["new_signature"], "2376690")
        self.assertEqual(progress.DONOR_FISHTEST_ARGS["base_signature"], "3464885")
        self.assertEqual(progress.DONOR_FISHTEST_ARGS["username"], "0mis")
        for key, bad in (("resolved_new", progress.SOURCE_FISHTEST_ARGS["resolved_new"]),
                         ("resolved_base", progress.SOURCE_FISHTEST_ARGS["resolved_base"]),
                         ("new_nets", ["nn-18cd32e11a9c.nnue"]), ("base_nets", ["nn-d1ee674a62ca.nnue"]),
                         ("new_signature", "3230034"), ("base_signature", "1556650"),
                         ("username", "another-user"), ("username", True), ("threads", True),
                         ("book_depth", 8), ("num_games", 8), ("new_options", "Hash=64"),
                         ("new_net", "nn-fcbaf7d2197c.nnue"), ("tests_repo", "https://example.invalid/Stockfish")):
            changed = self.donor_fixture()
            changed["args"][key] = bad
            with self.subTest(key=key), self.assertRaises(progress.ProgressError):
                progress.farm_observation(changed, progress.DONOR_FISHTEST_RUN_ID)
        with patch.object(progress.urllib.request, "build_opener") as http:
            for endpoint, run_id in (("submit", progress.DONOR_FISHTEST_RUN_ID), ("get_run", "0" * 24)):
                with self.assertRaises(progress.ProgressError):
                    progress.fetch_fishtest_json(endpoint, run_id)
            http.assert_not_called()

    def test_real_zero_shape_has_no_estimate_and_no_elo_fetch(self):
        for approved, finished, expected in ((False, False, "pending_approval"), (True, False, "approved_open"),
                                              (True, True, "stopped_without_sprt_decision")):
            run = self.donor_fixture()
            run.update(approved=approved, finished=finished)
            fetch = Mock(return_value=run)
            farm = progress.FishtestObserver(progress.DONOR_FISHTEST_RUN_ID, fetch=fetch, clock=lambda: 0).observe()
            observation = farm["observation"]
            self.assertEqual(observation["status"], expected)
            self.assertEqual(observation["results"]["games"], 0)
            self.assertEqual(observation["reported_elo"], progress.null_farm_elo("no_games"))
            self.assertEqual(farm["comparison_scope"], "donor_parent_only")
            self.assertIn("Elo and its interval are pending", "\n".join(progress.farm_marker(farm)))
            fetch.assert_called_once_with("get_run", progress.DONOR_FISHTEST_RUN_ID)
            encoded = progress.json_bytes(farm).decode()
            for private in ("C:\\", "private fixture", "worker_info", '"tasks"', '"info"'):
                self.assertNotIn(private, encoded)

    def test_foreign_or_mismatched_prefix_cannot_supply_donor_elo(self):
        run = self.donor_fixture(8)
        for other in (FishtestTests.run_fixture(), SourceFishtestTests.source_fixture(), self.donor_fixture(2)):
            fetch = Mock(side_effect=[run, {**other, "elo": {"elo": 99, "ci": [90, 100]}}])
            farm = progress.FishtestObserver(progress.DONOR_FISHTEST_RUN_ID, fetch=fetch, clock=lambda: 0).observe()
            self.assertEqual(farm["availability"], "current")
            self.assertEqual(farm["observation"]["results"]["games"], 8)
            self.assertIsNone(farm["observation"]["reported_elo"]["estimate"])
        bad = self.donor_fixture(8)
        bad["results"]["wins"] = -1
        farm = progress.FishtestObserver(progress.DONOR_FISHTEST_RUN_ID, fetch=Mock(return_value=bad), clock=lambda: 0).observe()
        self.assertIsNone(farm["observation"])

    def test_three_caches_are_isolated_throttled_and_restore_only_own_results(self):
        runs = {progress.FISHTEST_RUN_ID: FishtestTests.run_fixture(),
                progress.SOURCE_FISHTEST_RUN_ID: SourceFishtestTests.source_fixture(),
                progress.DONOR_FISHTEST_RUN_ID: self.donor_fixture(8)}
        estimates = dict(zip(runs, (-3.0, 7.0, 1.5)))
        now = 0
        def fetch(endpoint, run_id):
            return {**copy.deepcopy(runs[run_id]), "elo": {"elo": estimates[run_id], "ci": [-5, 10]}}
        calls = Mock(side_effect=fetch)
        observers = {key: progress.FishtestObserver(key, fetch=calls, clock=lambda: now) for key in runs}
        saved = {}
        for when, key in zip((0, 30, 45), runs):
            now = when
            saved[key] = observers[key].observe()
        self.assertEqual(calls.call_count, 6)
        now = 59
        for key in runs:
            self.assertEqual(observers[key].observe(), saved[key])
        self.assertEqual(calls.call_count, 6)
        now = 60
        observers[progress.FISHTEST_RUN_ID].observe()
        self.assertEqual(calls.call_count, 8)
        self.assertEqual(observers[progress.SOURCE_FISHTEST_RUN_ID].observe(), saved[progress.SOURCE_FISHTEST_RUN_ID])
        self.assertEqual(observers[progress.DONOR_FISHTEST_RUN_ID].observe(), saved[progress.DONOR_FISHTEST_RUN_ID])
        for key, own in saved.items():
            for foreign_key, foreign in saved.items():
                restored = progress.FishtestObserver(key, foreign, fetch=Mock(side_effect=OSError), clock=lambda: 0).observe()
                if foreign_key != key:
                    self.assertIsNone(restored["observation"])
                else:
                    self.assertEqual(restored["observation"]["reported_elo"]["estimate"], estimates[key])
        cache = copy.deepcopy(saved[progress.DONOR_FISHTEST_RUN_ID])
        cache["observation"]["private_path"] = "C:\\private\\fixture"
        restored = progress.FishtestObserver(progress.DONOR_FISHTEST_RUN_ID, cache,
                                             fetch=Mock(side_effect=OSError), clock=lambda: 0).observe()
        self.assertNotIn("private_path", progress.json_bytes(restored).decode())
        cache["configuration"]["username"] = "another-user"
        rejected = progress.FishtestObserver(progress.DONOR_FISHTEST_RUN_ID, cache,
                                             fetch=Mock(side_effect=OSError), clock=lambda: 0).observe()
        self.assertIsNone(rejected["observation"])

    def test_donor_purge_to_zero_clears_prior_estimate(self):
        now = 0
        current = self.donor_fixture(8)
        def fetch(endpoint, run_id):
            return {**copy.deepcopy(current), "elo": {"elo": 2.0, "ci": [-1, 5]}}
        calls = Mock(side_effect=fetch)
        observer = progress.FishtestObserver(progress.DONOR_FISHTEST_RUN_ID, fetch=calls, clock=lambda: now)
        self.assertEqual(observer.observe()["observation"]["reported_elo"]["estimate"], 2.0)
        now = 60
        current = self.donor_fixture(0)
        self.assertEqual(observer.observe()["observation"]["reported_elo"], progress.null_farm_elo("no_games"))
        self.assertEqual(calls.call_count, 3)

    def test_donor_cli_is_explicit_and_reuses_only_its_saved_slot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prior = {"donor_fishtest": {"run_id": progress.DONOR_FISHTEST_RUN_ID}}
            stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
            observer = object()
            with patch.object(progress, "previous_snapshot", return_value=prior), \
                    patch.object(progress, "FishtestObserver", return_value=observer) as constructor, \
                    patch.object(progress, "build_snapshot", return_value={"fixture": True}) as build, \
                    patch.object(progress, "sys", SimpleNamespace(stdout=stdout)), \
                    patch.object(progress, "git") as git:
                code = progress.main(["--publication-repo", str(root), "--stdout", "--donor-fishtest-run-id", progress.DONOR_FISHTEST_RUN_ID])
                self.assertEqual(code, 0)
                constructor.assert_called_once_with(progress.DONOR_FISHTEST_RUN_ID, prior["donor_fishtest"])
                self.assertIs(build.call_args.kwargs["donor_fishtest"], observer)
                self.assertIsNone(build.call_args.kwargs["fishtest"])
                self.assertIsNone(build.call_args.kwargs["source_fishtest"])
                git.assert_not_called()
                self.assertEqual(json.loads(stdout.buffer.getvalue()), {"fixture": True})


if __name__ == "__main__":
    unittest.main()
