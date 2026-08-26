#!/usr/bin/env bash
# ==============================================================================
# vllm_serv: Seed Pack 안전 복원 및 압축 해제 고도화 스크립트 (unpack_seed.sh)
# 멀티 포맷(.tar.gz & .zip) 동적 자동 감지, 비파괴형(-k/-n) 덮어쓰기 방지,
# CLI 옵션 파싱(-i, -t, -f, --verify-only, --run-setup), 사전/사후 무결성 검증
# ==============================================================================

set -eo pipefail

COLOR_GREEN='\033[0;32m'
COLOR_YELLOW='\033[1;33m'
COLOR_RED='\033[0;31m'
COLOR_CYAN='\033[0;36m'
COLOR_NC='\033[0m'

log_info() { echo -e "${COLOR_GREEN}[UNPACK INFO]${COLOR_NC} $1"; }
log_warn() { echo -e "${COLOR_YELLOW}[UNPACK WARN]${COLOR_NC} $1"; }
log_err()  { echo -e "${COLOR_RED}[UNPACK ERROR]${COLOR_NC} $1"; }
log_step() { echo -e "\n${COLOR_CYAN}====================================================${COLOR_NC}\n${COLOR_CYAN}▶ $1${COLOR_NC}\n${COLOR_CYAN}====================================================${COLOR_NC}"; }

show_help() {
    echo "사용법: $0 [OPTIONS] [ARCHIVE_FILE]"
    echo ""
    echo "vllm_serv 프로젝트의 Seed Pack 아카이브(.tar.gz 또는 .zip)를 안전하게 비파괴 복원합니다."
    echo ""
    echo "옵션:"
    echo "  -i, --input PATH          복원할 시드 팩 아카이브 경로 지정"
    echo "  -t, --target-dir PATH     압축 해제 목적지 디렉토리 지정 (기본값: 현 프로젝트 루트)"
    echo "  -f, --force-overwrite     기존 파일 강제 덮어쓰기 허용 (기본값: 비파괴 보존)"
    echo "      --verify-only         압축 해제 없이 사전 무결성 검증만 수행 후 종료"
    echo "      --run-setup           압축 해제 완료 후 ./setup.sh 자동 후속 구동"
    echo "  -h, --help                도움말 메시지 출력 후 종료"
    echo ""
    exit 0
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
    BASE_DIR="$SCRIPT_DIR"
elif [ -f "$SCRIPT_DIR/../pyproject.toml" ]; then
    BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
else
    BASE_DIR="$(pwd)"
fi
cd "$BASE_DIR"

INPUT_PATH=""
TARGET_DIR="$BASE_DIR"
FORCE_OVERWRITE=0
VERIFY_ONLY=0
RUN_SETUP=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--input)
            INPUT_PATH="$2"
            shift 2
            ;;
        -t|--target-dir)
            TARGET_DIR="$2"
            shift 2
            ;;
        -f|--force-overwrite)
            FORCE_OVERWRITE=1
            shift
            ;;
        --verify-only)
            VERIFY_ONLY=1
            shift
            ;;
        --run-setup)
            RUN_SETUP=1
            shift
            ;;
        -h|--help)
            show_help
            ;;
        -*)
            log_err "알 수 없는 옵션: $1"
            show_help
            ;;
        *)
            if [ -z "$INPUT_PATH" ]; then
                INPUT_PATH="$1"
            fi
            shift
            ;;
    esac
done

# Auto-detect input path if not explicitly provided
if [ -z "$INPUT_PATH" ]; then
    for candidate in "dist/vllm_serv_seed.tar.gz" "vllm_serv_seed.tar.gz" "dist/vllm_serv_seed.zip" "vllm_serv_seed.zip"; do
        if [ -f "$candidate" ]; then
            INPUT_PATH="$candidate"
            break
        fi
    done
fi

if [ -z "$INPUT_PATH" ] || [ ! -f "$INPUT_PATH" ]; then
    log_err "Seed Pack 아카이브 파일을 찾을 수 없습니다 (${INPUT_PATH:-입력값 없음})."
    log_err "사용법: ./scripts/unpack_seed.sh [-i vllm_serv_seed.tar.gz|zip]"
    exit 1
fi

