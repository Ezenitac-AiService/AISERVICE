import os
import time
import json
import httpx
import pymysql
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from common import (
    load_sample_config,
    print_section_header,
    get_httpx_client,
    clean_think_tags,
    NO_THINK_SYSTEM_PROMPT
)

# 1. 🗄️ 환경 설정 로드
config = load_sample_config()
SERVER_HOST = config["server_host"]
MAIN_PORT = config["main_port"]
MODEL_NAME = config["default_model"]
TARGET_URL = f"{SERVER_HOST}:{MAIN_PORT}/v1/chat/completions"

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "192.168.0.8"),
    "user": os.getenv("DB_USER", "GP"),
    "password": os.getenv("DB_PASSWORD", "GP123!"),
    "database": "oliview_project",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor
}

BATCH_SIZE = 10  # vLLM 인프라 부하 최소화를 위한 최적의 배치 묶음 크기

# 2. 🧠 Pydantic v2 데이터 구조화 스키마 선언
class ReviewMetadata(BaseModel):
    aspect_sentence_id: int = Field(description="전달받은 리뷰 문장의 고유 ID")
    speaker: str = Field(description="작성자 닉네임, 유추가 불가능하면 '익명'으로 기입")
    product_name: str = Field(description="정식 화장품 상품 명칭")
    brand_name: str = Field(description="화장품 브랜드명 (예: 차앤박, 이니스프리, 에뛰드 등)")
    category: str = Field(description="상품 카테고리 (예: 베이스메이크업, 스킨케어, 선케어 등)")
    sentiment_label: str = Field(description="문장의 감성 상태 - 오직 '긍정', '부정', '중립' 중 하나만 입력")
    display_name: str = Field(description="분석된 피부 속성 특징 (예: 자극성, 수분감, 발림성, 진정 등)")

class BatchReviewAnalysis(BaseModel):
    results: List[ReviewMetadata]


# 3. 🛠️ DB DDL 자동 감지 및 칼럼 확장 함수 (중복 에러 방어막 강화 버전)
def check_and_prepare_ddl(cursor, connection):
    print("🔍 [인프라 체크] 테이블 칼럼 구조 검사 중...")
    cursor.execute("DESCRIBE `review_aspect_sentences`")
    existing_columns = [row["Field"] for row in cursor.fetchall()]
    
    # 추가해야 할 전체 메타데이터 칼럼 명세 정의
    required_columns = {
        "speaker": "ALTER TABLE `review_aspect_sentences` ADD COLUMN `speaker` varchar(50) DEFAULT NULL COMMENT 'AI 추출: 작성자 닉네임'",
        "product_name": "ALTER TABLE `review_aspect_sentences` ADD COLUMN `product_name` varchar(255) DEFAULT NULL COMMENT 'AI 추출: 정식 상품명 (중복 제거용)'",
        "brand_name": "ALTER TABLE `review_aspect_sentences` ADD COLUMN `brand_name` varchar(100) DEFAULT NULL COMMENT 'AI 추출: 브랜드명 (1단계 필터링용)'",
        "category": "ALTER TABLE `review_aspect_sentences` ADD COLUMN `category` varchar(100) DEFAULT NULL COMMENT 'AI 추출: 카테고리 (1단계 필터링용)'",
        "sentiment_label": "ALTER TABLE `review_aspect_sentences` ADD COLUMN `sentiment_label` varchar(20) DEFAULT NULL COMMENT 'AI 추출: 감성 결과 (긍정/부정/중립)'",
        "display_name": "ALTER TABLE `review_aspect_sentences` ADD COLUMN `display_name` varchar(100) DEFAULT NULL COMMENT 'AI 추출: 분석 속성 (자극성/수분감 등)'"
    }
    
    altered_any = False
    
    # 이미 존재하는 칼럼은 건너뛰고 없는 칼럼만 하나씩 안전하게 추가(ADD)합니다.
    for col_name, alter_sql in required_columns.items():
        if col_name not in existing_columns:
            print(f"🚧 [{col_name}] 칼럼이 존재하지 않아 안전하게 생성을 시작합니다...")
            cursor.execute(alter_sql)
            connection.commit()
            print(f"✅ [{col_name}] 칼럼 추가 완료.")
            altered_any = True

    # 하이브리드 고속 필터용 복합 인덱스가 인덱스 목록에 있는지 확인 후 추가
    cursor.execute("SHOW INDEX FROM `review_aspect_sentences`")
    existing_indexes = [row["Key_name"] for row in cursor.fetchall()]
    
    if "idx_ai_hybrid_filter" not in existing_indexes:
        print("⚡ 하이브리드 고속 필터용 복합 인덱스(idx_ai_hybrid_filter) 생성을 시작합니다...")
        try:
            cursor.execute("""
                ALTER TABLE `review_aspect_sentences` 
                ADD INDEX `idx_ai_hybrid_filter` (`brand_name`, `sentiment_label`, `category`)
            """)
            connection.commit()
            print("🚀 [인덱스 생성 완료] idx_ai_hybrid_filter 복합 인덱스가 세팅되었습니다.\n")
        except Exception as idx_err:
            print(f"ℹ️ 인덱스 생성 건너뜀 또는 에러: {idx_err}\n")
    else:
        print("✅ [인덱스 체크 완료] 복합 인덱스가 이미 최적화되어 존재합니다.\n")
        
    if not altered_any:
        print("✨ [체크 완료] 모든 AI 메타데이터 인프라가 중복 없이 완벽히 준비되어 있습니다.\n")

