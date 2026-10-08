from pathlib import Path
import sys

# Vercel starts at the repository root; the existing backend package is nested.
backend_path = str(Path(__file__).resolve().parent / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.main import app
