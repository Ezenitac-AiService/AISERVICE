import hashlib
import json
import math
import re

from decimal import Decimal
from typing import Any, Mapping, Sequence

from pilos.analysis.signal_calibration import (
    SIGNAL_LEVEL_BANDS,
    SIGNAL_MEANING_NOTICE,
    SIGNAL_MOVING_AVERAGE_WINDOW,
    resolve_signal_level,
)
from pilos.dto.comment_signal_dto import (
    CommentSignalHistory,
    DailyCommentSignal,
)
from pilos.dto.llm_report_dto import (
    LlmMarketCommentary,
    LlmSignalEvidence,
    LlmSupplyState,
    ReportGenerationRequest,
    ReportGenerationResult,
)


MAX_LLM_MESSAGE_BYTES = 12_000

REPORT_NOTICE = (
    "현재 수급은 실제 개인투자자 체결량으로 계산한 관측값입니다. "
    f"{SIGNAL_MEANING_NOTICE}"
)

# 방향 문구는 supply_direction이 담당한다. 여기서는 방향 안에서의
# 상대 강도만 다루며 감성 어휘를 사용하지 않는다.
_SUPPLY_DIRECTION_LABELS = {
    "BUY": "매수 우위",
    "SELL": "매도 우위",
    "NEUTRAL": "수급 균형",
}

# 사용자에게 권장하는 방향 표현이다. 기존 '매수 우위' 표현을 금지하지는
# 않지만 프롬프트와 deterministic 요약은 쉬운 쪽을 쓴다. 방향 자체는
# 코드가 확정한 값이므로 LLM이 다시 추론하지 않는다.
#
# v13에서 과거형('오늘은 ~ 많았습니다')을 현재형으로 바꿨다. 수급 방향은
# 해당 거래일의 현재 상태를 보고하는 값인데 과거형은 이미 끝난 사건처럼
# 읽히기 때문이다.
_SUPPLY_DIRECTION_SENTENCES = {
    "BUY": "현재는 개인투자자의 매수가 더 많습니다",
    "SELL": "현재는 개인투자자의 매도가 더 많습니다",
    "NEUTRAL": "현재는 개인투자자의 매수와 매도가 비슷합니다",
}

# 문장 중간에 이어 붙일 때 쓰는 연결형이다.
_SUPPLY_DIRECTION_CLAUSES = {
    "BUY": "현재 개인투자자의 매수가 더 많고",
    "SELL": "현재 개인투자자의 매도가 더 많고",
    "NEUTRAL": "현재 개인투자자의 매수와 매도가 비슷하고",
}

# DB에 저장하는 등급 label은 그대로 두고 자연어 본문에서만 쓰는 표현이다.
# '70점으로 높음 편입니다' 같은 기계적인 문장을 없애기 위한 것이며,
# signal_level 값 자체는 바뀌지 않는다.
_LEVEL_NATURAL_TEXT = {
    "매우 높음": "매우 높은 편",
    "높음": "높은 편",
    "보통": "보통 수준",
    "중립": "보통 수준",
    "낮음": "낮은 편",
    "매우 낮음": "매우 낮은 편",
}


def describe_signal_level(signal_level: str | None) -> str | None:
    """등급 label을 본문에 쓸 자연어 표현으로 바꾼다."""
    if signal_level is None:
        return None

    return _LEVEL_NATURAL_TEXT.get(signal_level, f"{signal_level} 수준")


# signal_ma5를 부르는 기본 이름이다.
MOVING_AVERAGE_LABEL = f"직전 {SIGNAL_MOVING_AVERAGE_WINDOW}거래일 평균"

# 같은 값을 가리키는 허용 명칭이다. 문맥상 5거래일 창이 드러나면
# 표현은 자유롭게 고를 수 있다.
ALLOWED_MOVING_AVERAGE_LABELS = (
    MOVING_AVERAGE_LABEL,
    f"최근 {SIGNAL_MOVING_AVERAGE_WINDOW}거래일 평균",
    f"직전 {SIGNAL_MOVING_AVERAGE_WINDOW}일 평균",
    f"최근 {SIGNAL_MOVING_AVERAGE_WINDOW}일 평균",
    f"{SIGNAL_MOVING_AVERAGE_WINDOW}거래일 평균",
    f"{SIGNAL_MOVING_AVERAGE_WINDOW}일 평균",
    "최근 평균",
)

# 점수가 실제로 바뀌지 않았다고 주장하는 표현이다. v13은 '유지'라는
# 단어 자체를 막지 않는다. '높은 수준을 유지하고 있습니다'처럼 상태가
# 이어진다는 서술은 정상이기 때문이다. 대신 숫자 자체가 동일하다고
# 주장하는 경우만 실제 값과 대조한다.
_UNCHANGED_SCORE_PATTERN = re.compile(
    r"점수가\s*(?:그대로|동일|같)"
    r"|(?:어제|전날|전일|직전\s*거래일)\s*(?:와|과|하고)?\s*(?:는\s*)?"
    r"(?:완전히\s*)?(?:같은|동일한|똑같은)\s*점수"
    r"|점수\s*(?:에\s*)?변화가\s*없"
    r"|변동이\s*없"
    r"|그대로\s*유지(?:됐|되었|되고)"
    r"|동일한\s*점수"
)

# 변화량 서술 기준을 판정할 때 살펴볼 앞뒤 문맥 길이다.
# §9에 따라 앞 문맥은 같은 절 안으로 제한한다.
_CHANGE_PREFIX_WINDOW = 30
_CHANGE_SUFFIX_WINDOW = 14

SIGNAL_LEVEL_LABELS: tuple[str, ...] = tuple(
    label for _lower, _upper, label in SIGNAL_LEVEL_BANDS
)

# 강도 어간이다. 어미 변화는 자유이므로 완결형이 아니라 어간으로 둔다.
# 긴 어간부터 검사해야 "매우 낮"이 "낮"으로 잘못 축약되지 않는다.
_LEVEL_STEM_TO_LABEL: dict[str, str] = {
    "매우 높": "매우 높음",
    "매우 낮": "매우 낮음",
    "보통": "보통",
    "중립": "중립",
    "높": "높음",
    "낮": "낮음",
}
_LEVEL_STEMS = "|".join(
    re.escape(stem)
    for stem in sorted(_LEVEL_STEM_TO_LABEL, key=len, reverse=True)
)

# 강도 서술로 인정할 문맥이다. 등급 뒤에 "수준"이 붙거나 점수 바로
# 옆에서 서술될 때만 등급 표현으로 본다. 그래야
# "평균 55점보다 낮습니다" 같은 비교 문장을 재분류로 오인하지 않는다.
_LEVEL_WITH_NOUN_PATTERN = re.compile(
    rf"({_LEVEL_STEMS})(?:은|는|음|습니다|았|었)?\s*(?:수준|등급|편)"
)
_LEVEL_AFTER_SCORE_PATTERN = re.compile(
    r"\d+\s*점\s*(?:으로|이며|이고|입니다|은|는|이)\s*"
    rf"[^.]{{0,10}}?({_LEVEL_STEMS})"
)
_LEVEL_BEFORE_SCORE_PATTERN = re.compile(
    rf"({_LEVEL_STEMS})(?:은|는|음|습니다|았|었)?\s*\d+\s*점"
)

# 등급 서술 앞에 이 표지가 있으면 다른 값과의 비교이지 등급 재분류가
# 아니다. v12는 "평균과 비슷하게 높은 수준"처럼 비교를 쉬운 말로
# 풀어쓰도록 권장하므로 비교 문맥을 넓게 인정한다.
# '매우'를 뗀 표현은 같은 방향의 덜 정밀한 서술이므로 모순이 아니다.
# 반대 방향은 포함하지 않으므로 등급을 키우거나 뒤집는 것은 계속 막힌다.
_COARSER_LEVELS: dict[str, set[str]] = {
    "매우 높음": {"높음"},
    "매우 낮음": {"낮음"},
}

_LEVEL_PREFIX_WINDOW = 16
_COMPARISON_MARKERS = (
    "보다",
    "비교",
    "비슷",
    "대비",
    "만큼",
    "가깝",
    "같은 수준",
    "차이",
)

# 변화량 서술이다. "포인트"는 점수 차이에만 쓰이므로 값을 바로 검증한다.
_CHANGE_PATTERN = re.compile(r"(\d+)\s*(?:포인트|p)")

