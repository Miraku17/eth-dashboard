#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "eth-account>=0.13.0",
#   "tqdm>=4.66.0",
# ]
# ///
"""BIP39 seed phrase recovery — multi-process Python CLI.

For 1-2 unknown positions the browser tool (recover.html) is fine.
This is for 3+ unknowns where you need every core working in parallel.

Usage:
    uv run recover.py                          # interactive prompts
    uv run recover.py --target 0xabc... --length 12 \
        --words "abandon,?,ability,?,...,about" \
        --accounts 0-9

If you don't have uv, install deps manually then run with python3:
    pip install eth-account tqdm
    python3 recover.py

RUN OFFLINE. Disconnect from the internet before entering any words.
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import signal
import sys
import time
from typing import Optional


# Worker-process globals (initialised once per worker via Pool initializer)
_M = None
_WORDLIST: list[str] = []


def _worker_init() -> None:
    """Called once per pool worker."""
    global _M, _WORDLIST
    from eth_account import Account
    from eth_account.hdaccount.mnemonic import Language, Mnemonic

    Account.enable_unaudited_hdwallet_features()
    _M = Mnemonic(Language.ENGLISH)
    _WORDLIST = list(_M.wordlist)
    # Workers ignore SIGINT; the parent handles Ctrl-C and terminates the pool.
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def _search_chunk(args: tuple) -> Optional[tuple[str, str, str, int]]:
    """Process one chunk; return (phrase, path, address, candidates_validated) or None.

    args: (chunk_start, chunk_count, candidates_per_pos, path_tpl,
           account_indices, target_lc, required_set)

    candidates_per_pos: list[list[str]] — candidate words at each position.
        Anchored position has a single-element list; pool has the pool list;
        full unknown has the full 2048-word BIP39 wordlist.
    required_set: frozenset[str] — at-least-one must appear in the phrase.
        Empty set disables the filter.
    """
    (
        chunk_start,
        chunk_count,
        candidates_per_pos,
        path_tpl,
        account_indices,
        target_lc,
        required_set,
    ) = args

    from eth_account import Account
    from eth_account.hdaccount import key_from_seed, seed_from_mnemonic

    if _M is None:
        _worker_init()

    length = len(candidates_per_pos)
    sizes = [len(c) for c in candidates_per_pos]
    phrase: list[Optional[str]] = [None] * length
    validated = 0

    for offset in range(chunk_count):
        linear = chunk_start + offset
        for i in range(length):
            phrase[i] = candidates_per_pos[i][linear % sizes[i]]
            linear //= sizes[i]

        if required_set and required_set.isdisjoint(phrase):
            continue

        phrase_str = " ".join(phrase)  # type: ignore[arg-type]
        if not _M.is_mnemonic_valid(phrase_str):
            continue
        validated += 1

        seed = seed_from_mnemonic(phrase_str, "")
        for a in account_indices:
            path = path_tpl.replace("{i}", str(a))
            try:
                key = key_from_seed(seed, account_path=path)
                addr = Account.from_key(key).address
            except Exception:
                continue
            if addr.lower() == target_lc:
                return (phrase_str, path, addr, validated)

    return (None, None, None, validated)


def _parse_word_spec(raw: str, wordset: set[str], wordlist: list[str]) -> tuple[str, list[str]]:
    """Parse one word entry. Returns (kind, candidates).

    kind: 'anchor' | 'unknown' | 'pool'
    candidates: list of candidate BIP39 words (single element for anchor).

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
        # Dedupe while preserving order
        seen: set[str] = set()
        deduped = [x for x in pool if not (x in seen or seen.add(x))]
        return ("pool", deduped)
    if w in wordset:
        return ("anchor", [w])
    raise ValueError(f"'{w}' is not a BIP39 word")


def _parse_accounts(s: str) -> list[int]:
    if "-" in s:
        lo, hi = s.split("-", 1)
        return list(range(int(lo), int(hi) + 1))
    return [int(s)]


def _is_eth_address(s: str) -> bool:
    if not (s.startswith("0x") and len(s) == 42):
        return False
    try:
        int(s, 16)
        return True
    except ValueError:
        return False


def _print_match(phrase: str, path: str, addr: str) -> None:
    bar = "=" * 64
    print()
    print(bar)
    print("MATCH FOUND")
    print(bar)
    print(f"Phrase:  {phrase}")
    print(f"Path:    {path}")
    print(f"Address: {addr}")
    print(bar)
    print("Write the phrase down on paper now.")
    print("Then close this terminal and clear shell history (e.g. `history -c`).")


