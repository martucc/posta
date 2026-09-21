import os
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "scripts"))

# L'ambiente minimo perche' gmail.py si importi senza toccare la rete.
os.environ.setdefault("OWNER_EMAIL", "prova@example.com")
os.environ.setdefault("GMAIL_TOKEN_JSON", "{}")
os.environ.setdefault("PAGE_URL", "https://example.github.io/posta/")