# v12는 "어제보다 15점 낮아졌습니다" 같은 쉬운 표현을 권장한다. 이때의
# "점"은 변화량이므로 값과 방향을 검증해야 한다. 다만 "어제 80점"처럼
# 절대값을 말하는 경우와 구분해야 하므로 '보다'나 '대비'가 붙은 경우만
# 변화량으로 본다.
_CHANGE_WITH_BASELINE_PATTERN = re.compile(
    r"(?:어제|전날|전일|직전\s*거래일)\s*(?:보다|대비)\s*(?:는\s*)?"
    r"(\d+)\s*(?:점|포인트|p)"
)

_UPWARD_WORDS = (
    "상승", "올랐", "올라", "오르", "증가", "급등", "회복", "반등", "높아",
)
_DOWNWARD_WORDS = (
    "하락", "내렸", "내려", "떨어", "감소", "급감", "축소", "낮아", "줄어",
)

# 변화량 뒤의 서술을 볼 때 다음 절까지 넘어가지 않도록 끊는 지점이다.
_CLAUSE_BOUNDARY_PATTERN = re.compile(r"지만|하지만|다만|반면|그러나|[,.]")

# 비교 방향을 나타내는 서술어다.
_ABOVE_WORDS = ("웃도", "웃돌", "상회", "넘어", "넘는", "초과", "높")
_BELOW_WORDS = ("못 미", "미치지", "하회", "밑도", "밑돌", "낮", "아래")

# signal_ma5 자체의 시계열 변화는 evidence에 없다.
_MOVING_AVERAGE_TREND_PATTERN = re.compile(
    r"평균[^.]{0,6}?(상승|하락|올랐|올라|내렸|내려|"
    r"강화|약화|증가|감소|개선|악화)"
)

# 변화 표현의 대상이 댓글 수급 신호가 아닌 경우다. 이 대상들의 시계열은
# evidence에 없으므로 사실을 확인할 수 없다.
_TREND_SUBJECT_BLOCKLIST = (
    "매수세",
    "매도세",
    "매수 심리",
    "매도 심리",
    "투자 심리",
    "투자자 심리",
    "시장 흐름",
    "시장 분위기",
    "시장",
    "주가",
    "주식",
    "증시",
    "거래량",
)
_TREND_TERM_PATTERN = re.compile(
    r"(상승세|하락세|강화|약화|회복|강해|약해|살아나|위축|개선|악화)"
)
_TREND_SUBJECT_WINDOW = 20

# 주가나 시장을 대상으로 방향을 말하는 표현이다.
_PRICE_DIRECTION_PATTERN = re.compile(
    r"(주가|주식|증시|시장|주식시장|종목가|가격|주식가격)[^.]{0,10}?"
    r"(상승|하락|반등|조정|급등|급락|오를|오르|내릴|내리|상승세|하락세)"
)

# 미래를 말하는 표현이다. evidence는 당일과 과거 값만 담는다.
_FUTURE_OUTLOOK_PATTERN = re.compile(
    r"향후|앞으로|당분간|머지않아|다음\s*(?:거래일|주|달|분기)"
    r"|(?:예상|전망|기대)(?:됩니다|된다|되며|하고|이|을|합니다|입니다)"
    r"|(?:이어질|지속될|계속될|오를|내릴|상승할|하락할|반등할|약화될|강화될)"
    r"|가능성(?:이|은|도)?\s*(?:높|있|큽|커|보)"
)

# 원인을 말하는 표현이다. evidence에는 변화의 원인이 없다.
_CAUSAL_PATTERN = re.compile(
    r"때문|덕분|영향으로|영향을 받아|여파|탓(?:에|으로)|이유로"
    r"|배경(?:에|으로)|기대감(?:에|으로|이)|우려(?:에|로)"
)

# 투자 행동을 권유하는 표현이다.
FORBIDDEN_ADVICE_EXPRESSIONS = (
    "매수 추천",
    "매도 추천",
    "매수 신호",
    "매도 신호",
    "추천합니다",
    "추천드립니다",
    "목표가",
    "매수하기 좋",
    "매도하기 좋",
    "비중 확대",
    "비중 축소",
    "진입 시점",
    "손절",
    "익절",
)

# 대상이 생략돼도 주가·시장 방향을 뜻하는 관용 표현이다. 댓글 수급
# 신호를 가리킬 수 없는 어휘이므로 대상과 무관하게 막는다.
FORBIDDEN_PRICE_EXPRESSIONS = (
    "상승 신호",
    "하락 신호",
    "상승 압력",
    "하락 압력",
    "상승 가능성",
    "하락 가능성",
    "반등 가능성",
    "주가 반등",
    "주가 조정",
)

# v12에서 hard rejection 대상에서 뺀 문체 어휘다. 단어가 있다는 이유만으로
# 보고서를 폐기하지 않는다. 실제 숫자 관계와 모순되는지는 아래 사실
# 검증들이 따로 판정한다. 프롬프트로 사용을 줄이도록 유도만 한다.
SOFT_STYLE_EXPRESSIONS = (
    "강세",
    "약세",
    "회복세",
    "유지",
    "상회",
    "하회",
    "웃돌",
    "못 미치",
    "종합적으로",
)

# 모델 결과를 확률로 바꾸어 표현하는 어휘다.
FORBIDDEN_PROBABILITY_EXPRESSIONS = (
    "감성 확률",
    "긍정 확률",
    "부정 확률",
    "상승 확률",
    "하락 확률",
    "미래 수급",
    "수급 예측",
    "주가 예측",
)

# signal_ma5를 다른 통계처럼 부르는 표현이다. 값의 의미가 달라지므로
# 문체가 아니라 사실 문제다.
FORBIDDEN_MOVING_AVERAGE_ALIASES = (
    "과거 평균",
    "과거 분포",
    "과거의 평균",
    "중간 수준",
    "중앙값",
    "이동평균",
    "이동 평균",
    "평균 신호 수준",
    "직전 거래일 평균",
    "전일 평균",
    "누적 평균",
    "전체 평균",
)

# 이전 등급과 이전 수급 방향이 evidence에 없으므로 전환은 확인할 수 없다.
_REGIME_CHANGE_PATTERN = re.compile(
    r"(수준|등급|신호|국면|추세|구간)[^.]{0,8}?전환"
    r"|(매수|매도)(?:\s*우위)?(?:로|으로)\s*(?:전환|돌아섰|바뀌었|바뀌)"
    r"|(매수|매도)\s*전환"
)

# 수급 방향에 점수를 붙여 두 지표를 하나로 섞은 표현이다. 수급 방향은
# 체결량 관측값이고 댓글 신호는 별개의 0~100 점수이므로 사실 오류다.
_DIRECTION_SCORE_CONFUSION_PATTERN = re.compile(
    r"(?:매수|매도)\s*(?:우위|우세)[^.]{0,6}?\d+\s*점"
    r"|(?:매수|매도)(?:가|는|이)?\s*(?:더\s*)?많[^.]{0,6}?\d+\s*점"
)

# 수급 방향을 쉬운 말로 쓴 표현이다. v12 권장 문체를 반전 검사에 포함한다.
_DIRECTION_MORE_PATTERN = re.compile(
    r"(매수|매도)\s*(?:가|를|는|쪽이|쪽|세가)?\s*(?:더\s*)?(?:많|우세|우위)"
)

# 수급 강도의 시계열은 evidence에 없다. 현재 방향만 알 뿐 이전 방향이나
# 강도 변화를 알 수 없으므로 '매도 압력이 커졌다'는 만들어낸 사실이다.
_SUPPLY_PRESSURE_CHANGE_PATTERN = re.compile(
    r"(?:매수|매도)\s*(?:압력|강도|세)[^.]{0,10}?"
    r"(?:커졌|커지|강화|강해|세졌|완화|약화|약해|줄었|줄어|낮아|높아|"
    r"확대|축소|늘었|늘어)"
    r"|(?:매수|매도)\s*(?:압력|강도|세)\s*(?:이|가)?\s*(?:더\s*)?(?:강|약)"
)

# signal_ma5를 주어로 두고 현재 점수와 비교하는 표현이다. 이때는 비교
# 방향이 뒤집히므로 별도로 판정해야 한다. "평균 81점이 현재보다 낮다"는
# 실제로는 "현재가 평균보다 낮다"의 반대 주장이다.
_AVERAGE_AS_SUBJECT_PATTERN = re.compile(
    r"평균[^.]{0,12}?(\d+)\s*점\s*(?:이|은|는|가)\s*"
    r"(?:오늘|현재|지금|당일)[^.]{0,10}?(높|낮)"
)

