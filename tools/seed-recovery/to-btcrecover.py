#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "eth-account>=0.13.0",
# ]
# ///
"""Generate a btcrecover job for high-unknown ETH BIP39 recovery.

Use when the brute-force search space is too large for `recover.py` (3+ unknown
positions) and you need GPU acceleration. This script does NOT run any search —
it produces three artifacts in --out-dir that you copy onto the GPU box:

    btcrecover-tokens.txt   positional tokenlist
    run.sh                  ready-to-run command for seedrecover.py
    README.txt              4-step procedure for the GPU operator

CLI:
    uv run to-btcrecover.py                         # interactive
    uv run to-btcrecover.py \\
        --target 0x... \\
        --length 12 \\
        --words "abandon,?,ability,?,...,about" \\
        --path "m/44'/60'/0'/0" \\
        --addr-limit 5 \\
        --out-dir ./recovery-job

The --path is the btcrecover convention: derivation path WITHOUT the final
(address) index. btcrecover sweeps that index up to --addr-limit.
"""
from __future__ import annotations

import argparse
import os
import shlex
import sys
from pathlib import Path
from typing import Optional


def _is_eth_address(s: str) -> bool:
    if not (s.startswith("0x") and len(s) == 42):
        return False
    try:
        int(s, 16)
        return True
    except ValueError:
        return False


def _load_wordlist() -> list[str]:
    try:
        from eth_account.hdaccount.mnemonic import Language, Mnemonic
    except ImportError as e:
        sys.exit(f"missing dependency: {e}\ninstall: pip install eth-account  (or: uv run to-btcrecover.py)")
    m = Mnemonic(Language.ENGLISH)
    wl = list(m.wordlist)
    assert len(wl) == 2048 and wl[0] == "abandon" and wl[-1] == "zoo"
    return wl


def _parse_word_spec(raw: str, wordset: set[str], wordlist: list[str]) -> tuple[str, list[str]]:
    """Parse one word entry. Returns (kind, candidates).

    kind: 'anchor' | 'unknown' | 'pool'
    Accepted forms:
        ''           → ('unknown', WORDLIST)
        '?'          → ('unknown', WORDLIST)
        'cat'        → ('anchor', ['cat'])
        'cat;dog;..' → ('pool', ['cat', 'dog', ...])
    """
    w = raw.strip().lower()
    if w in ("", "?"):
        return ("unknown", wordlist)
    if ";" in w:
        pool = [x.strip().lower() for x in w.split(";") if x.strip()]
        if not pool:
            raise ValueError("empty pool")
        bad = [x for x in pool if x not in wordset]
        if bad:
            raise ValueError(f"pool words not in BIP39 wordlist: {bad}")
        seen: set[str] = set()
        return ("pool", [x for x in pool if not (x in seen or seen.add(x))])
    if w in wordset:
        return ("anchor", [w])
    raise ValueError(f"'{w}' is not a BIP39 word")


def _interactive_words(length: int, wordset: set[str], wordlist: list[str]) -> list[str]:
    print(f"\nEnter {length} words by position. Each entry can be:")
    print("    a single word (anchored)        e.g.  abandon")
    print("    ? or blank (any BIP39 word)     e.g.  ?")
    print("    pool of candidates              e.g.  cat;dog;bird")
    out: list[str] = []
    for i in range(length):
        while True:
            try:
                raw = input(f"  {i + 1:2d}: ").strip()
            except EOFError:
                sys.exit(1)
            try:
                _parse_word_spec(raw, wordset, wordlist)
                out.append(raw)
                break
            except ValueError as e:
                print(f"     {e}")
                if not raw.startswith("?") and ";" not in raw and raw:
                    matches = [x for x in wordlist if x.startswith(raw.lower()[:4])][:5]
                    if matches:
                        print(f"     did you mean: {', '.join(matches)}")
    return out


def _build_tokenlist(specs: list[tuple[str, list[str]]]) -> str:
    """Build a btcrecover tokenlist with positional anchors.

    For each position, emit one line with `^N^cand` tokens for every candidate
    allowed at that position. btcrecover treats multiple tokens on one line as
    mutually exclusive — exactly one per guess at that anchor.
    """
    lines: list[str] = []
    for i, (_kind, cands) in enumerate(specs):
        pos = i + 1  # btcrecover anchors are 1-indexed
        tokens = [f"^{pos}^{c}" for c in cands]
        lines.append(" ".join(tokens))
    return "\n".join(lines) + "\n"


