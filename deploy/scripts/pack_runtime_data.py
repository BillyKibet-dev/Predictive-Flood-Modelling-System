"""Bundle the git-ignored runtime data for the server (run on the development PC).

    python deploy/scripts/pack_runtime_data.py

Writes deploy/out/runtime-data.tar.gz and a SHA-256 list inside it. Contents:
  repo/data/model_v1, repo/models/nextday-proxy-v1     -> /srv/nairobifloodwatch/...
  store/point_weather, store/imerg_early, store/operational_sources
                                                       -> /var/lib/nairobifloodwatch/...
No .env, credentials, report photos or database contents are included.
"""
import hashlib
import io
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "deploy/out/runtime-data.tar.gz"
ITEMS = [
    ("data/model_v1", "repo/data/model_v1"),
    ("models/nextday-proxy-v1", "repo/models/nextday-proxy-v1"),
    ("data/hotspots/point_weather", "store/point_weather"),
    ("data/hotspots/imerg_early", "store/imerg_early"),
    ("data/operational_sources", "store/operational_sources"),
]
SKIP = {"__pycache__", ".lock", "collection.lock", "automatic.lock"}


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sums, count, size = [], 0, 0
    with tarfile.open(OUT, "w:gz") as tar:
        for source, target in ITEMS:
            base = ROOT / source
            if not base.is_dir():
                raise SystemExit(f"Missing {source}; nothing written.")
            for path in sorted(base.rglob("*")):
                if not path.is_file() or path.name in SKIP or "__pycache__" in path.parts:
                    continue
                name = f"{target}/{path.relative_to(base).as_posix()}"
                data = path.read_bytes()
                sums.append(f"{hashlib.sha256(data).hexdigest()}  {name}")
                tar.add(path, arcname=name)
                count, size = count + 1, size + len(data)
        listing = ("\n".join(sums) + "\n").encode()
        info = tarfile.TarInfo("SHA256SUMS")
        info.size = len(listing)
        tar.addfile(info, io.BytesIO(listing))
    print(f"{count} files, {size / 1e6:.1f} MB -> {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1e6:.1f} MB compressed)")


if __name__ == "__main__":
    main()
