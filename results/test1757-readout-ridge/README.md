# Reproduce the test1757 NNUE edit

This patch changes nine output biases in Shawn Xu's test1757 network. The original and patched networks contain 138,360,528 bytes each and differ at 11 byte positions. [Upstream source](https://github.com/xu-shawn/Stockfish/tree/d5a2bda7f028430f79e1789d47ae3228defb843b)

Download the original network and run the following command from the lab repository with Python 3.8 or later. Give the output file a new name. [Download nn-18cd32e11a9c.nnue](https://data.stockfishchess.org/nn/nn-18cd32e11a9c.nnue)

```text
python scripts/apply_test1757_readout_ridge.py nn-18cd32e11a9c.nnue nn-d5c257728ba5.nnue
```

Use these commands to check the result in memory or reverse the patch.

```text
python scripts/apply_test1757_readout_ridge.py --verify-only nn-18cd32e11a9c.nnue
python scripts/apply_test1757_readout_ridge.py --reverse nn-d5c257728ba5.nnue restored-original.nnue
```

| Network | Expected SHA-256 |
| --- | --- |
| Original | `18cd32e11a9cac7c595bc6ebf1301088da8e1f2c7b31efda88dbc74c71f5d2cf` |
| Edited | `d5c257728ba53cb9808543ce2800080c860f1c878896cd1b17f75ed4b20aafee` |

The applier verifies the complete input and output hashes. The upstream network is CC0. The lab publishes the recipe and Python script under GPL-3.0-or-later.

The edited network reduced average error against depth-13 search by 0.1041 centipawns on 146 stable held-out positions across 15 opening families. The match uses both colors of each opening to measure playing strength. [Measurement and verification](../test1757-readout-ridge-candidate.json) · [Fixed match plan](../test1757-readout-ridge-screen-plan.json) · [Experiment source](https://github.com/0mis/Stockfish/tree/08abd7bd1c3fa9a504a0fa8556a6bef6633933cc/research/readout_ridge)
