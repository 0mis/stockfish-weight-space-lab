# Five-agent review of the initial NNUE experiment

At the user's request, five helpers were spawned with explicit `model: gpt-6-astra`, `reasoning_effort: xhigh`, and `fork_turns: none`. Each received a bounded task and the required project context. No nested helpers were used. All five completed their reviews.

The shared conclusion is **no demonstrated strength improvement and no diagnosed weight defect that supports another correction**. The original Stockfish network remains the recommended incumbent. The edited networks and full game evidence are retained for inspection.

| Review | What was checked | Finding |
| --- | --- | --- |
| NNUE weight analysis | All eight stacks' hidden/output weights, quantized ranges, activation bounds, serialized offsets | Existing edits are correctly located. No provably dead/saturated second-layer neuron or supported hidden-weight repair was found. Extreme quantized values alone are not defects. |
| Chess failure analysis | Four selected loss positions, original and edited networks each receiving a 100,000-node request per position | At the larger search limit both networks chose the same move in all four examples. The examples suggest shallow-search sensitivity, not an isolated NNUE defect. They were selected from losses and do not establish a population-wide explanation. |
| Semantic feature analysis | Decoded HalfKA, threat, and pawn-pair PSQT sections and their use in evaluation | Odd isolated piece averages do not identify wrong chess values: the jointly trained branches compensate for one another and affect complexity damping. A small king-context contraction could be tested as a new hypothesis, but the weights do not justify treating it as a repair. No such candidate was produced or tested. |
| Statistical audit | Every PGN, final board, hash, paired score, pentanomial, bootstrap interval, and selection rule | All 264 recorded games and statistics agree. The confirmation is 28 wins, 73 draws, 27 losses: 50.39%, approximately +2.7 relative logistic Elo with a paired-bootstrap 95% interval of -35.4 to +40.9. This establishes neither a gain nor equivalence. |
| Research and harness audit | Authors' research, source serialization, archive members, actual network paths and UCI commands | No defect invalidates the current run. The experiment is legitimate direct parameter editing, but six generic intercept edits are much narrower than a mechanistically diagnosed circuit repair. Both installed executables match their downloaded archive members. |

## Concrete validation improvements

The root agent applied the review findings without changing networks, openings, match settings, selection, or recorded outcomes:

- `summarize_pgn` now verifies every result against the final board under chess rules. The existing 264 games already pass this check independently. Test fixtures now use legal completed games, and a fabricated nonterminal result is explicitly rejected.
- Match execution now reads concurrency, thread count, and hash size from the frozen protocol rather than duplicating those values in code. The values used in this run are unchanged.
- Documentation describes a **10,000-node search limit** with generous clocks. The statistical reviewer inspected 36,690 logged searches: 322 stopped below the limit, consisting of 300 mate searches and 22 depth-245 draw searches. No apparent clock-driven undersearch was identified. PGN node annotations can contain an earlier exact-score update.
- The identical-network control is labeled a symmetry check. Its four identical pair scores produce a degenerate bootstrap interval; this is not a precise strength estimate.
- The NNUE editor's documentation states its boundary: it checks architecture, section boundaries, and compressed-size envelopes but does not fully validate every signed LEB128 integer. The pinned original hash and native-engine byte-for-byte round trips validate the payload used here.

Eight focused tests and the full saved-game audit pass after these changes. See `results/audit.json` and [RESULTS.md](RESULTS.md).

## What would justify a next experiment

Use a separate practice pool to identify one repeatable evaluation failure. Inspect hidden activations, final-layer contributions, and the skip connection; formulate a specific explanation; then propose a targeted direct edit and evaluate it on fresh positions and games. Diagnostic inference and ablations can remain gradient-free. The reviews did not establish that such a correctable failure exists, so another speculative parameter edit was not launched.

The source research permits inference feedback and forbids training/gradients in its direct-edit experiment. It also reports an unsuccessful improvement attempt when no comparable localized pathology was found. See the [authors' article](https://raw.githubusercontent.com/RikiyaT/RikiyaT.github.io/master/blog/weight-space-programming/index.html), particularly Experiment 8 and its follow-up discussion.