# 직전 거래일의 점수를 가리키는 표현이다. 변화량을 여기에 적으면 값의
# 역할이 뒤바뀐다.
_PREVIOUS_SCORE_MENTION_PATTERN = re.compile(
    r"(?:직전\s*거래일|어제|전날|전일)\s*(?:의)?\s*(\d+)\s*점"
)

REPORT_SYSTEM_PROMPT = (
    "당신은 일반 사용자가 숫자를 쉽게 이해하도록 돕는 데이터 해설자입니다. "
    "애널리스트가 아니라 설명자입니다. 이미 계산이 끝난 값을 사용자가 한 번 "
    "읽고 이해할 수 있는 한국어로 풀어서 전달하는 것이 전부입니다. "

    "[전달할 내용] 다음 네 가지를 자연스럽게 이어 설명하세요. "
    "개인투자자의 매수·매도 중 현재 어느 쪽이 더 많은지, 현재 댓글 수급 "
    "신호의 점수와 등급, 직전 거래일과 비교한 변화, 그리고 최근 5거래일 "
    "평균과 비교한 현재 위치입니다. "

    "[표현 지침] 딱딱한 금융 보고서 문체보다 쉬운 말을 우선하세요. "

    "수급 방향은 현재 상태 보고형으로 씁니다. BUY는 '현재는 개인투자자의 "
    "매수가 더 많습니다', SELL은 '현재는 개인투자자의 매도가 더 "
    "많습니다'처럼 현재형으로 쓰세요. '오늘은 ~ 많았습니다'처럼 이미 끝난 "
    "사건으로 서술하지 마세요. "

    "등급은 자연스러운 한국어로 풀어 씁니다. '높음 편'이 아니라 '높은 편', "
    "'매우 낮음 편'이 아니라 '매우 낮은 편', '보통'은 '보통 수준'으로 "
    "쓰세요. "

    "비교도 마찬가지입니다. '상회', '하회', '웃돌다', '못 미치다' 대신 "
    "'최근 5일 평균보다 높습니다', '최근 평균과 비교하면 낮은 편입니다', "
    "'어제보다 15점 낮아졌습니다'처럼 쓸 수 있습니다. "

    "문장을 매번 같은 순서와 같은 표현으로 반복할 필요는 없습니다. 어떤 "
    "수치를 먼저 말할지, 무엇을 생략할지 직접 고르세요. 변화량으로 관계가 "
    "드러나면 직전 거래일의 절대 점수는 생략해도 됩니다. "

    "[사실 계약] 표현은 자유롭지만 사실과 숫자 관계는 절대 바꾸지 "
    "않습니다. "

    "1. 입력 JSON에 없는 사실, 원인, 미래 전망을 만들지 않습니다. 왜 "
    "변했는지는 입력에 없으므로 추론하지 않습니다. 주가, 거래량, 체결량, "
    "매수·매도 압력, 향후 가능성, 투자 추천은 입력에 없는 정보입니다. "

    "2. 수급 방향은 코드가 실제 개인투자자 체결량으로 확정한 값입니다. "
    "다시 추론하지 말고 주어진 방향을 쉬운 말로 옮기기만 하세요. BUY를 "
    "매도로, SELL을 매수로 쓰면 사실 오류입니다. 또한 지금 방향만 알 뿐 "
    "이전 방향이나 수급 강도의 시계열은 입력에 없으므로 '매도 압력이 "
    "커졌다', '매수세가 강화됐다'처럼 강도 변화를 만들지 마세요. "

    "3. 수급 방향과 댓글 신호 점수는 서로 다른 지표입니다. '매수 우위가 "
    "28점', '매도 우위가 62점'처럼 방향에 점수를 붙이지 마세요. 방향은 "
    "방향대로, 점수는 점수대로 말합니다. "

    "4. signal_level은 이미 결정된 등급입니다. '낮음'을 '매우 낮음'으로 "
    "바꾸지 않습니다. 등급을 생략해도 되지만, 말한다면 주어진 등급이어야 "
    "합니다. "

    "5. signal_change는 현재 신호와 직전 거래일 신호의 차이입니다. "
    "'N포인트'로 적을 때는 직전 거래일이 기준임을 밝히세요. signal_ma5를 "
    "변화량의 기준으로 삼지 않습니다. "

    f"6. signal_ma5는 '{MOVING_AVERAGE_LABEL}', "
    f"'{ALLOWED_MOVING_AVERAGE_LABELS[1]}', 문맥이 분명하면 '최근 평균'처럼 "
    "5거래일 창이 드러나는 이름으로 부릅니다. '과거 평균', '중간 수준', "
    "'이동평균', '직전 거래일 평균'은 다른 통계를 뜻하므로 쓰지 않습니다. "

    "7. 평균은 비교 기준이지 변화의 대상이 아닙니다. signal_ma5 자체가 "
    "올랐는지 내렸는지는 입력에 없으므로 '평균보다 상승했다', '평균이 "
    "낮아졌다'처럼 쓰지 않습니다. 전일 비교와 평균 비교는 분리해서 "
    "말하세요. "

    "8. '강해졌다', '약해졌다', '회복했다' 같은 변화 표현은 댓글 수급 "
    "신호를 대상으로 할 때만 씁니다. '매수세가 강해졌다', '투자 심리가 "
    "회복됐다', '주가 상승세'처럼 다른 대상에 붙이지 않습니다. 그 "
    "시계열은 입력에 없습니다. "

    "9. 직전 거래일의 수급 방향과 등급은 입력에 없습니다. '매수로 "
    "전환됐다', '매도로 돌아섰다', '등급이 전환됐다'고 쓰지 않습니다. "
    "'높은 수준을 유지하고 있습니다'처럼 상태가 이어진다는 서술은 써도 "
    "되지만, 점수가 실제로 바뀐 날에 '점수가 그대로다', '어제와 같은 "
    "점수다'라고 쓰면 사실 오류입니다. "

    "10. 각 숫자의 역할을 섞지 마세요. 현재 점수, 직전 거래일 점수, "
    "변화량, 5거래일 평균은 서로 다른 값입니다. 변화량을 직전 거래일의 "
    "점수인 것처럼 쓰지 말고, 평균을 현재 점수처럼 쓰지 마세요. "

    "[설명 방식] 현재 신호, 직전 거래일, 5거래일 평균 사이의 관계를 한 "
    "흐름으로 묶으세요. 전일보다 올랐지만 평균에는 미치지 못하는 경우처럼 "
    "방향이 엇갈리면 '하지만', '다만', '반면'으로 두 관계를 함께 보여주고 "
    "하나로 단순화하지 마세요. "

    "수급 방향과 신호 강도가 엇갈리는 조합은 모순이 아닙니다. 매도가 더 "
    "많은 날에 신호가 매우 높은 상황도 그대로 설명하면 되며, 이상하다고 "
    "쓸 필요가 없습니다. 다만 투자자의 의도나 심리를 추측하지 마세요. "

    "변화 폭이 크면 '크게', '뚜렷하게' 같은 강조를 써도 됩니다. 숫자 "
    "관계가 뒷받침하면 됩니다. "

    "market_commentary는 2~4문장입니다. conclusion은 새 분석을 더하지 말고 "
    "본문에서 가장 중요한 관계 하나를 완전한 한 문장으로 압축하세요. "
    "'높음', '매도' 같은 단어 하나만 반환하면 안 됩니다. "

    "숫자는 입력에 있는 값만 씁니다. 새로 계산하지 말고 백분율 기호도 "
    "쓰지 마세요. actual_supply_index의 소수 값은 본문에 적지 말고 방향 "
    "설명으로만 쓰세요. "

    "내부 모델 정보, <think>, 마크다운과 부가 설명 없이 "
    "market_commentary와 conclusion 두 키만 가진 JSON 객체를 반환하세요."
)


