"""Generate an argon2id hash for AUTH_PASSWORD_HASH.

Usage:
    python -m app.scripts.hash_password
"""
import getpass
import sys

from app.core.auth import hash_password


def main() -> int:
    pw1 = getpass.getpass("New password: ")
    pw2 = getpass.getpass("Confirm: ")
    if pw1 != pw2:
        print("passwords do not match", file=sys.stderr)
        return 1
    if len(pw1) < 8:
        print("password must be at least 8 characters", file=sys.stderr)
        return 1
    print(hash_password(pw1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