# 4. 📡 vLLM 메인 포트 기반 대량 문장 일괄 구조화 함수 (1406 에러 완벽 차단 최종본)
def analyze_review_batch(batch_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    schema_str = json.dumps(BatchReviewAnalysis.model_json_schema(), ensure_ascii=False, indent=2)
    
    user_payload_items = []
    for row in batch_rows:
        user_payload_items.append(f"[ID: {row['aspect_sentence_id']}] {row['separated_sentence']}")
    user_payload = "\n".join(user_payload_items)
    
    system_instruction = f"""{NO_THINK_SYSTEM_PROMPT}
당신은 대한민국 최고의 화장품 리뷰 분석가입니다.
전달받은 리뷰 문장들을 개별 분석하여 아래 제공된 JSON Schema 형식의 객체로 반환해야 합니다.

⚠️ [치명적인 규칙 - 반드시 준수할 것]
1. 출력하는 JSON의 결과 배열 내 모든 원소는 반드시 'aspect_sentence_id', 'speaker', 'product_name', 'brand_name', 'category', 'sentiment_label', 'display_name'이라는 7개의 영문 키(Key)를 정확하게 가지고 있어야 합니다.
2. 절대로 영문 키 명칭을 바꾸거나, 한국어로 번역하거나, 임의로 일부 키를 누락하지 마십시오.
3. 분석 속성 특징인 'display_name' 값은 키가 아니라 값(Value) 공간에 할당하십시오.

JSON Schema 규격:
{schema_str}"""

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": f"다음 ID별 리뷰 문장들을 일괄 분석하여 results 배열을 생성하세요. 절대 규칙을 위반하지 마십시오:\n{user_payload}"}
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": config.get("default_max_tokens", 1024)
    }
    
    try:
        with get_httpx_client(timeout=180.0) as client:
            resp = client.post(TARGET_URL, json=payload, headers={"Connection": "close"})
            resp.raise_for_status()
            res = resp.json()
            
            raw_content = res["choices"][0]["message"]["content"] or ""
            clean_content = clean_think_tags(raw_content, show_think=False)
            
            try:
                raw_json_dict = json.loads(clean_content)
                results_list = raw_json_dict.get("results", [])
                
                sanitized_results = []
                for item in results_list:
                    if not isinstance(item, dict): 
                        continue
                    if "aspect_sentence_id" not in item: 
                        continue
                        
                    # 💡 [글자수 초과 에러(1406) 원천 차단] DB 칼럼 한계 크기에 맞춰 안전하게 강제 절단합니다.
                    raw_speaker = str(item.get("speaker", item.get("작성자", "익명")))
                    raw_p_name = str(item.get("product_name", item.get("상품명", "일반 상품")))
                    raw_b_name = str(item.get("brand_name", item.get("브랜드", "미분류")))
                    raw_cat = str(item.get("category", item.get("카테고리", "미분류")))
                    raw_sent = str(item.get("sentiment_label", item.get("감성", "중립")))
                    raw_disp = str(item.get("display_name", "미분류"))

                    sanitized_item = {
                        "aspect_sentence_id": int(item["aspect_sentence_id"]),
                        # 확장된 DB 스키마 크기(255)보다 작은 안전 영역에서 무조건 절단
                        "speaker": raw_speaker[:240],         
                        "product_name": raw_p_name[:240],    
                        "brand_name": raw_b_name[:90],       
                        "category": raw_cat[:90],           
                        "sentiment_label": raw_sent[:15],    
                        "display_name": raw_disp[:90]        
                    }
                    sanitized_results.append(sanitized_item)
                
                fixed_json_str = json.dumps({"results": sanitized_results})
                parsed_data = BatchReviewAnalysis.model_validate_json(fixed_json_str)
                
            except Exception as json_parse_err:
                print(f"ℹ️ AI 응답 1차 유연화 가공 실패, 정석 파싱 시도: {json_parse_err}")
                parsed_data = BatchReviewAnalysis.model_validate_json(clean_content)
            
            update_data = []
            for item in parsed_data.results:
                update_data.append({
                    "speaker": item.speaker,
                    "product_name": item.product_name,
                    "brand_name": item.brand_name,
                    "category": item.category,
                    "sentiment_label": item.sentiment_label,
                    "display_name": item.display_name,
                    "aspect_sentence_id": item.aspect_sentence_id
                })
            return update_data
            
    except Exception as e:
        print(f"⚠️ 현재 배치 구조화 분석 오류 발생: {e}")
        return []




