"""One-shot deal backup script. Exports deal to JSON using the app's own exporter."""
import asyncio
import json
import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import AsyncSessionLocal
from app.exporters.deal_export import export_deal_json


async def main(deal_id: str, output_path: str) -> None:
    async with AsyncSessionLocal() as session:
        data = await export_deal_json(session, deal_id)
    out = Path(output_path)
    out.write_text(json.dumps(data, indent=2, default=str))
    print(f"Exported deal {deal_id} → {out} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python scripts/backup_deal.py <deal_id> <output_path>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
