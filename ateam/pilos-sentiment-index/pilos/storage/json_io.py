import json
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
# 원본 수집물은 data/raw 아래에 저장한다.
DATA_DIR = BASE_DIR / "data" / "raw"


def to_data_relative(path) -> str:
    """절대경로를 data 디렉터리 기준 posix 상대경로로 바꾼다(예: .../data/raw → "raw").

    DB 에는 절대경로 대신 이 상대경로를 저장한다. data 밖 경로면 relative_to 가
    ValueError 를 내므로, 그 경우 원 경로를 posix 로 돌려준다.
    """
    p = Path(path).resolve()
    try:
        return p.relative_to(DATA_DIR.parent).as_posix()
    except ValueError:
        return p.as_posix()


def get_data_dir() -> Path:
    """데이터 디렉터리를 만들어(있으면 재사용) 경로를 반환한다."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def get_data_file(filename: str) -> Path:
    """data 디렉터리 아래 filename 경로를 반환한다."""
    return get_data_dir() / filename


def get_logs_dir() -> Path:
    """로그 디렉터리(data/raw/logs)를 만들어(있으면 재사용) 경로를 반환한다(P3-6)."""
    logs = DATA_DIR / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return logs


def get_comment_file(stock_name: str, target_date: str) -> Path:
    """백필 수집 결과 jsonl 파일 경로를 반환한다.

    예: data/until_20260601_삼성전자_comment.jsonl
    """
    filename = f"until_{target_date}_{stock_name}_comment.jsonl"
    return get_data_file(filename)


def get_incremental_comment_file(stock_name: str, created_date: str) -> Path:
    """증분 수집 결과 jsonl 파일 경로를 반환한다(댓글 작성일 YYYYMMDD 기준으로 분리).

    예: data/from_20260729_삼성전자_comment.jsonl
    """
    filename = f"from_{created_date}_{stock_name}_comment.jsonl"
    return get_data_file(filename)

def atomic_write_json(path: Path, data) -> None:
    """data 를 path 에 원자적으로 쓴다(같은 디렉터리 임시파일 + os.replace, P0-2)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")   # 반드시 같은 디렉터리
    try:
        with os.fdopen(fd, mode="w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())   # 디스크까지 확정(전원 차단 대비)
        os.replace(tmp, path)      # Windows/POSIX 모두 원자적 교체
    except BaseException:
        Path(tmp).unlink(missing_ok=True)   # 실패 시 임시파일 정리
        raise


def _load_json(file_path: Path, default=None):
    """file_path 의 JSON 을 읽어 반환하고, 없거나 손상됐으면 default(P1-3)."""
    if not file_path.exists():
        return default
    try:
        with open(file_path, mode="r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError, OSError):
        logger.warning(f"체크포인트 손상 - default 사용: {file_path}")
        return default


# 종목별 수집 상태(재개 커서·증분 경계·백필 상태)는 storage/manifest 로 통합했다.
# 매니페스트 단일 파일에서 원자적으로 관리하므로 여기서 개별 체크포인트 파일을 두지 않는다.