def _interactive_words(length: int, wordset: set[str], wordlist: list[str]) -> list[str]:
    print(f"\nEnter {length} words by position. Each entry can be:")
    print("    a single word (anchored)        e.g.  abandon")
    print("    ? or blank (any BIP39 word)     e.g.  ?")
    print("    pool of candidates              e.g.  cat;dog;bird")
    words: list[str] = []
    for i in range(length):
        while True:
            try:
                raw = input(f"  {i + 1:2d}: ").strip()
            except EOFError:
                print()
                sys.exit(1)
            try:
                _parse_word_spec(raw, wordset, wordlist)
                words.append(raw)
                break
            except ValueError as e:
                print(f"     {e}")
                if not raw.startswith("?") and ";" not in raw and raw:
                    matches = [x for x in wordlist if x.startswith(raw.lower()[:4])][:5]
                    if matches:
                        print(f"     did you mean: {', '.join(matches)}")
    return words


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--target", help="Target ETH address (0x...)")
    p.add_argument("--length", type=int, choices=[12, 24], help="Phrase length (12 or 24)")
    p.add_argument(
        "--words",
        help="Comma-separated word specs. Each spec is one of: "
        "a BIP39 word (anchored), '?' (full unknown), "
        "or a semicolon-separated pool e.g. 'cat;dog;bird'. "
        "Example: 'abandon,?,cat;dog;bird,about'",
    )
    p.add_argument(
        "--required",
        help="Comma-separated words; the phrase must contain at least one of them somewhere.",
    )
    p.add_argument(
        "--path",
        default="m/44'/60'/0'/0/{i}",
        help="Derivation path template; {i} = account index (default: %(default)s)",
    )
    p.add_argument(
        "--accounts",
        default="0-4",
        help="Account index range, e.g. 0-9 (default: %(default)s)",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=mp.cpu_count(),
        help="Parallel worker processes (default: %(default)s)",
    )
    p.add_argument(
        "--chunk-size",
        type=int,
        default=32768,
        help="Candidates per worker chunk (default: %(default)s). "
        "Smaller = more progress updates; larger = less IPC overhead.",
    )
    p.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    args = p.parse_args()

    try:
        from eth_account import Account
        from eth_account.hdaccount.mnemonic import Language, Mnemonic
        from tqdm import tqdm
    except ImportError as e:
        print(f"missing dependency: {e}", file=sys.stderr)
        print("install:  pip install eth-account tqdm", file=sys.stderr)
        print("or:       uv run recover.py  (auto-installs)", file=sys.stderr)
        return 1

    Account.enable_unaudited_hdwallet_features()
    m = Mnemonic(Language.ENGLISH)
    wordlist = list(m.wordlist)
    wordset = set(wordlist)
    assert len(wordlist) == 2048 and wordlist[0] == "abandon" and wordlist[-1] == "zoo"

    # Self-test: derive canonical zero-vector phrase to confirm the crypto path is intact.
    from eth_account.hdaccount import key_from_seed, seed_from_mnemonic
    test_phrase = " ".join(["abandon"] * 11 + ["about"])
    test_seed = seed_from_mnemonic(test_phrase, "")
    test_key = key_from_seed(test_seed, account_path="m/44'/60'/0'/0/0")
    test_addr = Account.from_key(test_key).address
    if test_addr.lower() != "0x9858effd232b4033e47d90003d41ec34ecaeda94":
        print(f"FATAL: crypto self-test failed; got {test_addr}", file=sys.stderr)
        return 1

    print("=== BIP39 seed recovery (offline) ===")
    print("Disconnect from the internet before continuing.")

    # --- Length ---
    length = args.length
    if length is None:
        while True:
            try:
                v = input("\nPhrase length [12/24]: ").strip()
            except EOFError:
                return 1
            if v in ("12", "24"):
                length = int(v)
                break
            print("Must be 12 or 24")

    # --- Target address ---
    target = args.target
    if target is None:
        try:
            target = input("Target ETH address (0x...): ").strip()
        except EOFError:
            return 1
    if not _is_eth_address(target):
        print(f"error: invalid ETH address: {target}", file=sys.stderr)
        return 1
    target_lc = target.lower()

    # --- Account range ---
    try:
        account_indices = _parse_accounts(args.accounts)
    except ValueError:
        print(f"error: invalid --accounts: {args.accounts}", file=sys.stderr)
        return 1
    if not account_indices or any(a < 0 for a in account_indices):
        print(f"error: invalid --accounts: {args.accounts}", file=sys.stderr)
        return 1

    # --- Path ---
    path_tpl = args.path
    if not path_tpl.startswith("m/"):
        print(f"error: derivation path must start with 'm/': {path_tpl}", file=sys.stderr)
        return 1

    # --- Words ---
    if args.words:
        word_specs = [w.strip() for w in args.words.split(",")]
    else:
        word_specs = _interactive_words(length, wordset, wordlist)

    if len(word_specs) != length:
        print(f"error: got {len(word_specs)} word specs, expected {length}", file=sys.stderr)
        return 1

    candidates_per_pos: list[list[str]] = []
    kinds: list[str] = []
    for i, raw in enumerate(word_specs):
        try:
            kind, cands = _parse_word_spec(raw, wordset, wordlist)
        except ValueError as e:
            print(f"error: position {i + 1}: {e}", file=sys.stderr)
            return 1
        kinds.append(kind)
        candidates_per_pos.append(cands)

    # --- Required-set ---
    required_set: frozenset[str] = frozenset()
    if args.required:
        req = [w.strip().lower() for w in args.required.split(",") if w.strip()]
        bad = [w for w in req if w not in wordset]
        if bad:
            print(f"error: --required words not in BIP39 wordlist: {bad}", file=sys.stderr)
            return 1
        required_set = frozenset(req)

    n_anchored = sum(1 for k in kinds if k == "anchor")
    n_pool = sum(1 for k in kinds if k == "pool")
    n_unknown = sum(1 for k in kinds if k == "unknown")

    # Total raw search space and post-checksum estimate
    raw = 1
    for c in candidates_per_pos:
        raw *= len(c)

    last_size = len(candidates_per_pos[-1])
    if last_size > 1:
        cs_div = 16 if length == 12 else 256
    else:
        cs_div = 1
    filtered = max(raw // cs_div, 1)

    pool_summary = ""
    for i, k in enumerate(kinds):
        if k == "pool":
            pool_summary += f"\n    pos {i + 1}: pool of {len(candidates_per_pos[i])} candidates"

    print(f"\nPosition breakdown: {n_anchored} anchored, {n_pool} pool, {n_unknown} full-unknown{pool_summary}")
    print(f"Raw search space:   {raw:,}")
    print(f"After checksum:     {filtered:,}")
    if required_set:
        print(f"Required-set:       {sorted(required_set)} (≥1 must appear)")
    print(f"Workers:            {args.workers}")
    print(f"Account indexes:    {account_indices}")
    print(f"Path template:      {path_tpl}")
    print(f"Target:             {target}")

    if not args.yes:
        try:
            v = input("\nProceed? [y/N]: ").strip().lower()
        except EOFError:
            return 1
        if v not in ("y", "yes"):
            print("aborted.")
            return 0

    # --- Zero-unknowns shortcut (every position anchored to a single word) ---
    if raw == 1:
        phrase_str = " ".join(c[0] for c in candidates_per_pos)
        if required_set and required_set.isdisjoint(phrase_str.split()):
            print("\nPhrase does not contain any required-set word.")
            return 1
        if not m.is_mnemonic_valid(phrase_str):
            print("\nPhrase has invalid BIP39 checksum.")
            return 1
        seed = seed_from_mnemonic(phrase_str, "")
        for a in account_indices:
            path = path_tpl.replace("{i}", str(a))
            key = key_from_seed(seed, account_path=path)
            addr = Account.from_key(key).address
            if addr.lower() == target_lc:
                _print_match(phrase_str, path, addr)
                return 0
        print(f"\nNo match in account range {args.accounts}.")
        return 1

    # --- Distribute work ---
    chunk_size = max(1, args.chunk_size)
    n_chunks = (raw + chunk_size - 1) // chunk_size

    def chunk_args_iter():
        for c in range(n_chunks):
            start = c * chunk_size
            count = min(chunk_size, raw - start)
            yield (
                start,
                count,
                candidates_per_pos,
                path_tpl,
                account_indices,
                target_lc,
                required_set,
            )

    pool = mp.Pool(args.workers, initializer=_worker_init)
    start_time = time.time()
    total_validated = 0
    found = None

    try:
        with tqdm(total=filtered, unit="cand", smoothing=0.05, mininterval=0.5) as pbar:
            for result in pool.imap_unordered(_search_chunk, chunk_args_iter()):
                phrase_str, path, addr, validated = result
                total_validated += validated
                pbar.update(validated)
                if phrase_str is not None:
                    found = (phrase_str, path, addr)
                    break
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        pool.terminate()
        pool.join()
        return 130
    finally:
        pool.terminate()
        pool.join()

    elapsed = time.time() - start_time
    rate = total_validated / elapsed if elapsed > 0 else 0
    print(f"\nValidated {total_validated:,} candidates in {elapsed:.1f}s ({rate:,.0f}/sec).")

    if found:
        _print_match(*found)
        return 0

    print("\nNo match found. Possible reasons:")
    print("  - One of the known words is wrong (mark it as ? and re-run)")
    print("  - Wrong derivation path (try m/44'/60'/{i}'/0/0 for Ledger Live)")
    print("  - Account range too narrow (try --accounts 0-19)")
    print("  - Wrong phrase length (try the other of 12 / 24)")
    print("  - Target address is from a different wallet")
    return 1


if __name__ == "__main__":
    sys.exit(main())
