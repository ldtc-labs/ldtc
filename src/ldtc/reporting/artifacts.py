"""End-to-end artifact bundling for verification runs.

[`bundle`][ldtc.reporting.artifacts.bundle] is the convenience entry
point used by `python -m ldtc.cli.main run` to turn a single audit log
into a complete, frozen artifact directory:

* a paper-style timeline (PNG and SVG) via
  [`render_paper_timeline`][ldtc.reporting.timeline.render_paper_timeline],
* an optional SC1 results CSV via
  [`write_sc1_table`][ldtc.reporting.tables.write_sc1_table],
* a manifest JSON describing the profile thresholds, the device
  pubkey hash, and the audit hash head, and
* a snapshot of the original config plus a short policy notice.

All produced files are then `chmod`-ed to read-only on POSIX-like
filesystems so a results directory is hard to mutate after the fact.

See Also:
    `paper/main.tex`: Reporting & Figures; Verification Pipeline.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Tuple

from .tables import write_sc1_table
from .timeline import render_paper_timeline


def _read_audit(path: str) -> List[dict]:
    """Read a JSONL audit file into a list of dicts.

    Args:
        path: Path to the audit JSONL file.

    Returns:
        List of parsed JSON objects. A missing file yields an empty
        list; malformed lines are skipped.
    """
    recs: List[dict] = []
    if not os.path.exists(path):
        return recs
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return recs


def _extract_header(recs: List[dict]) -> Tuple[Dict[str, Any], int]:
    """Extract the last `run_header` record.

    A single audit log can contain multiple runs; the bundler always
    scopes itself to the most recent `run_header` so that re-runs do not
    contaminate each other's artifacts.

    Args:
        recs: Parsed audit records.

    Returns:
        Tuple `(header_details, last_index)` or `({}, -1)` if no
        `run_header` is present.
    """
    last_idx = -1
    last_details: Dict[str, Any] = {}
    for i, r in enumerate(recs):
        if r.get("event") == "run_header":
            last_idx = i
            last_details = r.get("details", {}) or {}
    if last_idx >= 0:
        d = last_details
        return (
            {
                "profile_id": int(d.get("profile_id", 0)),
                "profile": "R*" if int(d.get("profile_id", 0)) == 1 else "R0",
                "config_path": d.get("config_path", None),
                "dt": float(d.get("dt", 0.0)),
                "window_sec": float(d.get("window_sec", 0.0)),
                "method": str(d.get("method", "")),
                "p_lag": int(d.get("p_lag", 0)),
                "mi_lag": int(d.get("mi_lag", 0)),
                "Mmin_db": float(d.get("Mmin_db", 0.0)),
                "epsilon": float(d.get("epsilon", 0.0)),
                "tau_max": float(d.get("tau_max", 0.0)),
                "seed_py": int(d.get("seed_py", 0)),
                "seed_np": int(d.get("seed_np", 0)),
                "omega": d.get("omega", None),
                "omega_args": d.get("omega_args", {}),
            },
            last_idx,
        )
    return {}, -1


def _extract_sc1_rows(recs: List[dict], eta_label: str | None, start_index: int) -> List[Dict[str, Any]]:
    """Extract SC1 results into table rows.

    Args:
        recs: Parsed audit records.
        eta_label: Label for the `Ω` stimulus that produced these
            results (e.g., `"power_sag"`).
        start_index: Only consider records from this index onward;
            typically the index of the most recent `run_header`.

    Returns:
        List of dict rows ready for
        [`write_sc1_table`][ldtc.reporting.tables.write_sc1_table]. Each
        row contains `eta`, `delta`, `tau_rec`, `M_post`, and `pass`.
    """
    rows: List[Dict[str, Any]] = []
    for r in recs[max(0, int(start_index)) :]:
        if r.get("event") == "sc1_result":
            d = r.get("details", {}) or {}
            row = {
                "eta": str(eta_label or ""),
                "delta": float(d.get("delta", 0.0)),
                "tau_rec": float(d.get("tau_rec", 0.0)),
                "M_post": float(d.get("M_post", 0.0)),
                "pass": bool(d.get("pass", False)),
            }
            rows.append(row)
    return rows


def _audit_hash_head(recs: List[dict]) -> str:
    """Return the last hash value in the provided records or empty string.

    Args:
        recs: Parsed audit records.

    Returns:
        The last record's `hash` field, or `""` if the input is empty.
    """
    if not recs:
        return ""
    return str(recs[-1].get("hash", ""))


def _pubkey_hash_or_none(pubkey_path: str) -> str | None:
    """Compute SHA-256 of a PEM public key file, if present.

    Args:
        pubkey_path: Filesystem path to a PEM-encoded public key.

    Returns:
        Hex-encoded SHA-256 string, or `None` if the file is missing or
        unreadable. Used to give consumers of the manifest a stable
        fingerprint of the device key without bundling the key itself.
    """
    try:
        import hashlib

        if not os.path.exists(pubkey_path):
            return None
        with open(pubkey_path, "rb") as f:
            data = f.read()
        return hashlib.sha256(data).hexdigest()
    except Exception:
        return None


def bundle(artifact_dir: str, audit_path: str) -> Dict[str, str]:
    """Create a verification artifact bundle from an audit log.

    Generates a paper-style timeline (PNG and SVG), an optional SC1 CSV
    table, a manifest JSON describing profile thresholds and artifact
    paths, an optional config snapshot, and a short policy notice. All
    produced files are then made read-only on POSIX-like filesystems so
    a results directory is hard to mutate after the fact.

    Args:
        artifact_dir: Output directory for generated artifacts. Created
            if missing.
        audit_path: Path to the JSONL audit log emitted by
            [`AuditLog`][ldtc.guardrails.audit.AuditLog].

    Returns:
        Dict with keys for produced files: `timeline_png`,
        `timeline_svg`, `sc1_table` (optional), `manifest`,
        `config_snapshot` (optional), and a policy `notice`.

    Raises:
        FileNotFoundError: If the audit log is missing or empty.
    """
    os.makedirs(artifact_dir, exist_ok=True)
    recs = _read_audit(audit_path)
    if not recs:
        raise FileNotFoundError(f"No audit records at {audit_path}")
    header, header_idx = _extract_header(recs)
    eta = header.get("omega") or "trial"
    stamp = int(time.time())

    seg_path = os.path.join(artifact_dir, f"audit_segment_{eta}_{stamp}.jsonl")
    try:
        with open(seg_path, "w", encoding="utf-8") as f:
            for r in recs[max(0, header_idx) :]:
                f.write(json.dumps(r, sort_keys=True) + "\n")
        base = os.path.join(artifact_dir, f"timeline_{eta}_{stamp}")
        tpaths = render_paper_timeline(
            seg_path,
            out_base_path=base,
            sidecar_csv=None,
            show=False,
            footer_profile=str(header.get("profile", "R0")),
            footer_audit_head=_audit_hash_head(recs),
        )
    finally:
        try:
            os.remove(seg_path)
        except Exception:
            pass

    sc1_rows = _extract_sc1_rows(recs, eta_label=str(eta), start_index=header_idx)
    table_path = ""
    if sc1_rows:
        table_path = os.path.join(artifact_dir, f"sc1_table_{eta}_{stamp}.csv")
        write_sc1_table(sc1_rows, table_path)

    manifest = {
        "version": 1,
        "profile_id": int(header.get("profile_id", 0)),
        "profile": header.get("profile", "R0"),
        "config_path": header.get("config_path", None),
        "dt": float(header.get("dt", 0.0)),
        "window_sec": float(header.get("window_sec", 0.0)),
        "method": header.get("method", ""),
        "p_lag": int(header.get("p_lag", 0)),
        "mi_lag": int(header.get("mi_lag", 0)),
        "Mmin_db": float(header.get("Mmin_db", 0.0)),
        "epsilon": float(header.get("epsilon", 0.0)),
        "tau_max": float(header.get("tau_max", 0.0)),
        "seed_py": int(header.get("seed_py", 0)),
        "seed_np": int(header.get("seed_np", 0)),
        "eta": eta,
        "eta_args": header.get("omega_args", {}),
        "ci_coverage": 0.95,
        "audit_hash_head": _audit_hash_head(recs),
        "indicator_schema": {
            "mq_step_db": 0.25,
            "mq_bits": 6,
        },
        "pubkey_sha256": _pubkey_hash_or_none(os.path.join("artifacts", "keys", "ed25519_pub.pem")),
        "policy_note": "No raw LREG values or CI bounds are exported; figures derive only from M(dB) and audit events.",
        "artifacts": {
            "timeline_png": tpaths.get("png", ""),
            "timeline_svg": tpaths.get("svg", ""),
            "sc1_table_csv": table_path or None,
        },
    }
    cfg_snap_path = None
    try:
        cfg_src = header.get("config_path")
        if isinstance(cfg_src, str) and os.path.exists(cfg_src):
            base_name = os.path.basename(cfg_src)
            cfg_snap_path = os.path.join(artifact_dir, f"config_snapshot_{eta}_{stamp}_{base_name}")
            with (
                open(cfg_src, "r", encoding="utf-8") as f_in,
                open(cfg_snap_path, "w", encoding="utf-8") as f_out,
            ):
                f_out.write(f_in.read())
    except Exception:
        cfg_snap_path = None

    manifest_path = os.path.join(artifact_dir, f"manifest_{eta}_{stamp}.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    notice_path = os.path.join(artifact_dir, f"NOTICE_{eta}_{stamp}.txt")
    try:
        with open(notice_path, "w", encoding="utf-8") as nf:
            nf.write(
                "This repository enforces a derived-indicators-only policy: "
                "raw LREG values and CI bounds never leave the enclave.\n"
            )
    except Exception:
        notice_path = ""

    try:
        for p in [
            tpaths.get("png", ""),
            tpaths.get("svg", ""),
            table_path,
            manifest_path,
            cfg_snap_path,
            notice_path,
        ]:
            if p:
                os.chmod(p, 0o444)
    except Exception:
        pass

    return {
        "timeline_png": tpaths.get("png", ""),
        "timeline_svg": tpaths.get("svg", ""),
        "sc1_table": table_path,
        "manifest": manifest_path,
        "config_snapshot": cfg_snap_path or "",
        "notice": notice_path or "",
    }
