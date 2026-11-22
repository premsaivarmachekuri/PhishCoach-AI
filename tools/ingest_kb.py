"""Ingest /content/playbook/*.md into red_flags and kb_chunks tables."""
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.db import get_db


def parse_red_flags(md_text: str) -> tuple[list[dict], list[dict]]:
    sections = re.split(r"^##\s+", md_text, flags=re.MULTILINE)[1:]
    flags: list[dict] = []
    chunks: list[dict] = []
    for sec in sections:
        lines = [line.strip() for line in sec.strip().splitlines() if line.strip()]
        if not lines:
            continue
        code = lines[0]
        tier = 1
        title = code
        desc = ""
        guidance = ""
        for line in lines[1:]:
            if line.startswith("- **Tier:**"):
                tier = int(line.split("**Tier:**", 1)[1].strip())
            elif line.startswith("- **Title:**"):
                title = line.split("**Title:**", 1)[1].strip()
            elif line.startswith("- **Description:**"):
                desc = line.split("**Description:**", 1)[1].strip()
            elif line.startswith("- **Guidance:**"):
                guidance = line.split("**Guidance:**", 1)[1].strip()
        flags.append({"code": code, "description": desc or title, "difficulty_tier": tier})
        chunks.append(
            {
                "source": "red_flags.md",
                "title": f"{title} ({code})",
                "body": f"{desc} {guidance}".strip(),
            }
        )
    return flags, chunks


def parse_safe_habits(md_text: str) -> list[dict]:
    sections = re.split(r"^##\s+", md_text, flags=re.MULTILINE)[1:]
    chunks: list[dict] = []
    for sec in sections:
        lines = [line.strip() for line in sec.strip().splitlines() if line.strip()]
        if not lines:
            continue
        title = lines[0]
        body = ""
        for line in lines[1:]:
            if line.startswith("- **Title:**"):
                title = line.split("**Title:**", 1)[1].strip()
            elif line.startswith("- **Body:**"):
                body = line.split("**Body:**", 1)[1].strip()
        chunks.append({"source": "safe_habits.md", "title": title, "body": body})
    return chunks


def main() -> None:
    load_dotenv()
    root = Path(__file__).resolve().parents[1]
    rf_text = (root / "content/playbook/red_flags.md").read_text(encoding="utf-8")
    sh_text = (root / "content/playbook/safe_habits.md").read_text(encoding="utf-8")

    flags, rf_chunks = parse_red_flags(rf_text)
    sh_chunks = parse_safe_habits(sh_text)

    db = get_db()
    db.upsert("red_flags", flags, on_conflict="code")
    # Replace existing playbook chunks cleanly
    for src in ("red_flags.md", "safe_habits.md"):
        db.delete("kb_chunks", {"source": src})
    db.insert("kb_chunks", rf_chunks + sh_chunks)
    print(f"Ingested {len(flags)} red flags and {len(rf_chunks) + len(sh_chunks)} KB chunks.")


if __name__ == "__main__":
    main()
