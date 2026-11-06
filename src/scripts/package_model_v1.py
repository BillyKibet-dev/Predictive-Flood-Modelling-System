"""Verify and install selected native artifacts and historical inputs locally; no training."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from src.modeling.v1.contract import V1ArtifactError
from src.modeling.v1.runtime import ROOT, package_manifest, verify_files


def install_files(source: Path, destination: Path, files: dict) -> None:
    """Verify the complete source before copying; refuse to overwrite other bytes."""
    verify_files(source, files)
    for filename, metadata in files.items():
        target = destination / filename
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != metadata["sha256"]:
            raise V1ArtifactError("DESTINATION_CONTAINS_DIFFERENT_VERSION")
    destination.mkdir(parents=True, exist_ok=True)
    for filename in files:
        target = destination / filename
        if target.exists():
            continue
        with tempfile.NamedTemporaryFile(dir=destination, delete=False) as handle:
            temporary = Path(handle.name)
        try:
            shutil.copyfile(source / filename, temporary)
            blob = temporary.read_bytes()
            if (len(blob) != files[filename]["size_bytes"] or
                    hashlib.sha256(blob).hexdigest() != files[filename]["sha256"]):
                raise V1ArtifactError("INSTALLED_COPY_INTEGRITY_FAILURE")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    verify_files(destination, files)


def install_package(handoff: Path, source_dir: Path | None, model_dir: Path, data_dir: Path) -> dict:
    manifest = package_manifest()
    install_files(handoff / "model_v1", model_dir, manifest["files"])
    if source_dir:
        install_files(source_dir, data_dir, manifest["source_files"])
        source_manifest = {
            "schema_version": 1, "files": manifest["source_files"],
            "recipe_notebook_sha256": manifest["recipe_notebook_sha256"],
            "integrated_sha256": manifest["source_sha256"],
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "provenance": {"mode": "retrospective_research_replay",
                           "source_released_at": None, "original_release_times_known": False,
                           "weather": "ERA5-Seamless, original returned metadata retained",
                           "terrain_source_years": {"ndvi": 2023, "land_cover": 2021},
                           "terrain_extraction_recipe_verified": False,
                           "raw_hourly_independent_check": "cbd_2024.csv only; remaining zones use hash-verified daily aggregates"},
        }
        output = data_dir / "source_manifest.json"
        if not output.exists():
            output.write_text(json.dumps(source_manifest, indent=2) + "\n", encoding="utf-8")
    return {"model_version": manifest["model_version"], "model_files_verified": len(manifest["files"]),
            "source_files_verified": len(manifest["source_files"]) if source_dir else 0,
            "operational_promotion": False, "serialization": "native_json_only"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, default=ROOT / "codex-handoff")
    parser.add_argument("--source-dir", type=Path, help="Directory of original hash-matched research inputs")
    parser.add_argument("--model-dir", type=Path, default=ROOT / "models/nextday-proxy-v1")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/model_v1")
    args = parser.parse_args()
    try:
        print(json.dumps(install_package(args.handoff, args.source_dir, args.model_dir, args.data_dir), indent=2))
    except (OSError, ValueError, V1ArtifactError) as exc:
        parser.exit(1, f"Package installation refused: {type(exc).__name__}; verify source hashes and destination version.\n")


if __name__ == "__main__":
    main()
