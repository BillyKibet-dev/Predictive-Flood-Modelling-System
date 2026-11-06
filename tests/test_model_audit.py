"""Reproducible artefact inspection and unavailable evaluation-report behaviour."""
import hashlib
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import joblib

from src.api.routers import admin
from src.api.services.model_contract import FEATURE_COLUMNS
from src.api.utils.security import require_admin
from src.scripts.audit_model import audit_model, saved_notebook_evidence


def test_notebook_inspection_never_executes_code_and_marks_saved_metrics_unreproduced(tmp_path):
    path = tmp_path / "notebook.ipynb"
    path.write_text(json.dumps({"cells": [
        {"cell_type": "code", "source": ["!pip install never-run-this"], "outputs": []},
        {"cell_type": "code", "source": ["raise RuntimeError('must not execute')\nfeature_cols = ['temperature_2m']\nfeature_cols.append(sm_col)"],
         "outputs": [{"text": ["Date range: 2016-01-01 00:00:00 - 2025-12-31 00:00:00\n"]}]},
        {"cell_type": "code", "source": ["def evaluate(): pass"], "outputs": [{"text": [
            "VALIDATION SET\nWeighted Recall: 0.9\nTEST SET\nWeighted Recall: 0.8\nWeighted F1-Score: 0.7\nAUC-ROC (weighted): 0.85\n"]}]},
    ]}), encoding="utf-8")
    evidence = saved_notebook_evidence(path)
    assert evidence["feature_list_in_code"] == ["temperature_2m"]
    assert evidence["saved_merged_date_range"] == ["2016-01-01", "2025-12-31"]
    assert evidence["saved_test_metrics"] == {"weighted_recall": 0.8, "weighted_f1": 0.7, "auc_roc_weighted": 0.85}
    assert evidence["metrics_reproduced"] is False
    assert evidence["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_audit_fingerprints_artifacts_and_detects_feature_mismatch(tmp_path):
    notebook = tmp_path / "notebook.ipynb"
    notebook.write_text('{"cells":[]}', encoding="utf-8")
    joblib.dump(SimpleNamespace(n_features_in_=9, classes_=[0, 1, 2, 3]), tmp_path / "flood_model_final.joblib")
    joblib.dump(SimpleNamespace(n_features_in_=9, data_min_=[0] * 9, data_max_=[1] * 9), tmp_path / "scaler_final.joblib")
    joblib.dump(list(FEATURE_COLUMNS), tmp_path / "feature_cols_final.joblib")
    report = audit_model(tmp_path, notebook)
    assert report["artifact_contract_valid"] is True
    assert report["audit_status"] == "review_required"
    assert report["prediction_context"]["location_specific"] is False
    assert len(report["artifacts"]) == 3
    joblib.dump(list(reversed(FEATURE_COLUMNS)), tmp_path / "feature_cols_final.joblib")
    report = audit_model(tmp_path, notebook)
    assert report["artifact_contract_valid"] is False and report["contract_errors"]


def test_missing_or_invalid_report_never_returns_fabricated_performance(tmp_path, monkeypatch):
    report_path = tmp_path / "model_report_final.json"
    monkeypatch.setattr(admin, "MODEL_REPORT_PATH", report_path)
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(role="admin")
    client = TestClient(app)
    for document in [None, "invalid json", "{}", "[]"]:
        if document is not None:
            report_path.write_text(document, encoding="utf-8")
        response = client.get("/admin/model-performance")
        assert response.status_code == 503
        assert response.json() == {"detail": "No valid model evaluation report is available"}
