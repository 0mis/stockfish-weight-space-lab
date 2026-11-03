# Stockfish Weight-Space Lab

An independent, substantially AI-assisted experiment in editing a chess evaluator directly, without training or gradients. Built with Codex and reviewed by five helpers configured as GPT-6 Astra at xhigh.

**Initial result: no statistically established Elo gain.** Across 264 games, the separate 128-game confirmation finished **28 wins / 73 draws / 27 losses** (50.39%). The approximate relative Elo estimate is **+2.7**, with a **95% paired-bootstrap interval of -35.4 to +40.9** at this shallow search limit.

[Results](RESULTS.md) · [Five-agent review](AGENT_REVIEW.md) · [Frozen protocol](experiment.json) · [Game evidence](results) · [Research inspiration](https://rikiyat.github.io/blog/weight-space-programming/)

The first trial is deliberately narrow: two reasoned edits to six output-bias parameters. It demonstrates a reproducible direct-editing workflow; it does not demonstrate a stronger Stockfish or a replication of the Qwen repair.

A local experiment prompted by the suggestion to give an LLM Stockfish's NNUE weights and ask it to improve chess strength. The edits are specified directly, without gradient descent, neural-network training, or a fitted optimizer. The engine is the official Stockfish 19 executable on both sides.

The first two candidates change six final-layer bias parameters out of 89,957,768 stored parameters. The final layer sees the position from the side to move, so its bias is an interpretable initiative intercept. The edits add or subtract `[0, 0, 32, 64, 96, 128, 128, 128]` across the eight material buckets. The two sparsest endgame buckets are unchanged. This is a hypothesis about shallow-search calibration, not an identified defect or a claim to understand every learned NNUE feature.

## Run on Windows

Prerequisites: PowerShell and `uv`. Everything else is local to this directory. The setup downloads about 90 MB of pinned upstream archives, verifies their SHA-256 hashes, creates a small Python environment, exports the original net, and writes the candidate nets. It does not install a trainer or use the GPU.

```powershell
.\setup.ps1
.\run.ps1
```

To inspect or validate the weights separately:

```powershell
.\run.ps1 inspect
.\run.ps1 smoke
.\.venv\Scripts\python.exe scripts/audit.py
```

## What is measured

The frozen specification is in `experiment.json`. Before matches begin, a seeded sample from Stockfish's official `8moves_v3` book is separated into disjoint sets: 32 opening pairs for screening, 64 for confirmation, and 4 for a control. Each position is played twice with the colors reversed. Both candidates use the same screening openings. The higher screening score selects the candidate for confirmation; the screen and confirmation scores are never pooled.

Both engines receive a 10,000-node search limit per move, one engine thread, 32 MB hash, unrestricted playing strength, and the same executable. The generous `60+0.6` clocks also remain enabled, so the engine can stop earlier. PGN node annotations can reflect an earlier exact-score update rather than the final search count. Two games run concurrently at below-normal priority. There is no evaluation-based resignation or draw adjudication. A match has a 15-minute safety timeout. This is a short, shallow, node-limited experiment; its results cannot establish an absolute rating or a general improvement at realistic time controls.

The harness records executable, network and opening hashes, exact arguments, PGNs, and console logs. It checks that every game belongs to its declared opening set, every result is supported by the final board, and every opening has a pair with reversed colors. Approximate confidence intervals resample complete opening pairs. A small favorable score remains inconclusive if its interval includes equality.

Completed matches are reused only after checking their settings and recomputing their results from the PGN. Partial matches are preserved and cause a stop; they are not silently replaced. To design a new experiment, use a fresh directory so that the original evidence stays intact.

## Files

- `scripts/nnue.py`: format checks, output-layer inspection, reversible byte-preserving edits.
- `scripts/lab.py`: opening split, native-engine round trips, matched games, paired statistics, result report.
- `nets/*.json`: full parameter changes, parent hash, and resulting network hashes.
- `results/smoke/`: native engine round-trip and static evaluation checks; fresh execution also writes local logs.
- `results/*/`: published PGNs and summaries. Machine-specific commands and raw session logs are omitted.
- `results/experiment-summary.json` and `RESULTS.md`: final initial-experiment results, when the run finishes.
- `results/audit.json`: a fresh verification of the completed games, hashes, paired statistics, and candidate selection.
- `AGENT_REVIEW.md`: findings from the five requested Astra/xhigh helper reviews.

## Sources and licenses

- [Official Stockfish 19 release](https://github.com/official-stockfish/Stockfish/releases/tag/sf_19), including its matching source and GPLv3 license, preserved under `vendor/stockfish/stockfish`.
- [Stockfish network documentation](https://github.com/official-stockfish/networks/blob/master/README.md): embedded weights can be exported with `export_net`; upstream network files are CC0.
- [Fastchess v1.8.2-alpha](https://github.com/Disservin/fastchess/releases/tag/v1.8.2-alpha), MIT license, preserved in its vendor directory.
- [Official opening book at the pinned commit](https://github.com/official-stockfish/books/tree/a804a97e709f40aa75a00f9d19e84915b7a3a45c), CC0.
- [Weight-Space Programming research source](https://raw.githubusercontent.com/RikiyaT/RikiyaT.github.io/master/blog/weight-space-programming/index.html), particularly Experiment 8. The authors allowed inference feedback and direct edits while forbidding training and gradients. This project adapts that idea to NNUE; it does not reproduce the Qwen results.

Stockfish's GPLv3 terms apply if distributing its executable or modifications. Its matching source and license are included in the downloaded release. The local Python dependency `chess` is also GPLv3-or-later.

## Public evidence and reproduction

The four published PGNs contain all 264 games. Per-game wall-clock headers are removed, and text uses LF line endings. Moves, evaluation comments, results and paired statistics are retained. `results/publication-manifest.json` records both original and published PGN hashes. Raw local logs and absolute machine paths are omitted. Run `setup.ps1`, then the audit command above, to rebuild dependencies and independently recheck the published evidence.

This repository is licensed under GPL-3.0-or-later; see [LICENSE](LICENSE). Upstream Stockfish and Python chess dependencies retain their licenses. Official network and opening-book data are CC0. No pretrained binaries or weight blobs are checked into Git. Setup retrieves the pinned official releases and recreates the candidate files from exact parameter edits.
