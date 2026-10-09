"""Manually triggers one prediction pipeline run.

Run with:  python -m src.scripts.run_pipeline
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.api.services.pipeline import pipeline  # noqa: E402


def main():
    print("Running prediction pipeline...")
    summary = pipeline.run()
    print(summary)


if __name__ == "__main__":
    main()
