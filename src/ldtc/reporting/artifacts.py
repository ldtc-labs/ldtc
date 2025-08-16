from __future__ import annotations

import json
import os
import time
from typing import List, Dict, Any, Tuple

from .timeline import render_paper_timeline
from .tables import write_sc1_table


def _read_audit(path: str) -> List[dict]:
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
    """Return (header_dict, index_of_header) for the last run_header in recs."""
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


def _extract_sc1_rows(
    recs: List[dict], eta_label: str | None, start_index: int
) -> List[Dict[str, Any]]:
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
    if not recs:
        return ""
    return str(recs[-1].get("hash", ""))


def _pubkey_hash_or_none(pubkey_path: str) -> str | None:
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
    """
    Emit a single verification bundle for a trial consisting of:
      - Paper-style timeline image (PNG+SVG)
      - SC1 table (if present) with columns: eta, delta, tau_rec, M_post, pass
      - JSON manifest with profile, seeds, Δt, method, CI coverage, and audit hash head

    Returns paths of generated artifacts.
    """
    os.makedirs(artifact_dir, exist_ok=True)
    recs = _read_audit(audit_path)
    if not recs:
        raise FileNotFoundError(f"No audit records at {audit_path}")
    header, header_idx = _extract_header(recs)
    eta = header.get("omega") or "trial"
    stamp = int(time.time())

    # 1) Timeline (PNG+SVG), scoped to this run only
    # Write a temporary segment audit containing records from the last run_header onward
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

    # 2) SC1 table from audit (if any sc1_result present)
    sc1_rows = _extract_sc1_rows(recs, eta_label=str(eta), start_index=header_idx)
    table_path = ""
    if sc1_rows:
        table_path = os.path.join(artifact_dir, f"sc1_table_{eta}_{stamp}.csv")
        write_sc1_table(sc1_rows, table_path)

    # 3) Manifest JSON (include config path and policy note; lock files read-only)
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
        # CI coverage is fixed by estimator at 95% via bootstrap percentiles
        "ci_coverage": 0.95,
        "audit_hash_head": _audit_hash_head(recs),
        # Indicator schema note (bit-layout and pubkey hash for verification tooling)
        "indicator_schema": {
            "mq_step_db": 0.25,
            "mq_bits": 6,
        },
        "pubkey_sha256": _pubkey_hash_or_none(
            os.path.join("artifacts", "keys", "ed25519_pub.pem")
        ),
        # Policy note required by manuscript/patent: raw LREG never leaves enclave
        "policy_note": "No raw LREG values or CI bounds are exported; figures derive only from M(dB) and audit events.",
        "artifacts": {
            "timeline_png": tpaths.get("png", ""),
            "timeline_svg": tpaths.get("svg", ""),
            "sc1_table_csv": table_path or None,
        },
    }
    # 3a) Snapshot the YAML config used (exact profile passed to CLI)
    cfg_snap_path = None
    try:
        cfg_src = header.get("config_path")
        if isinstance(cfg_src, str) and os.path.exists(cfg_src):
            base_name = os.path.basename(cfg_src)
            cfg_snap_path = os.path.join(
                artifact_dir, f"config_snapshot_{eta}_{stamp}_{base_name}"
            )
            # Copy without bringing along permissions
            with (
                open(cfg_src, "r", encoding="utf-8") as f_in,
                open(cfg_snap_path, "w", encoding="utf-8") as f_out,
            ):
                f_out.write(f_in.read())
    except Exception:
        cfg_snap_path = None

    # 3b) Write manifest
    manifest_path = os.path.join(artifact_dir, f"manifest_{eta}_{stamp}.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    # 3c) Policy notice file
    notice_path = os.path.join(artifact_dir, f"NOTICE_{eta}_{stamp}.txt")
    try:
        with open(notice_path, "w", encoding="utf-8") as nf:
            nf.write(
                "This repository enforces a derived-indicators-only policy: raw LREG values and CI bounds never leave the enclave.\n"
            )
    except Exception:
        notice_path = ""

    # Lock generated artifacts as read-only to "freeze" demo outputs
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
        # Best-effort on non-POSIX or restricted FS
        pass

    return {
        "timeline_png": tpaths.get("png", ""),
        "timeline_svg": tpaths.get("svg", ""),
        "sc1_table": table_path,
        "manifest": manifest_path,
        "config_snapshot": cfg_snap_path or "",
        "notice": notice_path or "",
    }
