#!/usr/bin/env bash
# -*- coding: utf-8 -*-
# AISERVICE Ubuntu native bootstrap entrypoint.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACK_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT="$(cd "${PACK_DIR}/.." && pwd)"
PYTHON="${PYTHON:-python3}"

SECRET_FILE="${AISERVICE_SECRET_FILE:-}"
REPORT_FILE="${AISERVICE_REPORT_FILE:-${PACK_DIR}/verification_report.json}"
DRY_RUN=false
YES=false
FORCE_DUMP=false
ARCHIVE=""
EXTRACT_TO=""

usage() {
    cat <<'EOF'
사용법: bootstrap_restore.sh --secret-file PATH [--dry-run] [--report PATH] [--yes]
       [--force-dump] [--archive PATH] [--extract-to PATH]
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --secret-file)
            [[ $# -ge 2 ]] || { echo "--secret-file에는 경로가 필요합니다" >&2; exit 1; }
            SECRET_FILE="$2"
            shift 2
            ;;
        --report)
            [[ $# -ge 2 ]] || { echo "--report에는 경로가 필요합니다" >&2; exit 1; }
            REPORT_FILE="$2"
            shift 2
            ;;
        --dry-run|-d) DRY_RUN=true; shift ;;
        --yes|-y) YES=true; shift ;;
        --force-dump) FORCE_DUMP=true; shift ;;
        --archive)
            [[ $# -ge 2 ]] || { echo "--archive에는 경로가 필요합니다" >&2; exit 1; }
            ARCHIVE="$2"
            shift 2
            ;;
        --extract-to)
            [[ $# -ge 2 ]] || { echo "--extract-to에는 경로가 필요합니다" >&2; exit 1; }
            EXTRACT_TO="$2"
            shift 2
            ;;
        --help|-h) usage; exit 0 ;;
        *) echo "알 수 없는 인자: $1" >&2; usage >&2; exit 1 ;;
    esac
done

if [[ -z "${SECRET_FILE}" ]]; then
    echo "--secret-file은 필수입니다. 비밀값은 외부 보호 경로에서 주입합니다." >&2
    exit 1
fi
if [[ "${EUID:-$(id -u)}" -ne 0 && "${DRY_RUN}" != true ]]; then
    echo "실제 복원은 root 권한으로 실행해야 합니다." >&2
    exit 1
fi

args=("${PYTHON}" "${SCRIPT_DIR}/bootstrap_restore.py"
    --project-root "${PROJECT_ROOT}"
    --pack-root "${PACK_DIR}"
    --secret-file "${SECRET_FILE}"
    --report "${REPORT_FILE}")
[[ "${DRY_RUN}" == true ]] && args+=(--dry-run)
[[ "${YES}" == true ]] && args+=(--yes)
[[ "${FORCE_DUMP}" == true ]] && args+=(--force-dump)
[[ -n "${ARCHIVE}" ]] && args+=(--archive "${ARCHIVE}")
[[ -n "${EXTRACT_TO}" ]] && args+=(--extract-to "${EXTRACT_TO}")

exec "${args[@]}"
