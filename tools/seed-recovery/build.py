#!/usr/bin/env python3
"""Build a single-file offline BIP39 seed recovery HTML page.

Downloads ethers.js v6 (UMD bundle) and inlines it into template.html,
producing recover.html. The operator runs this once (needs internet);
the resulting recover.html is then handed to the client to run offline.

Usage:
    python3 build.py                     # download ethers from unpkg, build recover.html
    python3 build.py --ethers <path>     # use a locally provided ethers.umd.min.js
    python3 build.py --out <path>        # custom output path
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

ETHERS_VERSION = "6.13.4"
ETHERS_URL = f"https://unpkg.com/ethers@{ETHERS_VERSION}/dist/ethers.umd.min.js"
PLACEHOLDER = "/* __ETHERS_BUNDLE__ */"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ethers", type=Path, help="Path to a local ethers.umd.min.js (skip download)")
    parser.add_argument("--out", type=Path, default=Path("recover.html"), help="Output HTML path (default: recover.html)")
    parser.add_argument("--cache", type=Path, default=Path(".ethers-cache.js"), help="Cache file for downloaded ethers")
    args = parser.parse_args()

    here = Path(__file__).parent.resolve()
    template_path = here / "template.html"
    cache_path = here / args.cache
    out_path = args.out if args.out.is_absolute() else here / args.out

    if not template_path.exists():
        print(f"error: template.html not found at {template_path}", file=sys.stderr)
        return 1

    if args.ethers:
        print(f"Using local ethers bundle: {args.ethers}", file=sys.stderr)
        ethers_src = args.ethers.read_text(encoding="utf-8")
    elif cache_path.exists():
        print(f"Using cached ethers bundle: {cache_path}", file=sys.stderr)
        ethers_src = cache_path.read_text(encoding="utf-8")
    else:
        print(f"Downloading ethers.js v{ETHERS_VERSION} from {ETHERS_URL}", file=sys.stderr)
        try:
            with urllib.request.urlopen(ETHERS_URL, timeout=30) as resp:
                ethers_src = resp.read().decode("utf-8")
        except Exception as e:
            print(f"error: download failed: {e}", file=sys.stderr)
            print("hint: download the file manually and pass --ethers <path>", file=sys.stderr)
            return 1
        cache_path.write_text(ethers_src, encoding="utf-8")
        print(f"Cached to {cache_path}", file=sys.stderr)

    sha = hashlib.sha256(ethers_src.encode("utf-8")).hexdigest()
    print(f"ethers bundle SHA256: {sha}", file=sys.stderr)
    print(f"ethers bundle size:   {len(ethers_src) // 1024} KB", file=sys.stderr)

    template = template_path.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        print(f"error: placeholder {PLACEHOLDER!r} not found in template.html", file=sys.stderr)
        return 1

    output = template.replace(PLACEHOLDER, ethers_src)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output, encoding="utf-8")

    print(f"\nWrote {out_path} ({len(output) // 1024} KB)", file=sys.stderr)
    print("\nNext steps:", file=sys.stderr)
    print("  1. Send recover.html to the client over a secure channel (Signal, encrypted email, USB).", file=sys.stderr)
    print("  2. Tell them to DISCONNECT FROM THE INTERNET, then double-click the file to open it.", file=sys.stderr)
    print("  3. After recovery, they should write the phrase on paper and DELETE the HTML file.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
