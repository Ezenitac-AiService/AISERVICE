from evaluator.schemas import BinaryChecklist

def calculate_authenticity_score(checklist: BinaryChecklist) -> tuple[int, str]:
    """이진 체크리스트 판정 결과에 의거하여 기계적으로 점수 및 등급을 합산 연산합니다."""
    score = 100
    
    if checklist.has_meaningless_assertions:
        score -= 30
    if checklist.has_trivial_assert_fallback:
        score -= 20
    if checklist.is_mocking_abused:
        score -= 30
    if checklist.contains_exception_eater:
        score -= 20
    if not checklist.virtual_mutant_killed:
        score -= 40
        
    # 하한선 0점 강제
    score = max(0, score)
    
    # 등급 매핑
    if score == 100:
        grade = "Excellent"
    elif score >= 80:
        grade = "Pass"
    elif score >= 60:
        grade = "Fair"
    else:
        grade = "Fail"
        
    return score, grade
