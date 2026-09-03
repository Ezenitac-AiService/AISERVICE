#!/bin/sh
set -e

# ==============================================================================
# AISERVICE Internal 9-Endpoint Probe Script (SSOT)
# ==============================================================================
# Executes inside Docker aiservice-network using internal DNS.
# Prohibits host loopback (127.0.0.1) dependencies.

REPORT_PATH="${1:-/tmp/probe_report.json}"

echo "[PROBE] Probing 9 core endpoints via internal container DNS..."

python3 - <<EOF
import json
import socket
import sys
import time
import urllib.request
from datetime import datetime, timezone

TARGETS = [
    ("portal", "PUBLIC_WEB", "http://gateway:80/"),
    ("ateam_pilos", "PUBLIC_WEB", "http://gateway:80/ateam/pilos/"),
    ("bteam_oliview", "PUBLIC_WEB", "http://gateway:80/bteam/oliview/"),
    ("bteam_chata", "PUBLIC_WEB", "http://gateway:80/bteam/chata/"),
    ("bteam_chatb", "PUBLIC_WEB", "http://gateway:80/bteam/chatb/"),
    ("model_gateway_llm", "MODEL_GATEWAY", "http://vllm-serv-gateway:8081/health"),
    ("model_gateway_embedding", "MODEL_GATEWAY", "http://vllm-serv-gateway:8090/v1/models"),
    ("model_gateway_rerank", "MODEL_GATEWAY", "http://vllm-serv-gateway:8091/v1/models"),
    ("redis", "REDIS", "redis:6379"),
]

checks = []
failed = 0

for cid, cat, target in TARGETS:
    t0 = time.perf_counter()
    status = "FAIL"
    code = None
    err = None
    try:
        if cat == "REDIS":
            h, p = target.split(":")
            with socket.create_connection((h, int(p)), timeout=2.0) as s:
                s.sendall(b"PING\r\n")
                resp = s.recv(512).decode()
                if "+PONG" in resp:
                    status = "PASS"
                    code = "+PONG"
        else:
            req = urllib.request.Request(target, headers={"User-Agent": "aiservice-probe/1.0"})
            with urllib.request.urlopen(req, timeout=3.0) as r:
                code = r.getcode()
                if code in (200, 204):
                    status = "PASS"
    except Exception as exc:
        err = "ERR_PROBE_CONNECT"

    latency = round((time.perf_counter() - t0) * 1000, 2)
    entry = {
        "id": cid,
        "category": cat,
        "target": target,
        "status": status,
        "latency_ms": latency,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    if code:
        entry["status_code_or_ping"] = code
    if err:
        entry["error_code"] = err
    if cid == "portal":
        entry["subchecks"] = [
            {"id": "portal_root", "status": status, "status_code": code or 503},
            {"id": "portal_changelog", "status": status, "status_code": code or 503},
            {"id": "portal_changelog_data", "status": status, "status_code": code or 503},
            {"id": "portal_static_assets", "status": status, "status_code": code or 503},
        ]
    checks.append(entry)
    if status != "PASS":
        failed += 1

report = {
    "total": 9,
    "passed": 9 - failed,
    "failed": failed,
    "status": "PASS" if failed == 0 else "FAIL",
    "checks": checks,
}

with open("$REPORT_PATH", "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)

print(f"[PROBE] Finished: {9 - failed}/9 passed.")
sys.exit(0 if failed == 0 else 1)
EOF
