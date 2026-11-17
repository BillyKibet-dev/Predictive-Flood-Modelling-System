"""Append-only, content-addressed local evidence. No database persistence."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STORE = PROJECT_ROOT / "data/operational_sources"
PROTECTED = tuple(PROJECT_ROOT / path for path in ("models", "data/model_v1", "data/live_source_audit", "src/modeling/v1"))


class EvidenceIntegrityError(ValueError):
    pass


def allowed_output(path):
    resolved = Path(path).resolve()
    if any(resolved == root.resolve() or resolved.is_relative_to(root.resolve()) for root in PROTECTED):
        raise ValueError("Historical sources, audit captures and model artifacts are protected")
    return resolved


def canonical_json(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


class LocalEvidenceStore:
    def __init__(self, root=DEFAULT_STORE):
        self.root = allowed_output(root)
        # A store cannot be an ancestor of a protected tree either.
        if any(root.resolve().is_relative_to(self.root) for root in PROTECTED):
            raise ValueError("Choose a dedicated evidence directory")

    def put(self, kind, content):
        if kind not in ("raw", "captures", "readiness", "persistence") or not isinstance(content, bytes):
            raise ValueError("Unsupported evidence object")
        digest = hashlib.sha256(content).hexdigest()
        suffix = ".bin" if kind == "raw" else ".json"
        relative = f"{kind}/sha256/{digest[:2]}/{digest}{suffix}"
        path = self.root / relative
        if not path.resolve().is_relative_to(self.root):
            raise EvidenceIntegrityError("Evidence path escapes storage root")
        path.parent.mkdir(parents=True, exist_ok=True)
        # Publish a complete fsynced object with an atomic no-clobber hard link.
        # A crash during writing cannot leave a partial object at its final hash.
        descriptor, temporary_name = tempfile.mkstemp(prefix=".evidence-", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != content:
                    raise EvidenceIntegrityError("Existing content-addressed evidence was changed")
        finally:
            temporary.unlink()
        return {"path": relative, "sha256": digest, "bytes": len(content)}

    def put_json(self, kind, value):
        return self.put(kind, canonical_json(value))

    def read(self, reference, kind):
        if kind not in ("raw", "captures", "readiness", "persistence"):
            raise EvidenceIntegrityError("Unsupported evidence reference kind")
        suffix = r"\.bin" if kind == "raw" else r"\.json"
        match = re.fullmatch(rf"{kind}/sha256/([0-9a-f]{{2}})/([0-9a-f]{{64}}){suffix}", reference["path"])
        if not match or match[1] != match[2][:2] or reference["sha256"] != match[2]:
            raise EvidenceIntegrityError("Invalid evidence reference")
        path = (self.root / reference["path"]).resolve()
        if not path.is_relative_to(self.root):
            raise EvidenceIntegrityError("Evidence reference escapes storage root")
        raw = path.read_bytes()
        if len(raw) != reference["bytes"] or hashlib.sha256(raw).hexdigest() != reference["sha256"]:
            raise EvidenceIntegrityError("Evidence hash/length mismatch")
        return raw

    def read_json(self, reference, kind):
        return json.loads(self.read(reference, kind))
