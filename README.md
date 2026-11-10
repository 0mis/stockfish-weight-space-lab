# Stockfish Weight-Space Lab

This lab edits NNUE parameters and measures their effects in paired Stockfish games. GPT-6 Astra and GPT-6.1 Sol contributed to different phases of the research.

**Experimental Windows builds** · [Test1757 with nine edited biases](https://github.com/0mis/Stockfish/releases/tag/experimental-test1757-history-d5c257728ba5) · [Test1758 with its original weights](https://github.com/0mis/stockfish-weight-space-lab/releases/tag/experimental-test1758-history-68752b755c93)

Extract the ZIP and set your GUI’s `EvalFile` to the full path of its included network. Choose `nn-d5c257728ba5.nnue` for the test1757 build in local confirmation, or `nn-68752b755c93.nnue` for the test1758 development build.

<!-- live-status:start -->
## Live confirmation progress

Trial `trial-0004` · **provisional, independently unverified** · `60+0.6 / T1 / H64`

| Reference | W / D / L | Points | Games (pairs) | Logistic Elo estimate | Anytime lower Elo bound | Statistical decision | Minimum pairs |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `dev-261106` | 0 / 0 / 0 | 0–0 | 0 (0) | pending | −∞ | `continue` | 0/128 (pending) |
| `spcc-261025` | 90 / 179 / 83 | 179.5–172.5 | 352 (176) | +6.91 | -32.46 | `continue` | 176/128 (reached) |

The paired, one-sided anytime lower bounds use **99.975000%** coverage per reference (trial allocation: **99.950000%**; whole research family: **99%**). These are fixed protocol coverage levels under its assumptions, not probabilities that the candidate is stronger.

Each reference needs at least **128 pairs** and log-evidence ≥ **8.29405**. Both gates must pass; an independent terminal integrity audit is still required. Point estimates can rise or fall. Every completed pair in this trial's ledger prefix is retained; interrupted earlier trials are excluded. `continue` is a statistical decision and does not indicate whether the sampler is running.

Trial ledger state: **open**. Both statistical gates passed: **no**. Verified gain: **not established by this progress feed**.

Ledger checkpoint: event `554`, SHA-256 `945dc009c0454cc24610ab09dbfaea7f597068e55b67351612b82ab7766dac82`. [Aggregate JSON](results/live-status.json).

### Public Fishtest NNUE-only test

[Official run `6af10a258e7fb2e78bc1ca5c`](https://tests.stockfishchess.org/tests/view/6af10a258e7fb2e78bc1ca5c) · `10+0.1 / T1 / H16` · API **current**

This is a separate NNUE-only experiment. Its executable, clocks, normalized SPRT and results remain separate from local trial-0003's paired e-process.

Official state: **sprt_rejected**; approved: **yes**; finished: **yes**. A stale API label means these are the last validated official aggregates.

| W / D / L | Points | Games (pairs) | Fishtest logistic Elo | Fishtest nominal 95% CI | Elo availability | SPRT state | LLR |
| ---: | ---: | ---: | ---: | --- | --- | --- | ---: |
| 18085 / 35101 / 18238 | 35635.5–35788.5 | 71424 (35712) | -0.58 | [-1.87, +0.74] | `current` | `rejected` | -2.970476 |

Fishtest's normalized SPRT uses **[0, 2]**, **α = β = 0.05**, and LLR bounds **[−2.944439, +2.944439]**. Fishtest's nominal 95% CI is an SPRT/Brownian approximation, distinct from the local anytime lower bound. Official purges can lower the reported counts; this feed follows those counts. A finished run without an SPRT decision remains stopped/inconclusive. No farm decision automatically establishes an overall verified gain.

Candidate network: `nn-fcbaf7d2197c.nnue`; reference: `nn-d1ee674a62ca.nnue`. Source revisions: `9579e56ec2926265abe40ca20ba069d6463a66b6` / `7cdd5e89a39fe3071b67d91c7bb07d712044bf76`.

### Public Fishtest test1757 source and network test

[Official run `6af16e648e7fb2e78bc1cb09`](https://tests.stockfishchess.org/tests/view/6af16e648e7fb2e78bc1cb09) · `10+0.1 / T1 / H16` · API **current**

The test1757 prefetch source and original 18cd network face official Stockfish with the D1 network. The Elo estimate below applies only to this run.

The submitted source `de342a301195b34b7da76374fe3fadf29352de8d` shares tree `8e3164caf60d281cb4b1d00a699364e04b354451` with the tested commit `7a17b53bcaf93f54a23ad65f309c413585500c82`. It uses `nn-18cd32e11a9c.nnue` (bench `3464885`). The base is `7cdd5e89a39fe3071b67d91c7bb07d712044bf76` with `nn-d1ee674a62ca.nnue` (bench `1556650`).

This run finished with zero games. No Elo estimate, confidence interval, or SPRT decision is available.

Official state: **stopped_without_sprt_decision**; approved: **no**; finished: **yes**. A stale API label means these are the last validated official aggregates.

| W / D / L | Points | Games (pairs) | Fishtest logistic Elo | Fishtest nominal 95% CI | Elo availability | SPRT state | LLR |
| ---: | ---: | ---: | ---: | --- | --- | --- | ---: |
| 0 / 0 / 0 | 0–0 | 0 (0) | unavailable | unavailable | `no_games` | `undecided` | 0.000000 |

Fishtest's normalized SPRT uses **[0, 2]**, **α = β = 0.05**, and LLR bounds **[−2.944439, +2.944439]**. Fishtest's nominal 95% CI is an SPRT/Brownian approximation, distinct from the local anytime lower bound. Official purges can lower the reported counts; this feed follows those counts. A finished run without an SPRT decision remains stopped/inconclusive. No farm decision automatically establishes an overall verified gain.

### Public Fishtest NNUE edit vs donor parent

[Fishtest run `6af19afb8e7fb2e78bc1cb30`](https://tests.stockfishchess.org/tests/view/6af19afb8e7fb2e78bc1cb30) · `10+0.1 / T1 / H16` · API **current**

The nine-bias d5 NNUE edit faces its test1757 donor parent with the original 18cd network. Both sides use the same prefetch source except the default network filename. This estimates only the NNUE edit relative to its donor parent; it is not an official-Stockfish comparison. Its results remain separate from both earlier farm runs and local trial-0003.

Candidate `d7155994d192b4e723866360ae9285b42e122790` uses `nn-d5c257728ba5.nnue` (bench `2376690`). Donor parent `de342a301195b34b7da76374fe3fadf29352de8d` uses `nn-18cd32e11a9c.nnue` (bench `3464885`).

This run finished with zero games. No Elo estimate, confidence interval, or SPRT decision is available.

Official state: **stopped_without_sprt_decision**; approved: **no**; finished: **yes**. A stale API label means these are the last validated official aggregates.

| W / D / L | Points | Games (pairs) | Fishtest logistic Elo | Fishtest nominal 95% CI | Elo availability | SPRT state | LLR |
| ---: | ---: | ---: | ---: | --- | --- | --- | ---: |
| 0 / 0 / 0 | 0–0 | 0 (0) | unavailable | unavailable | `no_games` | `undecided` | 0.000000 |

Fishtest's normalized SPRT uses **[0, 2]**, **α = β = 0.05**, and LLR bounds **[−2.944439, +2.944439]**. Fishtest's nominal 95% CI is an SPRT/Brownian approximation, distinct from the local anytime lower bound. Official purges can lower the reported counts; this feed follows those counts. A finished run without an SPRT decision remains stopped/inconclusive. No farm decision automatically establishes an overall verified gain.

### Public Fishtest current-master NNUE-only test

[Official run `6af2455c8e7fb2e78bc1cc30`](https://tests.stockfishchess.org/tests/view/6af2455c8e7fb2e78bc1cc30) · `10+0.1 / T1 / H16` · API **current**

The d5 NNUE edit faces the original 18cd network on the SFNNv20 official-master snapshot at submission. This comparison is separate from local trial-0004, the historical D1 run, the earlier source/network run, and the donor-parent run. Its Elo and SPRT apply only to this comparison. Candidate bench: `2376690`; reference bench: `3464885`. Candidate `64b0b7a2a78e44f1eade4bb441f8819abbfac6d2` uses `nn-d5c257728ba5.nnue`; reference `43e01e07210948e1130dc687c065d7a3742b2793` uses `nn-18cd32e11a9c.nnue`.

Official state: **approved_open**; approved: **yes**; finished: **no**. A stale API label means these are the last validated official aggregates.

| W / D / L | Points | Games (pairs) | Fishtest logistic Elo | Fishtest nominal 95% CI | Elo availability | SPRT state | LLR |
| ---: | ---: | ---: | ---: | --- | --- | --- | ---: |
| 6263 / 12207 / 6202 | 12366.5–12305.5 | 24672 (12336) | +0.86 | [-1.26, +2.98] | `current` | `undecided` | 0.309127 |

Fishtest's normalized SPRT uses **[0, 2]**, **α = β = 0.05**, and LLR bounds **[−2.944439, +2.944439]**. Fishtest's nominal 95% CI is an SPRT/Brownian approximation, distinct from the local anytime lower bound. Official purges can lower the reported counts; this feed follows those counts. A finished run without an SPRT decision remains stopped/inconclusive. No farm decision automatically establishes an overall verified gain.

Candidate network: `nn-d5c257728ba5.nnue`; reference: `nn-18cd32e11a9c.nnue`. Source revisions: `64b0b7a2a78e44f1eade4bb441f8819abbfac6d2` / `43e01e07210948e1130dc687c065d7a3742b2793`.
<!-- live-status:end -->

Local trial 4 tests the experimental test1757 build, which combines nine output-bias edits to Shawn Xu’s test1757 network with accumulator prefetch and a search-history change. Both engines use one thread, 64 MiB of hash and 60 seconds per side plus 0.6 seconds per move. The first opponent is Stockfish 261025, the SPCC VLTC leader. If that comparison crosses its positive boundary, the second opponent is the official November 6 development revision `7cdd5e89` fixed before play. A verified gain requires both comparisons and an independent game and provenance audit. [Tested source and author credits](https://github.com/0mis/Stockfish/tree/cecfcfd5480afd16b31740b24387f5779d24c0db) · [SPCC ratings](https://www.sp-cc.de/) · [Official reference](https://github.com/official-stockfish/Stockfish/commit/7cdd5e89a39fe3071b67d91c7bb07d712044bf76)

On November 9, official Stockfish adopted SFNNv20 and Shawn Xu’s `nn-18cd32e11a9c.nnue`. Fishtest run `6af2455c8e7fb2e78bc1cc30` isolates the nine output-bias edits on official revision `43e01e07`. The patch changes one line selecting `nn-d5c257728ba5.nnue`. It uses the same search, `10+0.1` clock, one thread and 16 MiB hash on both sides. [Live Fishtest run](https://tests.stockfishchess.org/tests/view/6af2455c8e7fb2e78bc1cc30) · [Verified setup](results/nov9-nine-bias-fishtest.json) · [Upstream change](https://github.com/official-stockfish/Stockfish/commit/26647279081cdc39d72ef9f10c33289a7da4a5e9) · [Moderator’s guidance](https://github.com/official-stockfish/Stockfish/discussions/7298#discussioncomment-19501738)

To try the network-only configuration, set `EvalFile` to `nn-d5c257728ba5.nnue` in the official November 9 engine. [Official release](https://github.com/official-stockfish/Stockfish/releases/tag/stockfish-dev-20261109-43e01e07) · [Edited network](https://github.com/0mis/Stockfish/releases/download/experimental-nn-d5c257728ba5/nn-d5c257728ba5.nnue)

GitHub cancelled both shards of the planned 572-game whole-build comparison with November 9 Stockfish during play. Neither shard uploaded its referee records. The completed-game count and score are unknown. [Interrupted match](https://github.com/0mis/Stockfish/actions/runs/42714347653) · [Frozen schedule](https://github.com/0mis/Stockfish/blob/ea629f55bfdeb682f5e533faf877f81bf87c0406/PLAN.json)

The previous local trial used a D1 edit that scaled FC2 weights and biases by 1.02, rounded to integers and added 128 to each output bias. That engine also included mstembera’s transposition-table change. The trial paused after scoring 203.5–204.5 in 408 games against Stockfish 261025. [Trial 3 results](https://github.com/0mis/stockfish-weight-space-lab/blob/dddfe08064771a995a1fc7cf009fedd4b0530e26/results/live-status.json) · [Transposition-table change](https://github.com/official-stockfish/Stockfish/pull/7281)

An earlier candidate changed 408 weights and 18 biases in Shawn Xu's `test1757` network. Its Huber100 loss against archived search scores fell 0.5985% on 101 preselected retired training positions. The [prepared source](https://github.com/0mis/Stockfish/tree/7a17b53bcaf93f54a23ad65f309c413585500c82) now passes a [Windows native check](https://github.com/0mis/Stockfish/actions/runs/42543250921): all 44 predicted integer evaluations and 44 complete bucket tables match the independent scalar expectations, with two repeatable benchmark signatures per network and start-position perft4 of 197281 for both. Playing strength remains unverified. [Training diagnostic](results/donor-edit-check.json) · [Native conformance and raw diagnostic captures](results/native-donor-conformance.json)

The edited `test1757` candidate completed its fixed 64-pair development screen against the pinned November 6 reference at `10+0.1 / T1 / H64`: **32 wins, 60 draws, 36 losses (62–66)**. Its descriptive logistic Elo estimate is **−10.9**, with an approximate paired-bootstrap interval of **−46.4 to +21.7** on this reused development distribution. This establishes no gain. The separate frozen confirmation resumed from its existing checkpoint after both development screens finished. [Complete result and UTC game evidence](results/test1757-edited-screen-result.json) · [Screen plan](results/test1757-screen-plan.json).

The matched `test1757` follow-up is complete: both networks used the same executable, pinned November 6 opponent and 64-pair schedule at `10+0.1 / T1 / H64`, with 128 games each. Unmodified `18cd` scored **31 wins, 65 draws, 32 losses (63.5–64.5)**; edited `034f` scored **32 wins, 60 draws, 36 losses (62–66)**. The predeclared complete-screen rule selects unmodified `18cd` for further evaluation by **1.5 points**. The parent arm's authenticated Black clock loss at pair index 45 (10 ms overrun) is retained. These exploratory results establish neither an Elo gain nor harm from the manual edit. The frozen confirmation has resumed from its unchanged 134-pair checkpoint. [Complete parent result and UTC game evidence](results/test1757-parent-screen-result.json) · [Matched selection](results/test1757-matched-network-selection.json) · [Comparison plan](results/test1757-network-comparison-plan.json).

A Windows x86-64 BMI2 benchmark compared the prefetch build (A) with an alternative accumulator (B) using the original `test1757` network `18cd`. B took less time in **3 of 8** blocks. Its median block speedup (`A/B − 1`) was **−4.25%**. The selection rule required **at least +1%** and **at least 7 of 8** blocks favoring B, so the lab retained the prefetch build with `18cd`. Each run searched 3,464,885 nodes. This benchmark measured execution time only. [Ordered times, block sums and source builds](results/test1757-accumulator-timing.json).

A channel-order experiment fitted a permutation on 1,536 positions from 48 opening families in the two published `test1757` PGNs. On 480 positions from 15 held-out families, the reordered channels reduced the active four-channel groups from **74,186 to 74,153**, a saving of **33 groups (0.04448%)**. Eight families improved, meeting the family threshold. The total reduction fell below the required **1%**. The experiment ended before generating a network, measuring speed or playing strength games. [Counts, selection rule and experiment sources](results/test1757-channel-layout.json).

Two diagnostics asked whether the output bias of test1757 head 82 should move by +512 or −512 integer units, using head 87 as a control. On the same 453 positions, node-limited searches yielded **13 stable labels and 3 paired opening families**. Searches at depths 9 and 13 yielded **141 stable labels and 24 paired families**, with 43 target and 55 control observations in those families. The median target-minus-control contrast was **−14.5 centipawns** and the median target residual was **+21.5 centipawns**. Only 13 of 24 families agreed with the contrast direction. Both studies stopped during fitting, before evaluating held-out positions, editing weights or playing strength games. [Selection rule, counts and source runs](results/test1757-head-calibration-diagnostics.json).

Stefan Geschwentner's history-bonus change scored **68–60** against the prefetch parent across 128 games (38 wins, 60 draws, 30 losses). Both builds used the original `18cd` network. This corresponds to **+21.7 Elo against the lab parent**, with a descriptive paired-bootstrap 95% interval of **−10.9 to +54.7 Elo**. The result selects the search change for a direct comparison with official Stockfish. [Result and all 128 games](results/test1757-history-floor-screen-result.json)

The nine-bias NNUE edit scored **66–62** against the original network in 128 games (34 wins, 64 draws, 30 losses). Both sides used the same executable and exchanged colors on every opening. The estimate is **+10.9 logistic Elo against the parent**, with a descriptive 95% paired-bootstrap interval of **−16.3 to +38.2 Elo**. One clock forfeit counted in the result. The edit advances to the direct comparison with official Stockfish. [Full result and games](results/test1757-readout-ridge-screen-result.json) / [Reproduce the network](results/test1757-readout-ridge/README.md) / [Play](results/test1757-readout-ridge/PLAY.md)

On Shawn Xu’s newer test1758 network, the same nine bias edits scored **127.5–128.5** against the unedited network in 256 games (67 wins, 121 draws, 68 losses). Both sides used the same history-bonus executable at `10+0.1 / T1 / H64`. The estimate was **−1.36 Elo**, with a descriptive paired 95% interval of **−21.74 to +19.02**. The frozen rule selected the unedited test1758 network for the separate comparison against the November 6 official revision `7cdd5e89`. [All games and audit](https://github.com/0mis/Stockfish/blob/f6b8d4898be1515be76db88e28987184dd49c7f2/results/test1758-fixed-bias-dev-001/README.md) · [Follow-up plan](https://github.com/0mis/Stockfish/blob/4f0672262b2edd3d9b4c7ce17ac466893b398389/public-dev/plan.json) · [Follow-up match](https://github.com/0mis/Stockfish/actions/runs/42702655777)

The selected test1758 configuration scored **134.5–121.5** against official November 6 Stockfish (`7cdd5e89`) in a separate 256-game development match. It recorded 51 wins, 167 draws and 38 losses. The estimate was **+17.66 Elo**, with a nominal paired-bootstrap 95% interval of **+1.36 to +34.04** on these retired development openings. Each opening was played with both colors at `10+0.1 / T1 / H64`. This configuration uses Shawn Xu’s unedited test1758 weights and the history-floor executable. [Exact build and all games](https://github.com/0mis/stockfish-weight-space-lab/releases/tag/experimental-test1758-history-68752b755c93) · [Match figures](results/test1758-history-nov6.json) · [Independent readback](https://github.com/0mis/Stockfish/actions/runs/42702655777)

The history-bonus build with the nine-bias NNUE finished **131–125** against official Stockfish `7cdd5e89` in 256 games (71 wins, 120 draws, 65 losses). The descriptive estimate is +8.1 logistic Elo, with a nominal paired-bootstrap 95% interval of -14.9 to +31.3. That result nominated the build now playing in trial 4. [All games and complete result](results/test1757-selected-vs-official-result.json) / [Registered match plan](results/test1757-selected-vs-official-plan.json)

In 192 public positions, the two best moves at depths 9 and 13 met the study's clear-ranking rule six times. In four of those positions, the static evaluation favored the runner-up by at least 12 centipawns. The original test1757 engine played one of the four in the archived games. It chose Re1 at depth 16, while the separate depth-13 search favored Qxc4. The stronger move in that position remains an open question. [Move choices, scores and original games](results/test1757-sibling-diagnostic.json)

Fishtest closed the nine-bias comparison against its donor before any games were played. Its public action log records "User stop." The run produced no Elo estimate. [Fishtest record](https://tests.stockfishchess.org/tests/view/6af19afb8e7fb2e78bc1cb30) / [Closure details](results/test1757-readout-ridge-fishtest-closure.json) / [Download the experimental network](https://github.com/0mis/Stockfish/releases/tag/experimental-nn-d5c257728ba5)

A separate experiment changed two signed FC2 coefficients in the original test1757 network. Its training loss fell by 4.85 centipawns squared. On 62 measurable held-out move pairs, the loss rose slightly, from 356.3554 to 356.3674. The edit changed 33 move-score margins, increasing 10 and decreasing 23. It passed native checks and qualifies for a separate game test. [Two-byte recipe and data](results/test1757-lichess-fc2-freeze.json) / [Held-out measurements](results/test1757-lichess-fc2-heldout.json)

The two-weight edit to the original November 6 Stockfish network scored **60–68** in 128 games against unmodified Stockfish. Both sides used the identical executable. The edit recorded 25 wins, 70 draws and 33 losses. The descriptive estimate is -21.7 logistic Elo with a nominal paired 95% interval of -49.2 to +8.1. [Full result and games](results/official-d1-two-weight-match.json) / [Exact weight edits](results/official-d1-two-coefficient-freeze.json) / [Held-out measurements](results/official-d1-sibling-heldout.json)

A later calibration study collected 1,885 stable training comparisons from 6,658 positions across 167 opening families. Its plan required 2,000 comparisons. Training ended before fitting an edit or opening the validation labels. [Verified study result](https://github.com/0mis/Stockfish/blob/75e3cff37a39880912ee021d5a784503dfc0a574/research/official_d1_test1758/NO-FIT-RESULT.json)

The public NNUE-only [Fishtest STC test](https://tests.stockfishchess.org/tests/view/6af10a258e7fb2e78bc1ca5c) has been submitted against pinned official November 6 source. It uses `10+0.1`, one thread, 16 MiB hash and the standard normalized SPRT bounds `[0, 2]`. The [source branch](https://github.com/0mis/Stockfish/tree/nnue-fcbaf7d2197c) changes the default network filename. The [CC0 network release](https://github.com/0mis/Stockfish/releases/tag/experimental-nn-fcbaf7d2197c) includes submission metadata. Its patched binary reproduced benchmark signature **2261721** twice and passed start-position perft4 (**197281**). The Fishtest page reports queue approval and live results.

The Fishtest submission for the original `18cd` network with prefetch was stopped before approval after **zero games**. The public action log records a priority change and a stop. The submitted commit shares the locally tested source tree and records benchmark signature **3464885**. [Run record and settings](results/test1757-source-fishtest.json) · [Fishtest action log](https://tests.stockfishchess.org/actions?run_id=6af16e648e7fb2e78bc1cb09).

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
