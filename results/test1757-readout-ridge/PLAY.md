# Play with the nine-bias NNUE edit

Use the test1757 prefetch build with this network. It supports the network's 92 stored output heads. The Windows BMI2 executable used in the match has SHA-256 `12a8e7bfdd9b1189b4350bd9ebef3501be1e89bd5fa41dcb56921f85ba23869a`. [Compatible engine source](https://github.com/0mis/Stockfish/tree/7a17b53bcaf93f54a23ad65f309c413585500c82) · [Windows build](https://github.com/0mis/Stockfish/actions/runs/42543250921)

Recreate `nn-d5c257728ba5.nnue` and start the engine in the directory containing that file. In a UCI chess GUI, choose the file for the engine's `EvalFile` option. [Recreate the network](README.md)

To check it in the engine console, enter these UCI commands. Wait for `uciok` after the first command and `readyok` after `isready`.

```text
uci
setoption name EvalFile value nn-d5c257728ba5.nnue
isready
position startpos
go depth 12
```

The engine should report the network filename when it starts searching. The tested build reproduced a canonical benchmark of 2,376,690 nodes twice with this file.
