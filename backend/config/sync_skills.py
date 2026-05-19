#!/usr/bin/env python3
"""将 config/ai_prompts.py 中的 Cursor 技能正文同步到 skills/*.md"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from config.ai_prompts import AGENT_SKILLS  # noqa: E402


def main() -> None:
    for name, spec in AGENT_SKILLS.items():
        rel = spec["path"]
        out = ROOT / rel
        content = f"---\n{spec['meta'].strip()}\n---\n\n{spec['body'].rstrip()}\n"
        out.write_text(content, encoding="utf-8")
        print(f"updated {rel}")
    print("done")


if __name__ == "__main__":
    main()
