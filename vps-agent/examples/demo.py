#!/usr/bin/env python3
"""Create two bots and DM one from the other."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hierarchy.runtime import Runtime


def main() -> int:
    store = Path(tempfile.mkdtemp(prefix="hierarchy-demo-"))
    rt = Runtime(str(store))
    lead = rt.create("lead", "Project lead", "Coordinates specialists")
    finance = rt.create("finance", "Finance", "Money surfaces", reports_to=lead.id)
    rt.chat(finance.id, "ready")
    hop = rt.dm(sender_id=finance.id, to_id=lead.id, text="drill ack, status=ok")
    print("store", store)
    print("lead", lead.id)
    print("finance", finance.id)
    print("lead history:")
    for row in rt.history(lead.id):
        print(f"  {row['role']}: {row['content']}")
    print("hop", hop.text)
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
