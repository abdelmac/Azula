"""Créer une configuration locale à secrets aléatoires, sans écrasement."""
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
target = root / ".env"
content = (root / ".env.example").read_text(encoding="utf-8")
content = content.replace("DJANGO_SECRET_KEY=\n", f"DJANGO_SECRET_KEY={secrets.token_urlsafe(64)}\n")
content = content.replace("DB_PASSWORD=\n", f"DB_PASSWORD={secrets.token_urlsafe(32)}\n")
try:
    with target.open("x", encoding="utf-8") as stream:
        stream.write(content)
    target.chmod(0o600)
    print(".env créé. Conservez ses secrets localement et configurez PostgreSQL.")
except FileExistsError:
    print(".env existe : aucun changement.")
