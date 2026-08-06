from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import secrets


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a PBKDF2-SHA256 value for AGENT_AUTH_*_HASH variables.")
    parser.add_argument("--secret", help="Avoid on shared shells; omitted means secure prompt.")
    parser.add_argument("--iterations", type=int, default=310_000)
    args = parser.parse_args()
    secret = args.secret or getpass.getpass("Secret: ")
    salt = secrets.token_urlsafe(18)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt.encode(), args.iterations)
    encoded = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    print(f"pbkdf2_sha256:{args.iterations}:{salt}:{encoded}")


if __name__ == "__main__":
    main()
