# Cost and data access (Exp02)

**Cost: $0** (see `../BUDGET_LEDGER.md`). No inference was run; all trajectories are public, completed attempts.

## Sources (all public, anonymous)
| Resource | Access | Pin |
|---|---|---|
| SWE-bench Pro trajectories and per-instance eval outputs, `s3://scaleapi-results/swe-bench-pro/<run>/{traj,eval}/` | unsigned HTTPS `https://scaleapi-results.s3.amazonaws.com/` (no AWS CLI or account; the official README says an account is needed, but anonymous listing and GET work) | object ETags/MD5 + our SHA-256 in `data/manifests/bulk_keys.csv.done.csv`; full listing `data/manifests/s3_inventory.csv` (37,409 objects, listed 2026-10-26) |
| Task metadata, FAIL_TO_PASS / PASS_TO_PASS lists: HF `ScaleAI/SWE-bench_Pro`, split **v1** (731 tasks) | `huggingface_hub.snapshot_download`, unauthenticated | revision `2d52cb3df914a3fcf80c7f66738b3a88ae37fc50` |
| Official eval rule and official `eval_results.json` for 9 runs: `github.com/scaleapi/SWE-bench_Pro-os` | `git clone --depth 1` | `66f92766bba642462d4bbe5479e83f91f9211862` |
| Independent trajectory-shape analysis (for novelty comparison): `github.com/nilenso/swe-bench-pro-cost-token-time-analysis` | `git clone --depth 1` | `1169deb8892569c6b1ac4c51f2b09eb3b886ddef` |

## What was downloaded
13 runs × {`.traj`, `eval/<id>/_output.json`, `eval/<id>/_patch.diff`}: 27,006 files, 86.0 GB. All
files passed size checks and the MD5 checks where single-part ETags allow them (`status=ok` on 27,006/27,006).
Not downloaded: `gpt-5-codex-debug-oct22` (different setup), `gemini-…-nov17` (duplicate of oct22; its 5
smoke trajectories are byte-identical), and Gemini nov17 `.log/.yaml/.pred` files.

Smoke test first: 5 seeded tasks from 5 repositories × 15 runs (`data/manifests/smoke_keys.csv`) were
downloaded and their schema and config compared (`data/manifests/smoke_config_diff.tsv`) before the bulk download.

## Blockers encountered
None blocking. Notes: (1) Kimi-K2: the official eval folder is `kimi-k2-instruct-10132025`, but S3 only has
`kimi-paper` (50-call config). No 250-turn Kimi trajectories are public, so Kimi appears only in the
paper-50 cohort. (2) Haiku-4.5, GLM-4.5 and Gemini (oct22) have no official `eval_results.json`; their
labels are recomputed (validated by agreement on the 3 primary runs that have official labels; see PROVENANCE_DECISION).

Storage: data sits on scratch (`/share/gaise/qle3`, 30-day purge) and is re-downloadable with
`scripts/s3_download.py data/manifests/bulk_keys.csv`.
