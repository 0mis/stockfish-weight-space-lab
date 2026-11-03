$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

foreach ($directory in @('downloads', 'vendor', 'research', 'nets', 'results', 'openings/source')) {
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
}

$artifacts = @(
    @{
        File = 'stockfish-windows-x86-64-universal.zip'
        Url = 'https://github.com/official-stockfish/Stockfish/releases/download/sf_19/stockfish-windows-x86-64-universal.zip'
        Sha256 = '3c8bf1f9ea66a09350a40df4f632288285ac206d99f33ab5842c408fc30b48a7'
        Destination = 'vendor/stockfish'
        Expected = 'vendor/stockfish/stockfish/stockfish-windows-x86-64-universal.exe'
    },
    @{
        File = 'fastchess-windows-x86-64.zip'
        Url = 'https://github.com/Disservin/fastchess/releases/download/v1.8.2-alpha/fastchess-windows-x86-64.zip'
        Sha256 = '007ce550dc809510b34622a1aeb43fd443d40284045bef5c1bc39c8941114143'
        Destination = 'vendor/fastchess'
        Expected = 'vendor/fastchess/fastchess-windows-x86-64/fastchess.exe'
    },
    @{
        File = '8moves_v3.pgn.zip'
        Url = 'https://raw.githubusercontent.com/official-stockfish/books/a804a97e709f40aa75a00f9d19e84915b7a3a45c/8moves_v3.pgn.zip'
        Sha256 = '7e1e9dd118b4bb97d8a8b5b8a790c86e21f8509d59a27d2883767d94477be02e'
        Destination = 'openings/source'
        Expected = 'openings/source/8moves_v3.pgn'
    }
)

foreach ($artifact in $artifacts) {
    $archive = Join-Path 'downloads' $artifact.File
    if (-not (Test-Path -LiteralPath $archive)) {
        Invoke-WebRequest -Uri $artifact.Url -OutFile $archive
    }
    $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $artifact.Sha256) {
        throw ('Checksum mismatch: ' + $archive)
    }
    # Re-extract verified archives so that a cached executable cannot drift.
    Expand-Archive -LiteralPath $archive -DestinationPath $artifact.Destination -Force
    if (-not (Test-Path -LiteralPath $artifact.Expected)) {
        throw ('Missing extracted artifact: ' + $artifact.Expected)
    }
}

@{
    repository = 'https://github.com/official-stockfish/books'
    commit = 'a804a97e709f40aa75a00f9d19e84915b7a3a45c'
    file = '8moves_v3.pgn.zip'
    sha256 = '7e1e9dd118b4bb97d8a8b5b8a790c86e21f8509d59a27d2883767d94477be02e'
} | ConvertTo-Json | Set-Content -LiteralPath 'research/book-source.json' -Encoding utf8

if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    & uv venv --python 3.11 .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the project Python environment using uv.' }
}
& uv pip sync --python '.venv/Scripts/python.exe' requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Could not install the pinned project requirements.' }

if (-not (Test-Path -LiteralPath 'nets/original.nnue')) {
    @('export_net nets/original.nnue', 'quit') | & 'vendor/stockfish/stockfish/stockfish-windows-x86-64-universal.exe'
    if ($LASTEXITCODE -ne 0) { throw 'Could not export the original network.' }
}

& '.venv/Scripts/python.exe' scripts/lab.py prepare
if ($LASTEXITCODE -ne 0) { throw 'Preparation failed.' }
& '.venv/Scripts/python.exe' -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Validation failed.' }
