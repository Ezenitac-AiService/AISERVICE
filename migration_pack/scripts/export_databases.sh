#!/usr/bin/env bash
# -*- coding: utf-8 -*-
# Python 구현을 공통 진입점으로 사용하는 POSIX wrapper입니다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/export_databases.py" "$@"
