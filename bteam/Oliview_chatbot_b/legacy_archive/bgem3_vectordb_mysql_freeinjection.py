import os
import re
import time
import json
import httpx  # 🔗 로컬 bge-m3 데몬과의 REST API 통신을 위해 사용
import pymysql
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo  # ⏱️ 시간대 강제 지정을 위한 라이브러리

# 1. 🗄️ 데이터베이스 및 로컬 bge-m3 임베딩 서버 설정 정보
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "192.168.0.8"),
    "user": os.getenv("DB_USER", "GP"),
    "password": os.getenv("DB_PASSWORD", "GP123!"),
    "database": "oliview_project",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor
}

# 📡 실습 팩 config.json 기준 bge-m3 임베딩 데몬 주소 세팅
EMBEDDING_SERVER_URL = os.getenv("EMBEDDING_SERVER_URL", "http://192.168.0.151:8090/v1/embeddings")
MODEL_NAME = "bge-m3"  # 가용 임베딩 모델 ID

# 2. 🧠 로컬 bge-m3 데몬 기반 1024차원 임베딩 생성 함수 (기존 구조 완벽 대칭)
def get_embedding(text):
    try:
        payload = {
            "model": MODEL_NAME,
            "input": [text]
        }
        # 실습 팩 수트의 표준 httpx 통신 규격 적용 (안정적인 타임아웃 30초 설정)
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(EMBEDDING_SERVER_URL, json=payload, headers={"Connection": "close"})
            resp.raise_for_status()
            
            res = resp.json()
            # 기존 response.data[0].embedding 구조와 1:1 완벽 대칭 매핑
            return res["data"][0]["embedding"]
    except Exception as e:
        print(f"⚠️ 임베딩 생성 중 오류 발생: {e}")
        return None

# 3. 🚀 메인 벡터 MySQL 직접 적재 프로세스
def build_mysql_vector_store():
    try:
        connection = pymysql.connect(**DB_CONFIG)
        
        # 커서 기반 대용량 페이징 처리 (0번 문장 ID부터 순차 추적)
        last_aspect_sentence_id = 0
        limit_size = 500  # 기존 배치 크기 500 유지
        
        print("🚀 MySQL 내부 테이블 직접 매핑 방식의 벡터 라이징을 시작합니다.")
        print(f"📡 [로컬 bge-m3 서버 연동]: {EMBEDDING_SERVER_URL}")
        
        while True:
            with connection.cursor() as cursor:
                # 뷰에서 aspect_sentence_id를 기준으로 정렬하여 가져오기
                sql_select = """
                    SELECT aspect_sentence_id, separated_sentence, product_id 
                    FROM vw_llm_analysis_source
                    WHERE aspect_sentence_id > %s
                    ORDER BY aspect_sentence_id ASC
                    LIMIT %s
                """
                cursor.execute(sql_select, (last_aspect_sentence_id, limit_size))
                batch_data = cursor.fetchall()
                
                if not batch_data:
                    print("🎉 모든 분석용 문장의 임베딩 벡터가 MySQL에 정상적으로 직접 적재되었습니다.")
                    break
                
                print(f"📦 뷰 데이터 {len(batch_data)}건 확보 (현재 aspect_sentence_id: {last_aspect_sentence_id} 이후 처리 중...)")
                
                update_data = []
                product_ids_in_batch = set()
                
                for row in batch_data:
                    sentence = row["separated_sentence"]
                    sentence_id = row["aspect_sentence_id"]
                    
                    if not sentence or not str(sentence).strip():
                        continue
                    
                    # 💡 로컬 내부망 통신을 통해 실시간 bge-m3 1024차원 벡터 데이터 추출
                    vector_list = get_embedding(str(sentence))
                    
                    if vector_list is not None:
                        # 💡 Python의 리스트 구조를 MySQL JSON/TEXT 칼럼에 넣기 위해 문자열 형태로 가공
                        vector_json_str = json.dumps(vector_list)
                        update_data.append((vector_json_str, sentence_id))
                        
                        if row["product_id"]:
                            product_ids_in_batch.add(int(row["product_id"]))
                
                # MySQL 테이블에 생성한 벡터 정보 대량 일괄 반영 (Bulk Update)
                if update_data:
                    sql_update_vector = """
                        UPDATE review_aspect_sentences 
                        SET embedding_vector = %s 
                        WHERE aspect_sentence_id = %s
                    """
                    cursor.executemany(sql_update_vector, update_data)
                
                # ⏱️ DDL 연동: 가동이 끝난 상품 정보 테이블의 llm_analyzed_at 칼럼 한국 시간 업데이트
                current_now = datetime.now(ZoneInfo("Asia/Seoul")).strftime('%Y-%m-%d %H:%M:%S')
                if product_ids_in_batch:
                    format_strings = ','.join(['%s'] * len(product_ids_in_batch))
                    sql_update_products = f"""
                        UPDATE products 
                        SET llm_analyzed_at = %s 
                        WHERE product_id IN ({format_strings})
                    """
                    cursor.execute(sql_update_products, [current_now] + list(product_ids_in_batch))
                
                # 트랜잭션 정상 커밋
                connection.commit()
                
                # 다음 루프 동작을 위한 마커 ID 추적 갱신
                last_aspect_sentence_id = int(batch_data[-1]["aspect_sentence_id"])
                print(f"   ↳ 💾 {len(update_data)}개 문장 벡터 추출 및 MySQL 테이블 반영 완료. (최신 문장 ID: {last_aspect_sentence_id})")
                
                # 로컬 자원이므로 무의미한 대기 차단 및 처리 속도 향상을 위해 휴식 시간을 0.05초로 단축
                time.sleep(0.05)
                
    except Exception as e:
        if 'connection' in locals():
            connection.rollback()
        print(f"❌ 프로세스 작동 중 치명적 에러 발생 (롤백 완료): {e}")
    finally:
        if 'connection' in locals() and connection.open:
            connection.close()
            print("🔌 데이터베이스 연결 안전 종료.")

if __name__ == "__main__":
    build_mysql_vector_store()
