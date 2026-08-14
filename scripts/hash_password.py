#!/usr/bin/env python3
"""Print a bcrypt hash for seeding Airtable Users.password_hash."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from streamlit_app.auth import hash_password

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: hash_password.py <password>", file=sys.stderr)
        sys.exit(1)
    print(hash_password(sys.argv[1]))