# 5. 🚀 파이프라인 메인 오케스트레이션 엔진
def run_pipeline():
    print_section_header("11단계 배치 구조화 기반 DB 벌크 업데이트 자동화 파이프라인")
    
    connection = pymysql.connect(**DB_CONFIG)
    try:
        with connection.cursor() as cursor:
            # DDL 구조 검사 및 확장 자동 수행 (이미 구축되었으므로 검사만 통과함)
            check_and_prepare_ddl(cursor, connection)
            
            # 메타데이터 칼럼이 비어 있는(NULL) 대상 문장들을 순차 수집
            sql_select = """
                SELECT aspect_sentence_id, separated_sentence 
                FROM `review_aspect_sentences` 
                WHERE `brand_name` IS NULL OR `sentiment_label` IS NULL
                ORDER BY `aspect_sentence_id` ASC
            """
            cursor.execute(sql_select)
            unprocessed_rows = cursor.fetchall()
            
            total_count = len(unprocessed_rows)
            if total_count == 0:
                print("✨ 모든 리뷰 데이터가 가공 및 동기화 완료된 상태입니다.")
                return
                
            print(f"📦 총 {total_count}건의 구조화 대상 문장을 발견했습니다. {BATCH_SIZE}건씩 순차 처리를 시작합니다.")
            
            # 대량의 데이터를 BATCH_SIZE 단위로 쪼개어 루프 처리
            for i in range(0, total_count, BATCH_SIZE):
                batch_rows = unprocessed_rows[i:i + BATCH_SIZE]
                print(f"\n🔄 [{i + len(batch_rows)}/{total_count}] AI 배치 구조화 추론 진행 중...")
                
                t_start = time.time()
                update_payloads = analyze_review_batch(batch_rows)
                t_end = time.time()
                
                if not update_payloads:
                    print(f"⚠️ 현재 묶음 배치의 AI 결과 분석이 무효하여 패스합니다.")
                    continue
                
                # executemany 기반의 고속 벌크 갱신 쿼리 (기존 컬럼 및 벡터 완전 보존)
                sql_update = """
                    UPDATE `review_aspect_sentences` 
                    SET `speaker` = %(speaker)s,
                        `product_name` = %(product_name)s,
                        `brand_name` = %(brand_name)s,
                        `category` = %(category)s,
                        `sentiment_label` = %(sentiment_label)s,
                        `display_name` = %(display_name)s
                    WHERE `aspect_sentence_id` = %(aspect_sentence_id)s
                """
                
                updated_cnt = cursor.executemany(sql_update, update_payloads)
                connection.commit()  # 물리 디스크 동기화
                
                print(f"⚡ [Bulk Update 완료] {updated_cnt}건 정형 인덱싱 성공! (추론 속도: {t_end - t_start:.2f}초)")
                
    except Exception as pipeline_err:
        print(f"❌ 파이프라인 가동 오류로 인해 롤백을 수행합니다: {pipeline_err}")
        connection.rollback()
    finally:
        if connection and connection.open:
            connection.close()
            print("\n🔒 안전하게 데이터베이스 세션을 단절했습니다.")


if __name__ == "__main__":
    run_pipeline()
