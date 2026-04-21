from __future__ import annotations

import os


def main() -> int:
    old_key = os.getenv("OLD_DB_ENCRYPTION_KEY", "").strip()
    new_key = os.getenv("NEW_DB_ENCRYPTION_KEY", "").strip()

    if not old_key or not new_key:
        print("Set OLD_DB_ENCRYPTION_KEY and NEW_DB_ENCRYPTION_KEY before running rotation.")
        return 1

    print("Key rotation is intentionally left as a separate operational task.")
    print("Current stub validates environment wiring only and does not rewrite ciphertext.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