def _finite_float(value: Any, field_name: str) -> float:
    """JSON과 Pydantic에서 안전하게 다룰 수 있는 유한 실수로 변환한다."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{field_name}는 유한한 숫자여야 합니다.")

    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{field_name}는 유한한 숫자여야 합니다.")
    return converted


def classify_supply_state(actual_supply_index: Any) -> LlmSupplyState:
    """실제 수급지수의 부호와 절댓값으로 화면용 강도 문구를 결정한다."""
    if actual_supply_index is None:
        return LlmSupplyState(
            actual_supply_index=0.0,
            active_regime="neutral",
            supply_direction="NEUTRAL",
            state_label="수급 확인 대기",
            state_description="현재 개인투자자의 수급 데이터 확인 대기 중입니다.",
        )
    index = _finite_float(actual_supply_index, "actual_supply_index")
    magnitude = abs(index)

    if index == 0:
        regime = "neutral"
        supply_direction = "NEUTRAL"
        label = "수급 균형"
    else:
        regime = "positive" if index > 0 else "negative"
        supply_direction = "BUY" if index > 0 else "SELL"
        direction = "매수" if index > 0 else "매도"

        if magnitude < 0.05:
            label = f"거의 균형에 가까운 소폭 {direction} 우위"
        elif magnitude < 0.15:
            label = f"다소 {direction} 우위"
        elif magnitude < 0.30:
            label = f"{direction} 우위"
        else:
            label = f"뚜렷한 {direction} 우위"

    return LlmSupplyState(
        actual_supply_index=index,
        active_regime=regime,
        supply_direction=supply_direction,
        state_label=label,
        state_description=f"현재 개인투자자의 수급은 {label}입니다.",
    )


def build_signal_evidence(
    *,
    daily_signal: DailyCommentSignal,
    history: CommentSignalHistory,
) -> LlmSignalEvidence:
    """
    계산이 끝난 일별 신호와 비교값을 LLM 입력 정형 근거로 변환한다.

    키워드, 대표 댓글, 댓글 원문은 포함하지 않는다. 신호가 계산되지 않은
    날에는 점수와 강도 문구를 만들지 않는다.
    """
    is_ready = daily_signal.signal_status == "ready"
    return LlmSignalEvidence(
        actual_supply_index=daily_signal.actual_supply_index,
        supply_direction=daily_signal.supply_direction,
        signal_status=daily_signal.signal_status,
        comment_signal_score=(
            daily_signal.comment_signal_score if is_ready else None
        ),
        signal_level=daily_signal.signal_level if is_ready else None,
        comment_count=daily_signal.comment_count,
        previous_signal_score=(
            history.previous_signal_score if is_ready else None
        ),
        signal_change=history.signal_change if is_ready else None,
        signal_ma5=history.signal_ma5 if is_ready else None,
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


# 숫자와 로마자로 끝나는 종목명의 한국어 발음 기준 받침 유무다.
# 예: NAVER는 '네이버'로 읽으므로 받침이 없고, SOL은 '솔'이므로 있다.
_DIGIT_HAS_FINAL_CONSONANT = {
    "0": True,
    "1": True,
    "2": False,
    "3": True,
    "4": False,
    "5": False,
    "6": True,
    "7": True,
    "8": True,
    "9": False,
}
_LATIN_HAS_FINAL_CONSONANT = frozenset("lmn")


def _has_final_consonant(word: str) -> bool:
    """한국어 조사 선택을 위해 마지막 글자의 받침 유무를 확인한다."""
    for character in reversed(word.strip()):
        code = ord(character)

        if 0xAC00 <= code <= 0xD7A3:
            return (code - 0xAC00) % 28 != 0

        if character.isdigit():
            return _DIGIT_HAS_FINAL_CONSONANT[character]

        if character.isalpha():
            return character.lower() in _LATIN_HAS_FINAL_CONSONANT

    return False


def _topic_particle(word: str) -> str:
    return "은" if _has_final_consonant(word) else "는"


def _prompt_evidence(request: ReportGenerationRequest) -> dict[str, Any]:
    """프롬프트에 넣을 정형 근거만 골라 결정적인 dict로 만든다."""
    evidence: dict[str, Any] = {
        "stock_name": request.stock_name,
        "stock_code": request.stock_code,
        "model_date": request.model_date.isoformat(),
        "supply_direction": request.evidence.supply_direction,
        # v12는 방향을 쉬운 문장으로 전달한다. 방향 자체는 코드가 확정한
        # 값이므로 LLM이 다시 판단하지 않는다.
        "supply_direction_text": _SUPPLY_DIRECTION_SENTENCES[
            request.evidence.supply_direction
        ],
        "signal_status": request.evidence.signal_status,
        "comment_signal_score": request.evidence.comment_signal_score,
        "signal_level": request.evidence.signal_level,
        "comment_count": request.evidence.comment_count,
    }

    # 값이 없는 비교 항목은 키 자체를 넣지 않는다. null을 넣으면 LLM이
    # 없는 값을 설명하려 시도할 수 있다.
    optional_values = {
        "previous_signal_score": request.evidence.previous_signal_score,
        "signal_change": request.evidence.signal_change,
        "signal_ma5": request.evidence.signal_ma5,
    }

    for key, value in optional_values.items():
        if value is not None:
            evidence[key] = value

    return evidence


def describe_signal_pattern(
    request: ReportGenerationRequest,
) -> str | None:
    """
    현재 신호가 두 기준과 어떤 교차 관계인지 코드가 미리 판정한다.

    LLM이 `현재 - 전일`이나 `현재 - 평균`을 직접 계산하지 않게 하면서도,
    두 관계가 엇갈릴 때 하나로 단순화하지 않도록 관계 자체를 이름 붙여
    전달한다.
    """
    evidence = request.evidence
    score = evidence.comment_signal_score
    change = evidence.signal_change
    moving_average = evidence.signal_ma5

    if score is None or change is None or moving_average is None:
        return None

    above_previous = change > 0
    below_previous = change < 0
    above_average = score > moving_average
    below_average = score < moving_average

    if above_previous and above_average:
        return "어제보다도 최근 5일 평균보다도 높은 상태"

    if below_previous and below_average:
        return "어제보다도 최근 5일 평균보다도 낮은 상태"

    if above_previous and below_average:
        return "어제보다는 올라왔지만 최근 5일 평균보다는 아직 낮은 상태"

    if below_previous and above_average:
        return "어제보다는 낮아졌지만 최근 5일 평균보다는 여전히 높은 상태"

    return None


def _comparison_facts(request: ReportGenerationRequest) -> str:
    """
    코드가 판정한 비교 사실만 제시하고 문장 구성은 LLM에 맡긴다.

    v9까지는 완성된 문장을 그대로 주어 낭독을 유도했다. v10에서는 사실만
    고정하고 어떤 관계를 어떻게 묶을지는 LLM이 고르게 한다.
    """
    evidence = request.evidence
    lines = []

    if evidence.signal_change is not None:
        change = evidence.signal_change

        if change > 0:
            lines.append(
                f"- 어제(직전 거래일)와 비교: {change}점 높아짐 "
                f"(어제 {evidence.previous_signal_score}점)"
            )
        elif change < 0:
            lines.append(
                f"- 어제(직전 거래일)와 비교: {abs(change)}점 낮아짐 "
                f"(어제 {evidence.previous_signal_score}점)"
            )
        else:
            lines.append("- 어제(직전 거래일)와 비교: 변화 없음")

    if (
        evidence.signal_ma5 is not None
        and evidence.comment_signal_score is not None
    ):
        score = evidence.comment_signal_score
        moving_average = evidence.signal_ma5

        if score > moving_average:
            relation = "현재가 더 높음"
        elif score < moving_average:
            relation = "현재가 더 낮음"
        else:
            relation = "거의 같음"

        lines.append(
            f"- {ALLOWED_MOVING_AVERAGE_LABELS[3]}과 비교: {relation} "
            f"(평균 {moving_average}점)"
        )

    if not lines:
        return "비교할 과거 신호가 없으므로 변화에 대해 언급하지 마세요.\n"

    pattern = describe_signal_pattern(request)
    summary = (
        f"- 종합하면: {pattern}\n" if pattern else ""
    )
    joined = "\n".join(lines)
    return (
        "코드가 이미 판정한 비교 사실입니다. 이 관계를 바꾸지 말고, 어떤 "
        "것을 먼저 말할지와 문장 표현은 직접 정하세요.\n"
        f"{joined}\n"
        f"{summary}"
    )


def _build_user_prompt(request: ReportGenerationRequest) -> str:
    output_template = {
        "market_commentary": (
            "<수급 방향과 신호 관계를 쉬운 말로 풀어쓴 2~4문장>"
        ),
        "conclusion": (
            "<본문의 핵심 관계 하나를 완전한 한 문장으로 압축. 새 판단 금지>"
        ),
    }
    evidence = request.evidence
    stock_name = request.stock_name
    direction_sentence = _SUPPLY_DIRECTION_SENTENCES[
        evidence.supply_direction
    ]
    return (
        f"아래 정형 자료만 사용해 {stock_name}의 오늘 댓글 수급 신호를 "
        "일반 사용자에게 설명하세요.\n"

        f"수급 방향은 코드가 확정했습니다: {direction_sentence}. "
        "이 의미를 그대로 쓰되 표현은 다듬어도 됩니다. 현재형을 "
        "유지하세요.\n"

        f"현재 댓글 수급 신호는 {evidence.comment_signal_score}점이고 "
        f"등급은 '{evidence.signal_level}'입니다. 등급은 바꾸지 말고 "
        f"점수 옆에서 한 번 밝히세요. 예: "
        f"'{evidence.comment_signal_score}점으로 "
        f"{describe_signal_level(evidence.signal_level)}'.\n"

        f"{_comparison_facts(request)}"

        "문장 구조를 고정하지 마세요. 관계가 엇갈리면 한 문장 안에서 "
        "'하지만', '다만'으로 함께 보여줘도 됩니다. 중복되는 숫자는 "
        "생략해도 됩니다.\n"

        "'상회', '하회', '웃돌다', '못 미치다'보다 '더 높습니다', "
        "'낮은 편입니다', '어제보다 낮아졌습니다' 같은 쉬운 표현을 "
        "우선하세요.\n"

        "입력에 없는 숫자를 쓰지 말고 백분율 기호도 쓰지 마세요. "
        "주가 방향이나 투자 판단으로 확대하지 마세요.\n"

        f"SIGNAL_EVIDENCE_JSON={_canonical_json(_prompt_evidence(request))}\n"
        f"OUTPUT_JSON_TEMPLATE={_canonical_json(output_template)}\n"

        "완성된 JSON 객체 하나만 반환하세요."
    )


def _message_bytes(messages: Sequence[Mapping[str, str]]) -> int:
    return sum(len(message["content"].encode("utf-8")) for message in messages)


def build_report_messages(
    request: ReportGenerationRequest,
) -> tuple[dict[str, str], ...]:
    """OpenAI 호환 Chat Completions에 전달할 최종 메시지를 만든다."""
    messages = (
        {"role": "system", "content": REPORT_SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(request)},
    )

    if _message_bytes(messages) > MAX_LLM_MESSAGE_BYTES:
        raise ValueError("LLM 고정 메시지가 12,000바이트를 초과합니다.")

    return messages


def calculate_report_input_hash(request: ReportGenerationRequest) -> str:
    """보고서 원본·버전·최종 메시지를 포함한 재현 가능한 hash를 만든다."""
    payload = {
        "request": request.model_dump(mode="json"),
        "messages": build_report_messages(request),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def should_request_llm_commentary(
    request: ReportGenerationRequest,
) -> bool:
    """
    LLM을 호출할 만한 정형 근거가 있는지 판정한다.

    수급 방향과 현재 신호만 있는 경우는 deterministic 문장으로 충분하며
    LLM을 호출할 가치가 없다. 비교 가능한 과거 신호가 하나 이상 있을
    때만 LLM에게 요약을 맡긴다.
    """
    if request.evidence.signal_status != "ready":
        return False

    return request.evidence.has_comparable_history()


def detect_direct_causality(value: str) -> bool:
    """수급·댓글과 주가 사이의 명백한 직접 인과 표현만 탐지한다."""
    compact = " ".join(value.split())
    patterns = (
        r"(?:수급|매수세|매도세|개인투자자.{0,8}(?:매수|매도)).{0,24}"
        r"(?:주가|상승|하락).{0,16}(?:주도|이끌|막|원인|요인|작용|발생|이어)",
        r"(?:수급|매수세|매도세).{0,16}(?:때문|덕분).{0,16}(?:주가|상승|하락)",
        r"(?:댓글|게시판|분위기|신호).{0,20}(?:수급|매수|매도).{0,16}"
        r"(?:발생|유발|만들|이끌)",
    )
    return any(re.search(pattern, compact) for pattern in patterns)


def _contains_unexpected_cjk(value: str) -> bool:
    return re.search("[㐀-䶿一-鿿]", value) is not None


def allowed_report_integers(
    request: ReportGenerationRequest,
) -> set[int]:
    """
    본문에 나타나도 되는 정수 집합을 만든다.

    입력 근거에 있는 값, 0~100 척도 표기, 이동평균 창 크기와 보고서
    날짜 구성요소만 허용한다. 그 밖의 숫자는 LLM이 만들어낸 값이다.
    """
    allowed = {
        0,
        100,
        SIGNAL_MOVING_AVERAGE_WINDOW,
        request.evidence.comment_count,
        request.model_date.year,
        request.model_date.month,
        request.model_date.day,
    }

    for value in (
        request.evidence.comment_signal_score,
        request.evidence.previous_signal_score,
        request.evidence.signal_ma5,
    ):
        if value is not None:
            allowed.add(int(value))

    if request.evidence.signal_change is not None:
        allowed.add(abs(int(request.evidence.signal_change)))

    return allowed


def _validate_numeric_claims(
    request: ReportGenerationRequest,
    value: str,
) -> None:
    if "%" in value:
        raise ValueError(
            "신호 점수를 백분율로 표현하는 % 기호는 사용할 수 없습니다."
        )

    if re.search(r"\d+[.,]\d", value):
        raise ValueError(
            "본문에는 소수 수치를 적지 않습니다."
        )

    allowed = allowed_report_integers(request)
    invented = sorted(
        {
            int(token)
            for token in re.findall(r"\d+", value)
            if int(token) not in allowed
        }
    )

    if invented:
        raise ValueError(
            f"입력 근거에 없는 숫자가 포함됐습니다: {invented}"
        )


def detect_signal_levels(value: str) -> set[str]:
    """
    본문에서 강도 등급으로 서술된 표현을 찾는다.

    등급 뒤에 "수준"이 붙거나 점수 옆에서 서술될 때만 등급 표현으로
    본다. 그래야 "평균 55점보다 낮습니다", "낮아졌지만 평균보다는 높은
    상태" 같은 비교·관계 서술을 등급 재분류로 오인하지 않는다.

    등급을 문장에서 생략하는 것은 허용하므로 여기서는 검출만 한다.
    """
    compact = " ".join(value.split())
    detected = set()

    for pattern in (
        _LEVEL_WITH_NOUN_PATTERN,
        _LEVEL_AFTER_SCORE_PATTERN,
        _LEVEL_BEFORE_SCORE_PATTERN,
    ):
        for match in pattern.finditer(compact):
            prefix = compact[
                max(0, match.start() - _LEVEL_PREFIX_WINDOW): match.start()
            ]

            # "평균 49점보다 높은 수준", "85점과도 비슷하게 높은 수준"은
            # 등급 재분류가 아니라 다른 값과의 비교다.
            if any(marker in prefix for marker in _COMPARISON_MARKERS):
                continue

            detected.add(_LEVEL_STEM_TO_LABEL[match.group(1)])

    return detected


def _validate_signal_level_language(
    request: ReportGenerationRequest,
    *,
    market_commentary: str,
    conclusion: str,
) -> None:
    """
    입력 signal_level과 모순되는 등급으로 표현하지 않았는지 검증한다.

    등급을 생략하거나 위치를 바꾸는 것은 허용한다. 등급을 말했다면
    코드가 결정한 등급과 어긋나지 않아야 한다.

    v12는 '매우'를 뗀 표현을 모순으로 보지 않는다. '매우 낮음'인 날에
    "낮은 수준이 이어지고 있습니다"라고 쓰는 것은 덜 정밀할 뿐 사실과
    어긋나지 않기 때문이다. 반대로 '낮음'을 '매우 낮음'으로 키우거나
    '낮음'을 '높음'으로 뒤집는 것은 그대로 막는다.
    """
    expected = request.evidence.signal_level

    if expected is None:
        return

    acceptable = {expected} | _COARSER_LEVELS.get(expected, set())

    for field_name, text in (
        ("market_commentary", market_commentary),
        ("conclusion", conclusion),
    ):
        reclassified = detect_signal_levels(text) - acceptable

        if reclassified:
            raise ValueError(
                "입력 signal_level을 다른 등급으로 표현했습니다: "
                f"field={field_name}, 입력={expected}, "
                f"출력={sorted(reclassified)}"
            )


def _validate_supply_direction(
    request: ReportGenerationRequest,
    value: str,
) -> None:
    """
    실제 수급 방향과 반대로 서술하지 않았는지 검증한다.

    v12는 '개인투자자의 매도가 더 많았습니다' 같은 쉬운 표현을 권장하므로
    '매수 우위' 형태뿐 아니라 '매수가 더 많다' 형태의 반전도 함께 본다.
    """
    compact = " ".join(value.split())
    direction = request.evidence.supply_direction
    opposite_token = {"BUY": "매도", "SELL": "매수"}.get(direction)

    for match in _DIRECTION_MORE_PATTERN.finditer(compact):
        stated = match.group(1)

        if direction == "NEUTRAL":
            raise ValueError(
                "수급 균형인 날에 특정 수급 방향을 서술했습니다: "
                f"본문='{match.group(0)}'"
            )

        if stated == opposite_token:
            raise ValueError(
                "실제 수급 방향과 반대로 서술했습니다: "
                f"입력={direction}, 본문='{match.group(0)}'"
            )


def _validate_direction_score_confusion(value: str) -> None:
    """수급 방향과 댓글 신호 점수를 하나로 섞지 않았는지 검증한다."""
    compact = " ".join(value.split())
    confusion = _DIRECTION_SCORE_CONFUSION_PATTERN.search(compact)

    if confusion:
        raise ValueError(
            "수급 방향과 댓글 신호 점수를 같은 지표처럼 서술했습니다: "
            f"'{confusion.group(0)}'"
        )


def _validate_supply_pressure_change(value: str) -> None:
    """
    근거 없는 수급 강도 변화 서술을 막는다.

    evidence에는 오늘의 수급 방향만 있고 이전 방향이나 강도의 시계열은
    없다. SELL이라는 사실만으로 '매도 압력이 커졌다'고 쓰면 입력에 없는
    사실을 만든 것이다.
    """
    compact = " ".join(value.split())
    pressure = _SUPPLY_PRESSURE_CHANGE_PATTERN.search(compact)

    if pressure:
        raise ValueError(
            "수급 강도의 변화는 입력에 없습니다: "
            f"'{pressure.group(0)}'"
        )


def _validate_number_roles(
    request: ReportGenerationRequest,
    value: str,
) -> None:
    """
    현재값·직전값·변화량·평균값의 역할이 뒤바뀌지 않았는지 검증한다.

    숫자가 입력 근거에 있는 값이더라도 다른 값의 자리에 놓이면 사실이
    달라진다. 변화량을 직전 거래일의 점수처럼 적는 경우가 대표적이다.
    """
    compact = " ".join(value.split())
    evidence = request.evidence
    previous = evidence.previous_signal_score

    if previous is None:
        return

    for match in _PREVIOUS_SCORE_MENTION_PATTERN.finditer(compact):
        stated = int(match.group(1))

        if stated != previous:
            raise ValueError(
                "직전 거래일 점수 자리에 다른 값을 적었습니다: "
                f"본문={stated}, previous_signal_score={previous}, "
                f"signal_change={evidence.signal_change}"
            )


def _validate_moving_average_language(
    request: ReportGenerationRequest,
    value: str,
) -> None:
    """signal_ma5를 다른 통계로 바꾸거나 변화를 주장하지 않았는지 본다."""
    compact = " ".join(value.split())

    for alias in FORBIDDEN_MOVING_AVERAGE_ALIASES:
        if alias in compact:
            raise ValueError(
                "signal_ma5를 다른 통계처럼 표현했습니다: "
                f"{alias}. '{MOVING_AVERAGE_LABEL}' 계열 표현을 쓰세요."
            )

    trend = _MOVING_AVERAGE_TREND_PATTERN.search(compact)

    if trend:
        raise ValueError(
            f"평균 자체의 변화는 입력에 없습니다: '{trend.group(0)}'"
        )


def _resolve_comparable_moving_average(
    request: ReportGenerationRequest,
) -> int | None:
    """
    다른 근거 값과 숫자가 겹치지 않는 signal_ma5만 반환한다.

    값이 겹치면 본문의 숫자가 무엇을 가리키는지 판정할 수 없다.
    """
    evidence = request.evidence
    moving_average = evidence.signal_ma5

    if moving_average is None:
        return None

    other_values = {
        evidence.comment_signal_score,
        evidence.previous_signal_score,
        evidence.comment_count,
    }

    if evidence.signal_change is not None:
        other_values.add(abs(evidence.signal_change))

    return None if moving_average in other_values else moving_average


def _validate_moving_average_relation(
    request: ReportGenerationRequest,
    value: str,
) -> None:
    """평균 대비 비교 방향이 실제 값 관계와 일치하는지 검증한다."""
    evidence = request.evidence
    moving_average = _resolve_comparable_moving_average(request)
    score = evidence.comment_signal_score

    if moving_average is None or score is None:
        return

    compact = " ".join(value.split())

    # 평균을 주어로 두고 현재와 비교하면 방향이 뒤집힌다.
    # "평균 81점이 오늘보다 낮다"는 "평균 < 현재"라는 주장이다.
    for match in _AVERAGE_AS_SUBJECT_PATTERN.finditer(compact):
        stated_average = int(match.group(1))

        if stated_average != moving_average:
            continue

        says_average_is_higher = match.group(2) == "높"
        average_is_higher = moving_average > score

        if says_average_is_higher != average_is_higher:
            raise ValueError(
                "평균과 현재 점수의 비교 주어가 뒤바뀌었습니다: "
                f"현재={score}, 평균={moving_average}, "
                f"본문='{match.group(0)}'"
            )

    for match in re.finditer(
        rf"(?<!\d){moving_average}(?!\d)\s*점?",
        compact,
    ):
        tail = compact[match.end(): match.end() + 14]

        # 위에서 이미 판정한 '평균이 주어' 문형은 건너뛴다.
        if re.match(r"\s*(?:이|은|는|가)\s*(?:오늘|현재|지금|당일)", tail):
            continue

        says_above = any(word in tail for word in _ABOVE_WORDS)
        says_below = any(word in tail for word in _BELOW_WORDS)

        if says_above and score < moving_average:
            raise ValueError(
                "평균 대비 비교 방향이 실제와 반대입니다: "
                f"현재={score}, 평균={moving_average}, 본문='{tail.strip()}'"
            )

        if says_below and score > moving_average:
            raise ValueError(
                "평균 대비 비교 방향이 실제와 반대입니다: "
                f"현재={score}, 평균={moving_average}, 본문='{tail.strip()}'"
            )


def _clause_tail(compact: str, end: int, window: int) -> str:
    """
    변화량 뒤의 서술을 같은 절 안에서만 잘라 본다.

    "어제보다 30점 높아졌지만 최근 평균보다는 낮습니다"에서 뒤쪽 절의
    '낮' 때문에 방향이 반대라고 오판하지 않기 위해 절 경계에서 끊는다.
    """
    tail = compact[end: end + window]
    boundary = _CLAUSE_BOUNDARY_PATTERN.search(tail)
    return tail if boundary is None else tail[: boundary.start()]


def _clause_prefix(compact: str, start: int, window: int) -> str:
    """
    변화량 앞의 서술도 같은 절 안에서만 본다.

    "최근 5거래일 평균 52점보다는 낮지만 어제보다 11점 높아졌습니다"에서
    앞 절의 평균 값이 변화량의 기준으로 오인되면 정상 문장이 폐기된다.
    절 경계 뒤쪽만 남겨 오탐을 없앤다.
    """
    prefix = compact[max(0, start - window): start]
    boundaries = list(_CLAUSE_BOUNDARY_PATTERN.finditer(prefix))
    return prefix if not boundaries else prefix[boundaries[-1].end():]


def _validate_change_statement(
    request: ReportGenerationRequest,
    value: str,
) -> None:
    """
    변화량의 값과 방향, 비교 기준이 맞는지 검증한다.

    signal_change는 현재 신호와 직전 거래일 신호의 차이다. 값이나
    방향이 다르거나 signal_ma5를 기준으로 삼으면 사실이 어긋난다.
    표현 형식 자체는 강제하지 않는다.
    """
    compact = " ".join(value.split())
    change = request.evidence.signal_change
    moving_average = _resolve_comparable_moving_average(request)

    # 같은 위치를 두 패턴이 함께 잡을 수 있으므로 끝 위치로 중복을 없앤다.
    matches = {
        match.end(): match
        for pattern in (
            _CHANGE_PATTERN,
            _CHANGE_WITH_BASELINE_PATTERN,
        )
        for match in pattern.finditer(compact)
    }

    for _end, match in sorted(matches.items()):
        stated = int(match.group(1))

        if change is None or stated != abs(change):
            raise ValueError(
                "변화량으로 서술한 숫자가 signal_change와 다릅니다: "
                f"본문={stated}, signal_change={change}"
            )

        tail = _clause_tail(compact, match.end(), _CHANGE_SUFFIX_WINDOW)

        if change > 0 and any(word in tail for word in _DOWNWARD_WORDS):
            raise ValueError(
                "변화 방향이 실제와 반대입니다: "
                f"signal_change={change}, 본문='{tail.strip()}'"
            )

        if change < 0 and any(word in tail for word in _UPWARD_WORDS):
            raise ValueError(
                "변화 방향이 실제와 반대입니다: "
                f"signal_change={change}, 본문='{tail.strip()}'"
            )

        if moving_average is None:
            continue

        prefix = _clause_prefix(
            compact,
            match.start(),
            _CHANGE_PREFIX_WINDOW,
        )

        if re.search(rf"(?<!\d){moving_average}(?!\d)", prefix):
            raise ValueError(
                "변화량의 기준을 직전 거래일이 아닌 평균으로 서술했습니다: "
                f"'{compact[max(0, match.start() - 20): match.end()]}'"
            )


def _validate_trend_subject(value: str) -> None:
    """
    변화 표현의 대상이 확인 가능한지 검증한다.

    댓글 수급 신호의 변화는 evidence로 확인할 수 있다. 매수세나 투자
    심리, 주가의 시계열은 evidence에 없으므로 그 대상에 변화 표현을
    붙이면 사실을 확인할 수 없다. 대상이 명시되지 않은 경우는 문체
    문제이므로 막지 않는다.
    """
    compact = " ".join(value.split())

    for match in _TREND_TERM_PATTERN.finditer(compact):
        prefix = compact[
            max(0, match.start() - _TREND_SUBJECT_WINDOW): match.start()
        ]

        for subject in _TREND_SUBJECT_BLOCKLIST:
            if subject in prefix:
                raise ValueError(
                    "변화 표현을 확인할 수 없는 대상에 사용했습니다: "
                    f"'{subject}' + '{match.group(0)}'"
                )


def _validate_price_and_advice(value: str) -> None:
    """주가 방향 예측과 투자 권유를 대상 기준으로 차단한다."""
    compact = " ".join(value.split())
    price = _PRICE_DIRECTION_PATTERN.search(compact)

    if price:
        raise ValueError(
            "주가나 시장의 방향을 서술했습니다: "
            f"'{price.group(0)}'"
        )

    for phrase in (
        *FORBIDDEN_PRICE_EXPRESSIONS,
        *FORBIDDEN_ADVICE_EXPRESSIONS,
        *FORBIDDEN_PROBABILITY_EXPRESSIONS,
    ):
        if phrase in compact:
            raise ValueError(
                "주가 방향·투자 권유·확률 표현이 포함됐습니다: "
                f"{phrase}"
            )


def _validate_future_and_cause(value: str) -> None:
    """미래 전망과 원인 추론을 차단한다."""
    compact = " ".join(value.split())
    outlook = _FUTURE_OUTLOOK_PATTERN.search(compact)

    if outlook:
        raise ValueError(
            f"입력에 없는 미래 전망을 서술했습니다: '{outlook.group(0)}'"
        )

    cause = _CAUSAL_PATTERN.search(compact)

    if cause:
        raise ValueError(
            f"입력에 없는 원인을 추론했습니다: '{cause.group(0)}'"
        )


def _validate_maintenance_claim(
    request: ReportGenerationRequest,
    value: str,
) -> None:
    """
    점수가 실제로 바뀌었는데 그대로라고 주장하는 경우만 막는다.

    v11은 변화폭이 크면 '유지'라는 단어를 모두 막았고, v12는 등급 구간이
    같은지까지 따졌다. 두 방식 모두 "높은 수준을 유지하고 있습니다" 같은
    정상 문장을 폐기했다.

    v13은 '유지'의 의미를 더 이상 해석하지 않는다. 상태가 이어진다는
    추상적 서술은 허용하고, "점수가 그대로다", "어제와 같은 점수다"처럼
    **숫자 자체가 동일하다**고 주장하는 경우만 signal_change와 대조한다.

    등급 전환과 수급 방향 전환은 evidence에 직전 값이 없으므로 계속
    확인할 수 없고, 따라서 계속 막는다.
    """
    compact = " ".join(value.split())
    regime_change = _REGIME_CHANGE_PATTERN.search(compact)

    if regime_change:
        raise ValueError(
            "직전 등급과 직전 수급 방향이 입력에 없어 전환 여부를 확인할 "
            f"수 없습니다: '{regime_change.group(0)}'"
        )

    unchanged = _UNCHANGED_SCORE_PATTERN.search(compact)

    if unchanged is None:
        return

    change = request.evidence.signal_change

    if change is None:
        raise ValueError(
            "직전 거래일과 비교할 값이 없어 점수가 그대로인지 판단할 수 "
            f"없습니다: '{unchanged.group(0)}'"
        )

    if change != 0:
        raise ValueError(
            "점수가 실제로 변했는데 그대로라고 서술했습니다: "
            f"signal_change={change}, 본문='{unchanged.group(0)}'"
        )


def validate_market_commentary_response(
    *,
    request: ReportGenerationRequest,
    response: LlmMarketCommentary,
) -> None:
    """
    입력 근거와 대조 가능한 사실만 검증한다.

    문체나 문장 구조는 강제하지 않는다. 검증 목적은 evidence와 모순되는
    서술을 막는 것이다.
    """
    narrative_text = f"{response.market_commentary} {response.conclusion}"

    if detect_direct_causality(narrative_text):
        raise ValueError("수급·댓글과 주가 사이의 직접 인과 표현이 포함됐습니다.")

    if _contains_unexpected_cjk(narrative_text):
        raise ValueError("한국어 본문에 비정상적인 중국어 문자가 포함됐습니다.")

    _validate_price_and_advice(narrative_text)
    _validate_future_and_cause(narrative_text)
    _validate_numeric_claims(request, narrative_text)
    _validate_supply_direction(request, narrative_text)
    _validate_direction_score_confusion(narrative_text)
    _validate_supply_pressure_change(narrative_text)
    _validate_number_roles(request, narrative_text)
    _validate_moving_average_language(request, narrative_text)
    _validate_moving_average_relation(request, narrative_text)
    _validate_change_statement(request, narrative_text)
    _validate_trend_subject(narrative_text)
    _validate_maintenance_claim(request, narrative_text)
    _validate_signal_level_language(
        request,
        market_commentary=response.market_commentary,
        conclusion=response.conclusion,
    )


def _change_phrase(signal_change: int) -> str:
    if signal_change > 0:
        return f"어제보다 {signal_change}점 높아졌"

    if signal_change < 0:
        return f"어제보다 {abs(signal_change)}점 낮아졌"

    return "어제와 같은 수준이"


def _moving_average_phrase(
    *,
    comment_signal_score: int,
    signal_ma5: int,
) -> str:
    average_label = ALLOWED_MOVING_AVERAGE_LABELS[3]

    if comment_signal_score > signal_ma5:
        return f"{average_label} {signal_ma5}점보다도 높습니다"

    if comment_signal_score < signal_ma5:
        return f"{average_label} {signal_ma5}점보다는 낮습니다"

    return f"{average_label} {signal_ma5}점과 비슷한 수준입니다"


def _comparison_sentence(
    *,
    comment_signal_score: int,
    signal_change: int | None,
    signal_ma5: int | None,
) -> str | None:
    """
    두 비교를 한 문장으로 묶되 방향이 엇갈리면 그대로 드러낸다.

    "전일보다 올랐지만 평균에는 못 미친다"처럼 상반된 관계를 하나로
    단순화하지 않는 것이 핵심이다.
    """
    if signal_change is None and signal_ma5 is None:
        return None

    if signal_ma5 is None:
        return f"{_change_phrase(signal_change)}습니다."

    average_phrase = _moving_average_phrase(
        comment_signal_score=comment_signal_score,
        signal_ma5=signal_ma5,
    )

    if signal_change is None:
        return f"{average_phrase}."

    change_phrase = _change_phrase(signal_change)
    rises = signal_change > 0
    falls = signal_change < 0
    above_average = comment_signal_score > signal_ma5
    below_average = comment_signal_score < signal_ma5
    crossed = (rises and below_average) or (falls and above_average)
    connector = "지만" if crossed else "고"

    if signal_change == 0:
        return f"{change_phrase}고 {average_phrase}."

    return f"{change_phrase}{connector} {average_phrase}."


def build_deterministic_commentary(
    request: ReportGenerationRequest,
) -> LlmMarketCommentary:
    """
    LLM 없이 정형 값만으로 한국어 요약을 만든다.

    LLM API 실패나 비교 가능한 정형 데이터 부족 시에도 화면에 표시할
    문장을 보장한다. 입력 값을 그대로 문장에 배치하며 원인이나 전망을
    만들지 않는다.
    """
    evidence = request.evidence
    stock_name = request.stock_name
    particle = _topic_particle(stock_name)
    direction_clause = _SUPPLY_DIRECTION_CLAUSES[evidence.supply_direction]

    if evidence.signal_status == "no_direction":
        return LlmMarketCommentary(
            market_commentary=(
                f"{stock_name}{particle} 현재 개인투자자의 매수와 매도가 "
                "비슷합니다. 수급 방향이 정해지지 않아 댓글 수급 신호는 "
                "계산하지 않았습니다."
            ),
            conclusion=(
                f"{stock_name}{particle} 매수와 매도가 비슷해 댓글 신호를 "
                "특정 방향과 연결하지 않습니다."
            ),
        )

    if evidence.signal_status == "insufficient_features":
        return LlmMarketCommentary(
            market_commentary=(
                f"{stock_name}{particle} {direction_clause}, 이날 "
                "댓글에서 모델이 인식한 학습 단어가 없어 댓글 수급 신호는 "
                "계산하지 않았습니다."
            ),
            conclusion=(
                f"{stock_name}{particle} 모델이 인식한 댓글 특성이 없어 "
                "이날 댓글 신호를 제공하지 않습니다."
            ),
        )

    score = evidence.comment_signal_score
    level = evidence.signal_level
    sentences = [
        f"{stock_name}{particle} {direction_clause}, 댓글 수급 "
        f"신호는 {score}점으로 {describe_signal_level(level)}입니다."
    ]
    comparison = _comparison_sentence(
        comment_signal_score=score,
        signal_change=evidence.signal_change,
        signal_ma5=evidence.signal_ma5,
    )

    if comparison is not None:
        sentences.append(comparison)

    # 두 비교가 같은 방향이면 앞 문장에서 이미 드러나므로 덧붙이지
    # 않는다. 엇갈릴 때만 관계를 한 번 더 정리한다.
    pattern = describe_signal_pattern(request)
    crossed = pattern is not None and "지만" in pattern

    if crossed:
        sentences.append(f"현재 댓글 신호는 {pattern}입니다.")
        conclusion = (
            f"{stock_name}{particle} {direction_clause}, 댓글 수급 "
            f"신호는 {pattern}입니다."
        )
    else:
        conclusion = (
            f"{stock_name}{particle} {direction_clause}, 댓글 수급 "
            f"신호는 {score}점으로 {describe_signal_level(level)}입니다."
        )

    return LlmMarketCommentary(
        market_commentary=" ".join(sentences),
        conclusion=conclusion,
    )


def _render_report_text(
    *,
    title: str,
    supply_description: str,
    commentary: LlmMarketCommentary,
) -> str:
    return "\n\n".join(
        [
            title,
            supply_description,
            commentary.market_commentary,
            f"[한줄 정리]\n{commentary.conclusion}",
            f"※ {REPORT_NOTICE}",
        ]
    )


def build_report_json(
    *,
    request: ReportGenerationRequest,
    status: str,
    generation_result: ReportGenerationResult | None,
) -> dict[str, Any]:
    """
    검증된 LLM 결과와 코드 계산값을 화면·API용 JSON으로 조립한다.

    Flask 영역이 백분위, 모델 방향 판단, 신호 구간 계산을 다시 하지
    않도록 완성된 값만 담는다.
    """
    commentary = (
        build_deterministic_commentary(request)
        if generation_result is None
        else generation_result.commentary
    )
    evidence = request.evidence
    title = f"{request.stock_name} 댓글 수급 신호"
    rendered_text = _render_report_text(
        title=title,
        supply_description=request.supply_state.state_description,
        commentary=commentary,
    )
    return {
        "status": status,
        "prompt_version": request.prompt_version,
        "report_schema_version": request.report_schema_version,
        "evidence_schema_version": request.evidence_schema_version,
        "commentary_source": (
            "deterministic" if generation_result is None else "llm"
        ),
        "stock_id": request.stock_id,
        "stock_code": request.stock_code,
        "stock_name": request.stock_name,
        "model_date": request.model_date.isoformat(),
        "daily_document_id": request.daily_document_id,
        "comment_count": request.comment_count,
        "actual_supply_index": evidence.actual_supply_index,
        "supply_direction": evidence.supply_direction,
        "supply_state": request.supply_state.model_dump(mode="json"),
        "comment_signal_score": evidence.comment_signal_score,
        "signal_level": evidence.signal_level,
        "signal_status": evidence.signal_status,
        "supply_data_status": request.supply_data_status,
        "supply_observed_at": (
            None
            if request.supply_observed_at is None
            else request.supply_observed_at.isoformat()
        ),
        "previous_signal_score": evidence.previous_signal_score,
        "signal_change": evidence.signal_change,
        "signal_ma5": evidence.signal_ma5,
        "market_commentary": commentary.market_commentary,
        "conclusion": commentary.conclusion,
        "display_report": {
            "title": title,
            "current_supply": request.supply_state.state_description,
            "market_commentary": commentary.market_commentary,
            "conclusion": commentary.conclusion,
            "interpretation_note": REPORT_NOTICE,
            "rendered_text": rendered_text,
        },
        "llm_report": commentary.model_dump(mode="json"),
        "details": {
            "active_model_variant": request.active_model_variant,
            "predicted_score": request.predicted_score,
            "recognized_feature_count": request.recognized_feature_count,
            "unique_token_count": request.unique_token_count,
            "vocabulary_coverage": request.vocabulary_coverage,
            "inference_status": request.inference_status,
            "positive_result_id": request.positive_result_id,
            "negative_result_id": request.negative_result_id,
            "model_name": request.model_name,
            "model_version": request.model_version,
            "artifact_schema_version": request.artifact_schema_version,
            "calibration_schema_version": (
                request.calibration_schema_version
            ),
            "evidence": evidence.model_dump(mode="json"),
        },
        "notice": REPORT_NOTICE,
    }


def build_flask_daily_signal_response(
    report_json: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Flask 담당자가 모델 내부 구조를 몰라도 쓸 수 있는 응답을 만든다.

    프론트가 백분위, 방향 판단, 신호 구간을 직접 계산하지 않도록 이미
    완성된 값만 전달한다.
    """
    return {
        "status": report_json["status"],
        "commentary_source": report_json["commentary_source"],
        "stock_code": report_json["stock_code"],
        "stock_name": report_json["stock_name"],
        "model_date": report_json["model_date"],
        "supply_direction": report_json["supply_direction"],
        "actual_supply_index": report_json["actual_supply_index"],
        "comment_signal_score": report_json["comment_signal_score"],
        "signal_level": report_json["signal_level"],
        "signal_status": report_json["signal_status"],
        "report_supply_data_status": report_json["supply_data_status"],
        "report_supply_observed_at": report_json["supply_observed_at"],
        "signal_change": report_json["signal_change"],
        "signal_ma5": report_json["signal_ma5"],
        "comment_count": report_json["comment_count"],
        "market_commentary": report_json["market_commentary"],
        "conclusion": report_json["conclusion"],
        "notice": report_json["notice"],
    }