def _build_run_sh(target: str, length: int, path: str, addr_limit: int, gpu: bool) -> str:
    """Emit a run.sh that invokes seedrecover.py with all flags pre-filled.

    --bip32-path uses the btcrecover convention: path WITHOUT the final address
    index. btcrecover sweeps the final index up to --addr-limit.
    """
    flags = [
        "python3 seedrecover.py",
        "  --no-dupchecks",
        "  --no-eta",
        "  --no-pause",
        "  --no-gui",
        "  --wallet-type ethereum",
        f"  --mnemonic-length {length}",
        "  --language EN",
        f"  --addrs {target}",
        f"  --addr-limit {addr_limit}",
        f"  --bip32-path {shlex.quote(path)}",
        "  --tokenlist btcrecover-tokens.txt",
        "  --keep-tokens-order",
    ]
    if gpu:
        flags.append("  --enable-opencl")

    body = " \\\n".join(flags)
    return f"""#!/usr/bin/env bash
# Generated by tools/seed-recovery/to-btcrecover.py
#
# Run this on the GPU box AFTER cloning btcrecover and installing its
# dependencies (see README.txt).
#
# Operational hygiene before running:
#   unset HISTFILE                    # don't log the seed phrase to shell history
#   tmux/screen scrollback OFF        # match output stays in scrollback otherwise
#   close other users' shell sessions on this host
#
# A successful run prints the seed phrase to stdout. Capture it and write
# it on paper IMMEDIATELY. Then close the terminal.

set -e
cd "$(dirname "$0")"

{body}
"""


