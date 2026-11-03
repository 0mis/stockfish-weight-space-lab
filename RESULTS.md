# Initial direct NNUE weight-editing experiment

No statistically convincing improvement demonstrated by this initial direct-edit experiment.

Stockfish 19, same executable and settings on both sides; only the NNUE file differs. No gradients or training.

Both engines received a 10,000-node search limit per move with generous clocks. The engine can stop earlier; PGN node annotations can also reflect an earlier exact-score update.

| Stage | Candidate | W / D / L | Score | Approximate relative Elo (95% pair bootstrap) |
| --- | --- | --- | --- | --- |
| control | control | 3 / 2 / 3 | 50.0% | symmetry check; no rating estimate |
| screen | initiative-plus | 8 / 47 / 9 | 49.2% | -5.4 [-54.7, +43.7] |
| screen | initiative-minus | 8 / 45 / 11 | 47.7% | -16.3 [-65.9, +32.7] |
| confirmation | initiative-plus | 28 / 73 / 27 | 50.4% | +2.7 [-35.4, +40.9] |

Screening selects a candidate; it is not evidence of a gain. The confirmation uses different openings, each played twice with colors reversed. Confidence intervals resample entire opening pairs. The identical-network control checks symmetry; its degenerate bootstrap interval is not a precision or equivalence claim.

Each candidate changes six int32 final-layer bias parameters, tapered by material. Full byte-level edits and SHA-256 hashes are in `nets/*.json`. Stockfish loaded and re-exported all three networks byte for byte, and the static evaluation moved in the intended directions.

## Limits

- Only two manually chosen output-bias edits were tested, not all possible direct edits.
- The 10,000-node search limit is shallow; no absolute or general Elo claim is supported.
- Confirmation uses disjoint positions but the same opening-book source.
- The confidence interval is approximate and the sample is small.
- This is an adaptation to NNUE, not a reproduction of the Qwen experiment.

Eight focused tests passed. The full audit verifies all 264 results against their final boards, saved hashes, declared openings, reversed-color pairs, and recomputed statistics. Five additional agents, each configured as `gpt-6-astra` with `xhigh` reasoning, reviewed the experiment. Their findings are in [AGENT_REVIEW.md](AGENT_REVIEW.md).
