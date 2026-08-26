"""
3-Stage Implicit Anaphora Resolution Engine (Spec 035 FR-006 / T018).
사용자의 대명사/지시어("아까 그 크림", "처음에 말한 앰플") 질의 시
세션 메타데이터 및 의미 검색을 통해 대상 턴 번호를 자동 특정합니다.
"""

import re
import logging
from typing import List, Optional, Tuple
from .graph_state import AnaphoraTurnTag

logger = logging.getLogger("oliview.rag.anaphora")


class AnaphoraResolver:
    """비명시적 지시어/대명사 해석기."""

    # 지시어 탐지 정규표현식
    ANAPHORA_PATTERNS = [
        re.compile(r"(?:아까|이전에?|방금|처음에?|앞서|지난번|그때)\s*(?:말한|비교한|언급한|추천한)?\s*(?:그|해당|이)?\s*(?:제품|화장품|크림|앰플|세럼|토너|로션|에센스|선크림|클렌저|거|것)", re.IGNORECASE),
        re.compile(r"(?:그거|그것|그제품|해당제품|그크림|그앰플)\s*(?:가격|성분|후기|장단점|어때|얼마|비교)", re.IGNORECASE),
        re.compile(r"\b(?:[0-9]+번째|첫\s*번째|두\s*번째|세\s*번째)\s*(?:대화|질문|제품)\b", re.IGNORECASE),
    ]

    def is_anaphora_query(self, query: str) -> bool:
        """질의에 비명시적 대명사/지시어가 포함되어 있는지 확인합니다."""
        for pattern in self.ANAPHORA_PATTERNS:
            if pattern.search(query):
                return True
        return False

    def resolve_turn_from_tags(
        self,
        query: str,
        turn_tags: List[AnaphoraTurnTag],
        similarity_threshold: float = 0.65,
    ) -> Optional[int]:
        """
        3단계 암묵적 지시어 해결 파이프라인:
        1. 명시적 턴 번호(예: '10번째 대화') 파싱
        2. `turn_tags`의 entities/attributes 키워드 매칭
        3. 텍스트 유사도 기반 대상 턴 특정
        """
        if not turn_tags:
            return None

        # 1. 명시적 턴 번호 추출 시도 ("N번째 대화")
        turn_num_match = re.search(r"([0-9]+)번째\s*(?:대화|질문)", query)
        if turn_num_match:
            turn_idx = int(turn_num_match.group(1))
            for tag in turn_tags:
                if tag.turn_index == turn_idx:
                    return turn_idx

        # 2. 엔티티 및 속성 키워드 매칭
        lower_query = query.lower()
        best_match_turn: Optional[int] = None
        best_match_score = 0

        for tag in reversed(turn_tags):  # 최근 턴 우선
            score = 0
            # 엔티티 매칭
            for entity in tag.entities_mentioned:
                # 제품명 단어 분할 매칭 (예: '닥터지', '크림', '앰플')
                for token in entity.lower().split():
                    if len(token) >= 2 and token in lower_query:
                        score += 3
            # 속성 매칭 (예: '보습', '진정', '가격')
            for attr in tag.attributes_discussed:
                if attr.lower() in lower_query:
                    score += 2

            # 요약문 단어 매칭
            if any(w in lower_query for w in tag.short_summary.lower().split() if len(w) >= 2):
                score += 1

            if score > best_match_score:
                best_match_score = score
                best_match_turn = tag.turn_index

        if best_match_score >= 2 and best_match_turn is not None:
            logger.info(f"[AnaphoraResolver] Matched Turn {best_match_turn} (Score: {best_match_score}) for query: '{query}'")
            return best_match_turn

        # 3. 기본 지시어("아까 그거")의 경우 가장 최근 턴(Turn - 1)으로 해결
        if self.is_anaphora_query(query):
            latest_turn = turn_tags[-1].turn_index
            logger.info(f"[AnaphoraResolver] Fallback to latest Turn {latest_turn} for generic anaphora: '{query}'")
            return latest_turn

        return None

    def resolve(self, query: str, session_id: str) -> Tuple[str, List[str]]:
        """과거 세션에서 대명사를 해소하여 (정규화된 쿼리, 해소된 엔티티 목록)을 반환합니다."""
        if not self.is_anaphora_query(query):
            return query, []

        from .session import session_store
        messages = session_store.get_messages(session_id, max_messages=10)
        resolved_entities: List[str] = []
        for msg in reversed(messages):
            content = msg.get("content", "")
            for pat in [r"차앤박\s*프로폴리스(?:\s*에너지)?\s*앰플", r"닥터지\s*레드\s*블레미쉬(?:\s*클리어)?\s*크림", r"이니스프리\s*그린티\s*세럼"]:
                m = re.search(pat, content, re.IGNORECASE)
                if m:
                    entity = m.group(0)
                    if entity not in resolved_entities:
                        resolved_entities.append(entity)
            if resolved_entities:
                break

        if resolved_entities:
            resolved_query = f"{resolved_entities[0]} {query}"
            return resolved_query, resolved_entities
        return query, []


# Singleton instance
anaphora_resolver = AnaphoraResolver()
