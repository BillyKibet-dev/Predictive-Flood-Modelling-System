# Operational source persistence contract

Phase 2 is source-evidence storage, not an inference service. It reuses Phase 1's
collector replay, source contract, original timestamps, raw hashes and QC. It
never makes HTTP requests or loads a model. Apply the explicit migration before
running the manual importer; API startup performs neither operation.

## Tables and identities

Migration `005_operational_sources.sql` adds six tables in the explicitly chosen
existing PostgreSQL schema:

| Table | Purpose and identity |
| --- | --- |
| `operational_source_imports` | Per-invocation audit journal: STARTED then IMPORTED/REUSED/FAILED, import timestamps, optional prior journal link and safe error/result. Journal context and terminal outcomes cannot be rewritten. |
| `operational_collection_attempts` | One original request/capture, unique capture SHA-256. Stores explicit model/run, HTTP/transport/provider outcomes, receipt/source-storage timestamps, immutable references and complete capture/readiness documents. |
| `operational_source_receipts` | One raw-body receipt per attempt when bytes exist, with raw hash/length, relative reference, request/raw source identity and original provenance. Error/partial bodies are explicitly typed. No raw receipt is fabricated for a network failure with no body. |
| `operational_zone_quality` | One row per captured zone/attempt: requested/returned grid/elevation, source versus target quality, complete original interval/unit/missingness/reason document. Uses existing `zones` foreign keys. |
| `operational_forecast_snapshots` | One eligible original issue/target/policy/source identity. All snapshots select one explicit receipt/run. Status is immutable READY_AS_RECORDED, not a current-file-availability guarantee. |
| `operational_forecast_snapshot_zones` | Exactly eight QC memberships in a ready snapshot. Composite foreign keys bind snapshot/receipt and QC/receipt/zone, preventing mixed source cycles or unrelated QC. |

UUIDs for attempts, receipts, QC and snapshots are deterministic under a fixed
namespace and their verified content identities. The unique capture hash prevents
duplicate original attempts; UUIDs and SHA-256 both participate in conflict
checks. New actual requests with different capture timestamps are distinct
attempts even if their raw weather bytes happen to match. Repeated imports of
one capture add import history without duplicating its source graph.

`source_identity_sha256` hashes request identity plus raw digest. It groups
equivalent request/body evidence; it does not erase separate retrieval times.
Raw, capture and readiness references remain relative to an explicitly selected
local content-addressed store, allowing exact verified backup copies without
silently changing scientific identity. Database rows do not contain credentials,
private file paths or weather values invented to fill gaps.

## Eligibility and immutable facts

Unknown publication is NULL; it is never inferred from HTTP Date, valid time or
import time. UTC receipt/source-storage instants are copied from Phase 1; the
database journal has separate actual import times. Original documents retain
the original timestamp strings, units, source attribution and requested/returned
grids. PostgreSQL TIMESTAMPTZ stores the same instants; CLI UTC fields normalize
the display even if the server session uses Nairobi time.

An eligible source can have source quality PARTIAL and target quality PASSED:
initial accumulation nulls outside the required target remain missing. Neither
import nor replay upgrades source completeness. Failed providers, missing
required target data, late receipts, changed units/depth, inconsistent models
and unverified evidence cannot create a ready snapshot.

Database row/statement triggers reject UPDATE/DELETE/TRUNCATE of source facts.
Deferred snapshot triggers check all eight target-passing memberships and the
original model/run/policy/cutoff evidence at commit. Composite foreign keys and
uniqueness constraints prevent mixed receipts and duplicates. This enforces the
stored structural contract; it is not a substitute for raw-file QC or protection
against a privileged database administrator disabling constraints.

Current zone coordinates must match the captured catalogue at import/check.
There is no geographic reassignment. A later coordinate correction must be
reviewed/versioned rather than silently making an old snapshot describe a new
location.

## Transactions, concurrency and recovery

1. Verify raw/capture/readiness hashes, lengths, paths and reproducible QC offline.
2. Persist a STARTED import journal in its own small transaction. Invalid source
   files can have a failed import audit without a trusted collection-attempt row.
3. Acquire a transaction-scoped PostgreSQL advisory lock derived from schema and
   capture identity. Verify existing geography and any prior source graph.
4. Insert or verify/reuse attempt, raw receipt, all QC, optional ready snapshot
   and its eight memberships. Re-check local evidence before commit.
5. Commit the entire source graph and terminal journal result together. Deferred
   database checks must pass. A failed core transaction leaves no partial graph.

If the core write fails, a separate transaction finishes the journal as FAILED
where the database is available. Otherwise the response explicitly marks source
commit/failure auditing as unconfirmed and tries to save a local immutable
`persistence/sha256/...json` failure record. If local storage also fails, that
reference is null. No persistent failure record is falsely claimed.

A crash can leave STARTED history. Retry the same capture safely and optionally
link `--resume-import-id`; do not rewrite the old journal as though it completed
originally. If commit acknowledgement was lost, retry verifies/reuses the graph
instead of guessing whether the earlier transaction committed.

Immutable-record/hash conflicts are refused and audited. Do not fix conflicts
by editing metadata, receipt times or selected raw bytes. Investigate/restore the
approved original evidence or prepare a separately identified source capture.

## File availability and reads

The database stores references and provenance, not replicated raw weather blobs.
Use the CLI `--check-snapshot` before any later consumer uses a stored snapshot.
It reads the graph in a read-only transaction, verifies the saved objects and
recomputed QC, compares all stored evidence/memberships and checks geography.
Missing/corrupt objects produce effective readiness UNAVAILABLE. Historical
READY_AS_RECORDED facts remain unchanged. Exact original file restoration can
restore effective readiness without changing the source identity.

The local filesystem and database cannot be committed as one distributed
transaction. Files are verified before DB commit and again on explicit read;
later external file loss is still possible. No continuous watcher, automatic
repair, remote object replication or production durability SLA is claimed.

## Manual use and rollback

Commands, dry-run and fixtures are documented in
`docs/integration/shadow_collection_runbook.md`. Persistence exit 0 means an
IMPORTED/REUSED record or valid dry-run; a provider failure can be correctly
recorded with no eligible snapshot. Exit 1 is persistence/configuration failure;
exit 2 is unavailable snapshot/rejected dry-run. Original facts are never dated
using the current import/replay time.

Migration/rollback requires explicit invocation and an existing schema's own
zone catalogue. Migration 005 is additive, serialized and repeatable. Empty
rollback removes only its six tables and three functions. Nonempty rollback is
refused unless an operator explicitly approves data loss after archival. The
down script uses no CASCADE; external dependencies cause transactional rollback.
Selected v1 tables, artifacts and historical replay identities are never targets.

Native tests: `RUN_OPERATIONAL_SOURCE_POSTGRES_TESTS=1` enables disposable
`test_operational_<uuid>` schemas. Portable public fixtures come from Phase 1;
the suite forbids provider requests. There are no credentials/private database
rows in the fixtures. Exact local outcomes live in the Phase 2 implementation
and verification reports. Stop for review before a v2 dataset or inference work.
