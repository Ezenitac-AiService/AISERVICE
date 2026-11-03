#!/usr/bin/env bash
# ==============================================================================
# install_git_hook.sh: Git post-commit 훅 설치 스크립트 (Feature 010)
# 비차단 백그라운드 모드 (기본) 및 --sync 동기 실행 모드 지원
# ==============================================================================
set -euo pipefail

IS_SYNC=false
for arg in "$@"; do
    if [ "$arg" = "--sync" ]; then
        IS_SYNC=true
    fi
done

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
HOOKS_DIR=$(git rev-parse --git-path hooks 2>/dev/null || echo "$REPO_ROOT/.git/hooks")

mkdir -p "$HOOKS_DIR"
HOOK_FILE="$HOOKS_DIR/post-commit"

if [ "$IS_SYNC" = true ]; then
cat <<'EOF' > "$HOOK_FILE"
#!/usr/bin/env bash
# ==============================================================================
# Auto-Changelog Agent post-commit hook (Synchronous Mode)
# ==============================================================================
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
LOG_DIR=$(git rev-parse --git-dir 2>/dev/null || echo "$REPO_ROOT/.git")
case "$LOG_DIR" in
    /*) ;;
    *) LOG_DIR="$REPO_ROOT/$LOG_DIR" ;;
esac

AGENT_SCRIPT=""
if [ -f "$REPO_ROOT/scripts/auto_changelog.py" ]; then
    AGENT_SCRIPT="$REPO_ROOT/scripts/auto_changelog.py"
elif [ -f "$REPO_ROOT/AISERVICE/scripts/auto_changelog.py" ]; then
    AGENT_SCRIPT="$REPO_ROOT/AISERVICE/scripts/auto_changelog.py"
else
    CURR="$REPO_ROOT"
    for _ in 1 2 3 4 5; do
        if [ -f "$CURR/scripts/auto_changelog.py" ]; then
            AGENT_SCRIPT="$CURR/scripts/auto_changelog.py"
            break
        elif [ -f "$CURR/AISERVICE/scripts/auto_changelog.py" ]; then
            AGENT_SCRIPT="$CURR/AISERVICE/scripts/auto_changelog.py"
            break
        fi
        PARENT=$(dirname "$CURR")
        [ "$PARENT" = "$CURR" ] && break
        CURR="$PARENT"
    done
fi

if [ -n "$AGENT_SCRIPT" ] && [ -f "$AGENT_SCRIPT" ]; then
    mkdir -p "$LOG_DIR" 2>/dev/null || true
    python3 -u "$AGENT_SCRIPT" --yes --sync >> "$LOG_DIR/auto_changelog.log" 2>&1
fi
EOF
echo "Successfully installed synchronous post-commit hook to $HOOK_FILE"
else
cat <<'EOF' > "$HOOK_FILE"
#!/usr/bin/env bash
# ==============================================================================
# Auto-Changelog Agent post-commit hook
# Non-blocking detached execution: 0ms prompt return (S1 / HOOK-1)
# ==============================================================================
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
LOG_DIR=$(git rev-parse --git-dir 2>/dev/null || echo "$REPO_ROOT/.git")
case "$LOG_DIR" in
    /*) ;;
    *) LOG_DIR="$REPO_ROOT/$LOG_DIR" ;;
esac

AGENT_SCRIPT=""
if [ -f "$REPO_ROOT/scripts/auto_changelog.py" ]; then
    AGENT_SCRIPT="$REPO_ROOT/scripts/auto_changelog.py"
elif [ -f "$REPO_ROOT/AISERVICE/scripts/auto_changelog.py" ]; then
    AGENT_SCRIPT="$REPO_ROOT/AISERVICE/scripts/auto_changelog.py"
else
    CURR="$REPO_ROOT"
    for _ in 1 2 3 4 5; do
        if [ -f "$CURR/scripts/auto_changelog.py" ]; then
            AGENT_SCRIPT="$CURR/scripts/auto_changelog.py"
            break
        elif [ -f "$CURR/AISERVICE/scripts/auto_changelog.py" ]; then
            AGENT_SCRIPT="$CURR/AISERVICE/scripts/auto_changelog.py"
            break
        fi
        PARENT=$(dirname "$CURR")
        [ "$PARENT" = "$CURR" ] && break
        CURR="$PARENT"
    done
fi

if [ -n "$AGENT_SCRIPT" ] && [ -f "$AGENT_SCRIPT" ]; then
    mkdir -p "$LOG_DIR" 2>/dev/null || true
    (
        python3 -u "$AGENT_SCRIPT" --yes >> "$LOG_DIR/auto_changelog.log" 2>&1
    ) >/dev/null 2>&1 & disown
fi
EOF
echo "Successfully installed non-blocking post-commit hook to $HOOK_FILE"
fi

chmod +x "$HOOK_FILE"
