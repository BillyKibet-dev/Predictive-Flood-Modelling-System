"""Profile the original CSVs and replay the v2 daily proxy evaluation offline."""
import argparse
import json
from pathlib import Path

from src.modeling.proxy_evaluation import PROVENANCE_PATH, evaluate_dataset
from src.scripts.audit_model import ARTIFACT_FILES

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chirps", type=Path, default=PROJECT_ROOT / "data/CHIRPS_Nairobi_2016_2026.csv")
    parser.add_argument("--weather", type=Path, default=PROJECT_ROOT / "data/nairobi_weather_2016_2026.csv")
    parser.add_argument("--model-dir", type=Path, default=PROJECT_ROOT / "models")
    parser.add_argument("--notebook", type=Path, default=PROJECT_ROOT / "notebooks/FloodHub.ipynb")
    parser.add_argument("--reference-fit", action="store_true", help="Refit the notebook recipe in memory; never export or deploy")
    parser.add_argument("--output", type=Path, help="Write a JSON report here instead of stdout")
    args = parser.parse_args()
    protected = {path.resolve() for path in (args.chirps, args.weather, args.notebook, PROVENANCE_PATH)}
    protected.update((args.model_dir / name).resolve() for name in ARTIFACT_FILES)
    if args.output and args.output.resolve() in protected:
        parser.error("Report output must not overwrite a source, notebook, provenance or model file")
    try:
        report = evaluate_dataset(args.chirps, args.weather, args.model_dir, args.notebook, args.reference_fit)
        document = json.dumps(report, indent=2, allow_nan=False) + "\n"
        if args.output:
            args.output.write_text(document, encoding="utf-8")
        else:
            print(document, end="")
    except (ValueError, OSError, TypeError, AttributeError) as exc:
        parser.exit(1, f"Proxy evaluation failed: {exc}\n")
    if report["frozen_artifact"]["status"] == "unavailable":
        parser.exit(1, "Report written; frozen model evaluation is unavailable in this environment.\n")


if __name__ == "__main__":
    main()