# Convert input & target paths to absolute paths
if [[ "$INPUT_PATH" != /* ]]; then
    ABS_INPUT_PATH="$BASE_DIR/$INPUT_PATH"
else
    ABS_INPUT_PATH="$INPUT_PATH"
fi

if [[ "$TARGET_DIR" != /* ]]; then
    ABS_TARGET_DIR="$BASE_DIR/$TARGET_DIR"
else
    ABS_TARGET_DIR="$TARGET_DIR"
fi

mkdir -p "$ABS_TARGET_DIR"

log_step "⚡ vllm_serv Seed Pack 안전 압축 해제 구동"
log_info "프로젝트 루트: $BASE_DIR"
log_info "대상 아카이브: $ABS_INPUT_PATH"
log_info "목적지 디렉토리: $ABS_TARGET_DIR"

# 1. Format Detection (Extension & File Header Magic)
FORMAT=""
HEADER_BYTES=""
if command -v od &> /dev/null; then
    HEADER_BYTES=$(od -N 4 -t x1 "$ABS_INPUT_PATH" 2>/dev/null | head -n 1 | sed 's/^[0-7]* //' | tr -d ' ')
fi

if [[ "$ABS_INPUT_PATH" == *.zip ]] || [[ "$HEADER_BYTES" == "504b0304"* ]]; then
    FORMAT="ZIP"
elif [[ "$ABS_INPUT_PATH" == *.tar.gz ]] || [[ "$ABS_INPUT_PATH" == *.tgz ]] || [[ "$HEADER_BYTES" == "1f8b"* ]]; then
    FORMAT="TAR_GZ"
else
    # Fallback to extension check
    if [[ "$ABS_INPUT_PATH" == *.zip ]]; then
        FORMAT="ZIP"
    else
        FORMAT="TAR_GZ"
    fi
fi

log_info "감지된 아카이브 포맷: $FORMAT"

# 2. Required Tools Check
if [ "$FORMAT" == "ZIP" ]; then
    if ! command -v unzip &> /dev/null && ! command -v python3 &> /dev/null; then
        log_err "'unzip' 또는 'python3' 명령어를 찾을 수 없습니다. zip 패키지를 설치하세요."
        exit 1
    fi
else
    if ! command -v tar &> /dev/null || ! command -v gzip &> /dev/null; then
        log_err "'tar' 또는 'gzip' 명령어를 찾을 수 없습니다."
        exit 1
    fi
fi

# 3. Pre-Unpack Integrity Verification
log_info "사전 무결성 검증 수행 중..."
if [ "$FORMAT" == "ZIP" ]; then
    if command -v unzip &> /dev/null; then
        ARCHIVE_LIST=$(unzip -l "$ABS_INPUT_PATH" 2>/dev/null || true)
    else
        ARCHIVE_LIST=$(python3 -m zipfile -l "$ABS_INPUT_PATH" 2>/dev/null || true)
    fi
else
    ARCHIVE_LIST=$(tar -tzf "$ABS_INPUT_PATH" 2>/dev/null || true)
fi

REQUIRED_ENTRIES=(
    "platform_profiles.json"
    "model_catalog.json"
    "gpu_detector.py"
    "start_server.sh"
    "ensure_models.py"
    "auxiliary_manager.py"
    "process_manager.py"
    "model_downloader.py"
    "benchmark_quality.py"
    "benchmark_context_window.py"
    "setup.sh"
    "make_seed_pack.sh"
)

MISSING_ENTRIES=()
for entry in "${REQUIRED_ENTRIES[@]}"; do
    if ! echo "$ARCHIVE_LIST" | grep "$entry" > /dev/null; then
        MISSING_ENTRIES+=("$entry")
    fi
done

if [ ${#MISSING_ENTRIES[@]} -gt 0 ]; then
    log_err "❌ [PRE-UNPACK FAIL] 필수 파일이 누락된 아카이브입니다: ${MISSING_ENTRIES[*]}"
    exit 1
fi
log_info "✓ [PRE-UNPACK PASS] 필수 구성 파일 전수 수록 검증 성공 (${#REQUIRED_ENTRIES[@]}개 항목)"

if [ "$VERIFY_ONLY" -eq 1 ]; then
    log_info "ℹ️ --verify-only 플래그 감지: 압축 해제를 진행하지 않고 무결성 검증 완결 후 정상 종료합니다."
    exit 0
fi

# 4. Existing Binary Preservation Check
if [ "$FORCE_OVERWRITE" -eq 0 ]; then
    if uv run python scripts/verify_wheel_binary.py --check-live 2>/dev/null; then
        log_info "ℹ️ [PRESERVED] 현재 환경의 기존 바이너리가 CUDA 가속 검증을 통과했습니다."
        log_info "   압축 해제 시 기존 유효 바이너리를 덮어쓰지 않고 최우선 보존합니다 (non-destructive flag)."
    fi
else
    log_warn "⚠️ --force-overwrite 플래그 활성화: 기존 바이너리 및 설정 파일을 강제 덮어씁니다."
fi

# 5. Extraction Execution
START_TIME=$(date +%s)
UNPACK_ERR=0

if [ "$FORMAT" == "ZIP" ]; then
    if command -v unzip &> /dev/null; then
        if [ "$FORCE_OVERWRITE" -eq 1 ]; then
            log_info "ZIP 강제 덮어쓰기 해제 중 (unzip -o -q)..."
            unzip -o -q "$ABS_INPUT_PATH" -d "$ABS_TARGET_DIR" 2>/dev/null || UNPACK_ERR=$?
        else
            log_info "ZIP 비파괴 압축 해제 중 (unzip -n -q)..."
            unzip -n -q "$ABS_INPUT_PATH" -d "$ABS_TARGET_DIR" 2>/dev/null || UNPACK_ERR=$?
        fi
    else
        log_info "ZIP 비파괴 압축 해제 중 (python3 zipfile fallback)..."
        python3 -c "
import zipfile, os, sys
archive = sys.argv[1]
target = sys.argv[2]
force = int(sys.argv[3])
with zipfile.ZipFile(archive, 'r') as z:
    for member in z.infolist():
        out_path = os.path.join(target, member.filename)
        if force or not os.path.exists(out_path):
            z.extract(member, target)
" "$ABS_INPUT_PATH" "$ABS_TARGET_DIR" "$FORCE_OVERWRITE" 2>/dev/null || UNPACK_ERR=$?
    fi
else

    if [ "$FORCE_OVERWRITE" -eq 1 ]; then
        log_info "TAR.GZ 강제 덮어쓰기 해제 중 (tar -xvpf)..."
        tar -xvpf "$ABS_INPUT_PATH" -C "$ABS_TARGET_DIR" 2>/dev/null || UNPACK_ERR=$?
    else
        log_info "TAR.GZ 비파괴 압축 해제 중 (tar -xvkpf)..."
        tar -xvkpf "$ABS_INPUT_PATH" -C "$ABS_TARGET_DIR" 2>/dev/null || UNPACK_ERR=$?
    fi
fi

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

if [ "$UNPACK_ERR" -ne 0 ] && [ "$UNPACK_ERR" -ne 2 ]; then
    log_err "Seed Pack 압축 해제 중 오류가 발생했습니다 (exit code: $UNPACK_ERR)."
    exit "$UNPACK_ERR"
fi

# 6. Post-Unpack Verification & Metrics
log_info "사후 무결성 검증 수행 중 ($ABS_TARGET_DIR)..."
POST_MISSING=0
for entry in "${REQUIRED_ENTRIES[@]}"; do
    if [ ! -f "$ABS_TARGET_DIR/$entry" ] && [ ! -f "$ABS_TARGET_DIR/config/$entry" ] && [ ! -f "$ABS_TARGET_DIR/src/core/$entry" ] && [ ! -f "$ABS_TARGET_DIR/scripts/$entry" ]; then
        log_warn "⚠️ 사후 복원 항목 확인 필요: $entry"
    fi
done

FILE_COUNT=$(find "$ABS_TARGET_DIR" -type f 2>/dev/null | wc -l | tr -d ' ')
RESTORED_SIZE=$(du -sh "$ABS_TARGET_DIR" 2>/dev/null | cut -f1 | tr -d ' ')

log_info "📊 [METRICS] 복원 완결 메트릭 -> 복원 파일: ${FILE_COUNT}개 | 총 용량: ${RESTORED_SIZE} | 소요 시간: ${ELAPSED}초"
log_info "✓ Seed Pack 안전 압축 해제 완결! (소요 시간: ${ELAPSED}초)"


# 7. Post-Action: --run-setup
if [ "$RUN_SETUP" -eq 1 ]; then
    log_step "🚀 --run-setup 옵션 감지: ./setup.sh 후속 구동을 시작합니다"
    if [ -f "$ABS_TARGET_DIR/setup.sh" ]; then
        bash "$ABS_TARGET_DIR/setup.sh"
    elif [ -f "$BASE_DIR/setup.sh" ]; then
        bash "$BASE_DIR/setup.sh"
    else
        log_err "setup.sh 스크립트를 찾을 수 없습니다."
        exit 1
    fi
else
    log_info "다음 단계: ./setup.sh 실행하여 환경 및 서버 설정을 완료하세요."
fi

exit 0