def _build_readme(
    target: str,
    length: int,
    specs: list[tuple[str, list[str]]],
    required: list[str],
    gpu: bool,
) -> str:
    raw = 1
    for _, cands in specs:
        raw *= len(cands)
    last_size = len(specs[-1][1])
    cs_div = (16 if length == 12 else 256) if last_size > 1 else 1
    filtered = max(raw // cs_div, 1)
    n_anchor = sum(1 for k, _ in specs if k == "anchor")
    n_pool = sum(1 for k, _ in specs if k == "pool")
    n_unknown = sum(1 for k, _ in specs if k == "unknown")

    pool_lines = "\n".join(
        f"    pos {i + 1}: pool of {len(cands)} candidates  ({', '.join(cands[:6])}{'...' if len(cands) > 6 else ''})"
        for i, (k, cands) in enumerate(specs)
        if k == "pool"
    )
    pool_block = f"\nPool positions:\n{pool_lines}\n" if pool_lines else ""

    required_block = ""
    if required:
        required_block = (
            f"\nRequired-set (operator MUST post-filter):\n"
            f"    The recovered phrase must contain at least one of: {required}\n"
            f"    btcrecover does NOT enforce this. When btcrecover prints 'Seed found',\n"
            f"    verify the phrase contains one of the required words. If it does not,\n"
            f"    the match is for the WRONG wallet (target address collision is essentially\n"
            f"    impossible, so this should never happen — but check anyway).\n"
        )

    return f"""btcrecover recovery job
=======================

Target ETH address: {target}
Mnemonic length:    {length}
Position breakdown: {n_anchor} anchored, {n_pool} pool, {n_unknown} full-unknown
Search space:       {raw:,} raw / ~{filtered:,} after BIP39 checksum filter
Acceleration:       {"OpenCL/GPU enabled" if gpu else "CPU only"}
{pool_block}{required_block}

Files in this directory
-----------------------
  btcrecover-tokens.txt   positional tokenlist (one line per phrase position)
  run.sh                  ready-to-run command
  README.txt              this file

How to run
----------
1. Clone btcrecover on the GPU host:
       git clone https://github.com/3rdIteration/btcrecover.git
       cd btcrecover

2. Install dependencies:
       pip install -r requirements.txt
   For GPU:  also install OpenCL drivers + pyopencl per
             https://btcrecover.readthedocs.io/en/latest/GPU_Acceleration/

3. Copy the three files from this job into the btcrecover/ directory:
       cp /path/to/job/btcrecover-tokens.txt /path/to/job/run.sh \\
          /path/to/btcrecover/
       chmod +x /path/to/btcrecover/run.sh

4. Disable shell history for this session, then run:
       unset HISTFILE
       cd /path/to/btcrecover
       ./run.sh

When a match is found, btcrecover prints:
    Seed found: word1 word2 word3 ... word{length}

WRITE THIS ON PAPER. Close the terminal. Wipe the GPU instance.

Notes
-----
- The bip32-path in run.sh is the path WITHOUT the final address index;
  btcrecover sweeps that index up to --addr-limit. If your wallet uses
  Ledger Live (account index varies), edit run.sh and change the path
  template, or run multiple times with different paths.
- A successful run also writes nothing to disk by default. The phrase
  exists only in stdout and process memory.
- On rented GPU (vast.ai/RunPod): the host operator can read your process
  memory. Use a provider you trust or own the hardware.
"""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target", help="Target ETH address (0x...)")
    p.add_argument("--length", type=int, choices=[12, 24], help="Phrase length")
    p.add_argument(
        "--words",
        help="Comma-separated word specs. Each spec is one of: a BIP39 word (anchored), "
        "'?' (full unknown = all 2048 BIP39 words), or a semicolon-separated pool e.g. 'cat;dog;bird'. "
        "Example: 'abandon,?,cat;dog;bird,about'",
    )
    p.add_argument(
        "--required",
        help="Comma-separated words; the phrase must contain at least one of them. "
        "WARNING: btcrecover does NOT enforce this in its tokenlist; the constraint is recorded "
        "in README.txt and the operator must post-filter, OR you should fold these into pool entries "
        "at unknown positions yourself.",
    )
    p.add_argument(
        "--path",
        default="m/44'/60'/0'/0",
        help="Derivation path EXCLUDING the final address index (btcrecover convention; default: %(default)s)",
    )
    p.add_argument("--addr-limit", type=int, default=5, help="Number of address indexes to sweep per phrase candidate (default: %(default)s)")
    p.add_argument("--no-gpu", action="store_true", help="Don't include --enable-opencl in run.sh (CPU-only test runs)")
    p.add_argument("--out-dir", type=Path, default=Path("recovery-job"), help="Output directory (default: %(default)s)")
    p.add_argument("--force", action="store_true", help="Overwrite an existing --out-dir")
    args = p.parse_args()

    print("=== btcrecover job generator ===\n")

    wordlist = _load_wordlist()
    wordset = set(wordlist)

    # Length
    length = args.length
    if length is None:
        while True:
            try:
                v = input("Phrase length [12/24]: ").strip()
            except EOFError:
                return 1
            if v in ("12", "24"):
                length = int(v)
                break
            print("Must be 12 or 24")

    # Target
    target = args.target
    if target is None:
        try:
            target = input("Target ETH address (0x...): ").strip()
        except EOFError:
            return 1
    if not _is_eth_address(target):
        print(f"error: invalid ETH address: {target}", file=sys.stderr)
        return 1

    # Words
    if args.words:
        raw_specs = [w.strip() for w in args.words.split(",")]
    else:
        raw_specs = _interactive_words(length, wordset, wordlist)

    if len(raw_specs) != length:
        print(f"error: got {len(raw_specs)} specs, expected {length}", file=sys.stderr)
        return 1

    specs: list[tuple[str, list[str]]] = []
    for i, spec in enumerate(raw_specs):
        try:
            specs.append(_parse_word_spec(spec, wordset, wordlist))
        except ValueError as e:
            print(f"error: position {i + 1}: {e}", file=sys.stderr)
            return 1

    # Required-set
    required: list[str] = []
    if args.required:
        required = [w.strip().lower() for w in args.required.split(",") if w.strip()]
        bad = [w for w in required if w not in wordset]
        if bad:
            print(f"error: --required words not in BIP39 wordlist: {bad}", file=sys.stderr)
            return 1

    n_anchor = sum(1 for k, _ in specs if k == "anchor")
    n_pool = sum(1 for k, _ in specs if k == "pool")
    n_unknown = sum(1 for k, _ in specs if k == "unknown")

    raw_space = 1
    for _, cands in specs:
        raw_space *= len(cands)
    last_size = len(specs[-1][1])
    cs_div = (16 if length == 12 else 256) if last_size > 1 else 1
    filtered = max(raw_space // cs_div, 1)

    print(f"\nPosition breakdown: {n_anchor} anchored, {n_pool} pool, {n_unknown} full-unknown")
    for i, (k, cands) in enumerate(specs):
        if k == "pool":
            print(f"    pos {i + 1}: pool of {len(cands)} candidates")
    print(f"Raw search space:   {raw_space:,}")
    print(f"After checksum:     {filtered:,}")
    if required:
        print(f"Required-set:       {required}  (recorded in README; btcrecover does NOT enforce)")
    print(f"Target:             {target}")
    print(f"Path template:      {args.path}  (final index swept up to {args.addr_limit})")
    print(f"GPU:                {'OFF (--no-gpu)' if args.no_gpu else 'ON (--enable-opencl in run.sh)'}")

    out = args.out_dir
    if out.exists() and not args.force:
        print(f"\nerror: {out} already exists. Pass --force to overwrite.", file=sys.stderr)
        return 1
    out.mkdir(parents=True, exist_ok=True)

    tokens_path = out / "btcrecover-tokens.txt"
    run_path = out / "run.sh"
    readme_path = out / "README.txt"

    tokens_path.write_text(_build_tokenlist(specs))
    run_path.write_text(_build_run_sh(target, length, args.path, args.addr_limit, gpu=not args.no_gpu))
    os.chmod(run_path, 0o755)
    readme_path.write_text(_build_readme(target, length, specs, required, gpu=not args.no_gpu))

    print(f"\nWrote 3 files to {out.resolve()}:")
    for f in (tokens_path, run_path, readme_path):
        print(f"  {f.name}  ({f.stat().st_size:,} bytes)")
    print("\nNext steps:")
    print(f"  1. Copy {out.name}/ to the GPU host (scp / rsync / USB).")
    print(f"  2. Follow {out.name}/README.txt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
