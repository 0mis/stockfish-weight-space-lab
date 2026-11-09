# Stockfish Weight-Space Lab

An AI-assisted research log of direct NNUE edits and Stockfish experiments. Current helper agents use GPT-6 Astra with max reasoning.

<!-- live-status:start -->
## Live confirmation progress

Trial `trial-0003` · **provisional, independently unverified** · `60+0.6 / T1 / H64`

| Reference | W / D / L | Points | Games (pairs) | Logistic Elo estimate | Anytime lower Elo bound | Statistical decision | Minimum pairs |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `spcc-261025` | 82 / 140 / 80 | 152–150 | 302 (151) | +2.30 | -36.31 | `continue` | 151/128 (reached) |
| `dev-261106` | 0 / 0 / 0 | 0–0 | 0 (0) | pending | −∞ | `continue` | 0/128 (pending) |

The paired, one-sided anytime lower bounds use **99.958333%** coverage per reference (trial allocation: **99.916667%**; whole research family: **99%**). These are fixed protocol coverage levels under its assumptions, not probabilities that the candidate is stronger.

Each reference needs at least **128 pairs** and log-evidence ≥ **7.78322**. Both gates must pass; an independent terminal integrity audit is still required. Point estimates can rise or fall. Every completed pair in this trial's ledger prefix is retained; interrupted earlier trials are excluded. `continue` is a statistical decision and does not indicate whether the sampler is running.

Trial ledger state: **open**. Both statistical gates passed: **no**. Verified gain: **not established by this progress feed**.

Ledger checkpoint: event `324`, SHA-256 `f1d03e0b1f88ab1f6292e9a36f156bbc53af13940a25141a1a1cb1df929422bd`. [Aggregate JSON](results/live-status.json).

### Public Fishtest NNUE-only test

[Official run `6af10a258e7fb2e78bc1ca5c`](https://tests.stockfishchess.org/tests/view/6af10a258e7fb2e78bc1ca5c) · `10+0.1 / T1 / H16` · API **current**

This is a separate NNUE-only experiment. Its executable, clocks, normalized SPRT and results remain separate from local trial-0003's paired e-process.

Official state: **approved_open**; approved: **yes**; finished: **no**. A stale API label means these are the last validated official aggregates.

| W / D / L | Points | Games (pairs) | Fishtest logistic Elo | Fishtest nominal 95% CI | Elo availability | SPRT state | LLR |
| ---: | ---: | ---: | ---: | --- | --- | --- | ---: |
| 3074 / 6046 / 3136 | 6097–6159 | 12256 (6128) | -1.76 | [-4.78, +1.26] | `current` | `undecided` | -0.930090 |

Fishtest's normalized SPRT uses **[0, 2]**, **α = β = 0.05**, and LLR bounds **[−2.944439, +2.944439]**. Fishtest's nominal 95% CI is an SPRT/Brownian approximation, distinct from the local anytime lower bound. Official purges can lower the reported counts; this feed follows those counts. A finished run without an SPRT decision remains stopped/inconclusive. No farm decision automatically establishes an overall verified gain.

Candidate network: `nn-fcbaf7d2197c.nnue`; reference: `nn-d1ee674a62ca.nnue`. Source revisions: `9579e56ec2926265abe40ca20ba069d6463a66b6` / `7cdd5e89a39fe3071b67d91c7bb07d712044bf76`.
<!-- live-status:end -->

The current real-clock comparison uses one thread, 64 MiB hash and `60+0.6` for both engines. Its references are Stockfish 261025, the leader on the [SPCC VLTC list](https://www.sp-cc.de/), and the official November 6 development build `7cdd5e89`. The second comparison starts after a positive statistical decision against the first reference. An independent integrity audit is also required before claiming a verified gain.

The D1 candidate scales FC2 weights and biases by 1.02 with exact integer rounding and adds 128 to each final bias. Its source includes [mstembera's transposition-table optimization](https://github.com/official-stockfish/Stockfish/pull/7281). The complete engine is being compared, so a positive result would cover that combination. A comparison using the same executable on both sides is needed to isolate the effect of the NNUE edit.

A second candidate changes 408 weights and 18 biases in Shawn Xu's `test1757` network. Its Huber100 loss against archived search scores fell 0.5985% on 101 preselected retired training positions. The [prepared source](https://github.com/0mis/Stockfish/tree/7a17b53bcaf93f54a23ad65f309c413585500c82) now passes a [Windows native check](https://github.com/0mis/Stockfish/actions/runs/42543250921): all 44 predicted integer evaluations and 44 complete bucket tables match the independent scalar expectations, with two repeatable benchmark signatures per network and start-position perft4 of 197281 for both. Playing strength remains unverified. [Training diagnostic](results/donor-edit-check.json) · [Native conformance and raw diagnostic captures](results/native-donor-conformance.json)

The edited `test1757` candidate completed its fixed 64-pair development screen against the pinned November 6 reference at `10+0.1 / T1 / H64`: **32 wins, 60 draws, 36 losses (62–66)**. Its descriptive logistic Elo estimate is **−10.9**, with an approximate paired-bootstrap interval of **−46.4 to +21.7** on this reused development distribution. This establishes no gain. The separate frozen confirmation resumed from its existing checkpoint after both development screens finished. [Complete result and UTC game evidence](results/test1757-edited-screen-result.json) · [Screen plan](results/test1757-screen-plan.json).

The matched `test1757` follow-up is complete: both networks used the same executable, pinned November 6 opponent and 64-pair schedule at `10+0.1 / T1 / H64`, with 128 games each. Unmodified `18cd` scored **31 wins, 65 draws, 32 losses (63.5–64.5)**; edited `034f` scored **32 wins, 60 draws, 36 losses (62–66)**. The predeclared complete-screen rule selects unmodified `18cd` for further evaluation by **1.5 points**. The parent arm's authenticated Black clock loss at pair index 45 (10 ms overrun) is retained. These exploratory results establish neither an Elo gain nor harm from the manual edit. The frozen confirmation has resumed from its unchanged 134-pair checkpoint. [Complete parent result and UTC game evidence](results/test1757-parent-screen-result.json) · [Matched selection](results/test1757-matched-network-selection.json) · [Comparison plan](results/test1757-network-comparison-plan.json).

A Windows x86-64 BMI2 benchmark compared the prefetch build (A) with an alternative accumulator (B) using the original `test1757` network `18cd`. B took less time in **3 of 8** blocks. Its median block speedup (`A/B − 1`) was **−4.25%**. The selection rule required **at least +1%** and **at least 7 of 8** blocks favoring B, so the lab retained the prefetch build with `18cd`. Each run searched 3,464,885 nodes. This benchmark measured execution time only. [Ordered times, block sums and source builds](results/test1757-accumulator-timing.json).

The public NNUE-only [Fishtest STC test](https://tests.stockfishchess.org/tests/view/6af10a258e7fb2e78bc1ca5c) has been submitted against pinned official November 6 source. It uses `10+0.1`, one thread, 16 MiB hash and the standard normalized SPRT bounds `[0, 2]`. The [source branch](https://github.com/0mis/Stockfish/tree/nnue-fcbaf7d2197c) changes the default network filename. The [CC0 network release](https://github.com/0mis/Stockfish/releases/tag/experimental-nn-fcbaf7d2197c) includes submission metadata. Its patched binary reproduced benchmark signature **2261721** twice and passed start-position perft4 (**197281**). The Fishtest page reports queue approval and live results.

The sections below document the original shallow experiment and preserve its reproducible evidence.

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
