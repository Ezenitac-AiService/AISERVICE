"""수집(collection) 공통 상수 단일 소스.

크롤러와 실행기가 이 파일에서 필요한 상수만 import 한다.
저장 경로(DATA_DIR)는 계층 역전을 피하기 위해 storage(json_io)에 유지하고 여기 두지 않는다.
"""
from zoneinfo import ZoneInfo

# --- 시간대 ---
KST = ZoneInfo("Asia/Seoul")

# --- 크롤 엔진 ---
BASE_URL = "https://wts-cert-api.tossinvest.com/api/v4/comments"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36")
BASE_TIME = 0.5
REQUEST_TIMEOUT = 5      # 단일 요청 타임아웃(초)
MAX_RETRY = 3            # 요청 실패/일시 오류 시 재시도 횟수

# --- 종목 도메인 ---
# 개별 수집 대상(요청량이 많아 따로 돌린다)
SK_HYNIX_ID = "KR7000660001"
SAMSUNG_ID = "KR7005930003"

SUBJECTID_OTHER_WHITE_LIST = [
    "KR7035720002",
    "KR7035420009",
    "KR7373220003",
    "KR7247540008",
    "KR7068270008",
    "KR7005380001",
    "KR7005490008",
    "KR7034020008",
]

SUBJECTID_WHITE_LIST = [
    "KR7000660001",
    "KR7005930003",
    "KR7035720002",
    "KR7035420009",
    "KR7373220003",
    "KR7247540008",
    "KR7068270008",
    "KR7005380001",
    "KR7005490008",
    "KR7034020008",
]
STOCK_NAME = {
    "KR7000660001": "SK하이닉스",
    "KR7005930003": "삼성전자",
    "KR7035720002": "카카오",
    "KR7035420009": "NAVER",
    "KR7373220003": "LG에너지솔루션",
    "KR7247540008": "에코프로비엠",
    "KR7068270008": "셀트리온",
    "KR7005380001": "현대차",
    "KR7005490008": "포스코홀딩스",
    "KR7034020008": "두산에너빌리티",
}

# --- 백필 정책 ---
# --resume(백필 재개) 모드의 종료 하한 날짜. 이 날짜 00:00(KST) 이전 댓글을 만나면 멈춘다.
RESUME_UNTIL_DATE = "2026-04-30"
