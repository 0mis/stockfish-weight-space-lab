from pathlib import Path
import struct
import sys
import tempfile
import unittest

import chess
import chess.pgn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from nnue import BASELINE_SHA256, Network, sha256
from lab import file_hash, paired_summary, summarize_pgn, verify_saved_match

ROOT = Path(__file__).resolve().parent.parent


class NetworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.net = Network.load(ROOT / "nets/original.nnue")

    def test_pinned_official_network(self):
        self.assertEqual(sha256(self.net.data), BASELINE_SHA256)
        self.assertEqual(len(self.net.layers), 8)

    def test_no_op_is_byte_identical(self):
        data, edits = self.net.edit_biases([0] * 8)
        self.assertEqual(data, self.net.data)
        self.assertEqual(edits, [])

    def test_direct_edits_reversible(self):
        data, edits = self.net.edit_biases([0, 0, 32, 64, 96, 128, 128, 128])
        self.assertEqual(len(edits), 6)
        parsed = Network(data)
        restored, _ = parsed.edit_biases([0, 0, -32, -64, -96, -128, -128, -128])
        self.assertEqual(restored, self.net.data)
        self.assertEqual(parsed.layers[7].weights, self.net.layers[7].weights)

    def test_wrong_architecture_and_truncation_rejected(self):
        bad = bytearray(self.net.data)
        struct.pack_into("<I", bad, 4, 0)
        with self.assertRaises(ValueError):
            Network(bytes(bad))
        with self.assertRaises(ValueError):
            Network(self.net.data[:-1])
        with self.assertRaises(ValueError):
            Network(self.net.data + b"\x00")

    def test_bias_overflow_rejected(self):
        with self.assertRaises(ValueError):
            self.net.edit_biases([2**32] * 8)


class StatisticsTests(unittest.TestCase):
    def test_color_pair_statistics(self):
        result = paired_summary([0.25, 0.5, 0.75, 0.5])
        self.assertEqual(result["score_fraction"], 0.5)
        self.assertEqual(result["pentanomial"], [0, 1, 2, 1, 0])
        self.assertEqual(result["relative_logistic_elo"], 0)
        self.assertFalse(result["positive_exploratory_signal"])

    def test_pgn_pairs_require_reversed_colors_and_declared_openings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            opening = root / "opening.epd"
            opening.write_text(" ".join(chess.Board().fen().split()[:4]) + "\n")
            path = root / "games.pgn"

            def write_games(swapped):
                games = []
                for white, black, result in [("candidate", "baseline", "1-0"),
                                             ("baseline" if swapped else "candidate",
                                              "candidate" if swapped else "baseline", "0-1")]:
                    game = chess.pgn.Game()
                    game.headers.update(White=white, Black=black, Result=result, Termination="normal")
                    board, node = game.board(), game
                    moves = ("e4 e5 Qh5 Nc6 Bc4 Nf6 Qxf7#" if result == "1-0"
                             else "f3 e5 g4 Qh4#")
                    for san in moves.split():
                        move = board.parse_san(san)
                        board.push(move)
                        node = node.add_main_variation(move)
                    games.append(str(game))
                path.write_text("\n\n".join(games) + "\n\n")

            write_games(True)
            result = summarize_pgn(path, "candidate", 1, opening)
            self.assertEqual(result["wins"], 2)
            self.assertEqual(result["pentanomial"], [0, 0, 0, 0, 1])
            saved = {"pgn_sha256": file_hash(path), "stats": result}
            verify_saved_match(saved, path, "candidate", 1, opening)
            path.write_text(path.read_text() + "\n")
            with self.assertRaisesRegex(ValueError, "PGN hash"):
                verify_saved_match(saved, path, "candidate", 1, opening)
            write_games(False)
            with self.assertRaisesRegex(ValueError, "colors reversed"):
                summarize_pgn(path, "candidate", 1, opening)
            write_games(True)
            with self.assertRaisesRegex(ValueError, "Incomplete match"):
                summarize_pgn(path, "candidate", 2, opening)
            opening.write_text("8/8/8/8/8/4k3/8/4K3 w - -\n")
            with self.assertRaisesRegex(ValueError, "declared opening"):
                summarize_pgn(path, "candidate", 1, opening)

    def test_result_requires_a_terminal_board(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            opening = root / "opening.epd"
            opening.write_text(" ".join(chess.Board().fen().split()[:4]) + "\n")
            game = chess.pgn.Game()
            game.headers.update(White="candidate", Black="baseline", Result="1-0", Termination="normal")
            path = root / "games.pgn"
            path.write_text(str(game) + "\n\n")
            with self.assertRaisesRegex(ValueError, "final board"):
                summarize_pgn(path, "candidate", 1, opening)


if __name__ == "__main__":
    unittest.main()
