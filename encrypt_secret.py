import argparse
import os
import sys


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(CURRENT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from secret_cipher import encrypt_text, generate_key


def main() -> None:
    parser = argparse.ArgumentParser(description="Encrypt secrets for config.json")
    parser.add_argument("--text", required=True, help="Plain text to encrypt")
    parser.add_argument(
        "--key",
        default="",
        help="Fernet key; if omitted, tool generates one",
    )
    args = parser.parse_args()

    key = args.key.strip() or generate_key()
    cipher = encrypt_text(args.text, key)

    print("KEY=" + key)
    print("CIPHER=" + cipher)


if __name__ == "__main__":
    main()

