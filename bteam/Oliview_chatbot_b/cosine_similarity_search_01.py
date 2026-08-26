import os
import time
import json
import httpx
import pymysql
import numpy as np  # ⚡ 초고속 코사인 유사도 행렬 연산을 위한 라이브러리
from datetime import datetime

# 1. 🗄️ 데이터베이스 및 로컬 bge-m3 임베딩 서버 설정 정보
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "192.168.0.8"),
    "user": os.getenv("DB_USER", "GP"),
    "password": os.getenv("DB_PASSWORD", "GP123!"),
    "database": "oliview_project",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor
}

EMBEDDING_SERVER_URL = os.getenv("EMBEDDING_SERVER_URL", "http://192.168.0.151:8090/v1/embeddings")
MODEL_NAME = "bge-m3"

# 2. 🧠 질문(Query) 텍스트를 로컬 bge-m3를 통해 1024차원 벡터로 변환하는 함수 (파싱 안전성 극대화)
def get_query_embedding(query_text):
    try:
        payload = {"model": MODEL_NAME, "input": [query_text]}
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(EMBEDDING_SERVER_URL, json=payload, headers={"Connection": "close"})
            resp.raise_for_status()
            
            res = resp.json()
            
            # [케이스 1] OpenAI 호환 규격 딕셔너리로 오는 경우
            if isinstance(res, dict):
                if "data" in res and len(res["data"]) > 0:
                    data_entry = res["data"][0]
                    if isinstance(data_entry, dict) and "embedding" in data_entry:
                        return data_entry["embedding"]
                    elif isinstance(data_entry, list):
                        return data_entry
                if "embedding" in res:
                    return res["embedding"]
            
            # [케이스 2] 중첩 리스트 형태로 오는 경우 (예: [[0.1, 0.2, ...]])
            if isinstance(res, list) and len(res) > 0:
                if isinstance(res[0], list):
                    return res[0]
                return res
                
            return None
    except Exception as e:
        print(f"⚠️ 질문 임베딩 생성 실패: {e}")
        return None

# 3. 📐 수학적으로 가장 정확하고 빠른 고성능 코사인 유사도 연산 함수
def cosine_similarity(v1, v2):
    dot_product = np.dot(v1, v2)
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)
    if norm_v1 == 0 or norm_v2 == 0:
        return 0.0
    return float(dot_product / (norm_v1 * norm_v2))

# 4. 🚀 브랜드/감성 필터링 기반 하이브리드 벡터 검색 메인 함수
def search_similar_reviews(query_text, brand_filter=None, sentiment_filter=None, top_n=3):
    query_vector = get_query_embedding(query_text)
    if query_vector is None:
        print("❌ 질문 임베딩 결과가 올바르지 않아 검색을 중단합니다.")
        return []
    
    # 확실하게 1차원 실수형 벡터로 변환
    query_vector = np.array(query_vector, dtype=np.float32).flatten()
    
    # 💡 정상적인 1024차원 벡터인지 최종 검증
    if query_vector.shape[0] != 1024:
        print(f"❌ 임베딩 차원 에러 발생: 현재 차원 {query_vector.shape[0]}은 1024차원이 아닙니다. 서버 응답을 확인하세요.")
        return []
    
    try:
        connection = pymysql.connect(**DB_CONFIG)
        with connection.cursor() as cursor:
            
            sql_select = """
                SELECT 
                    ras.aspect_sentence_id,
                    ras.separated_sentence,
                    ras.embedding_vector,
                    vlas.product_name,
                    vlas.brand_name,
                    vlas.category,
                    vlas.review_score,
                    vlas.display_name,
                    vlas.sentiment_label
                FROM review_aspect_sentences ras
                JOIN vw_llm_analysis_source vlas ON ras.aspect_sentence_id = vlas.aspect_sentence_id
                WHERE ras.embedding_vector IS NOT NULL
            """
            
            params = []
            if brand_filter:
                sql_select += " AND vlas.brand_name = %s"
                params.append(brand_filter)
            if sentiment_filter:
                sql_select += " AND vlas.sentiment_label = %s"
                params.append(sentiment_filter)
                
            t_db_start = time.time()
            cursor.execute(sql_select, params)
            candidates = cursor.fetchall()
            t_db_end = time.time()
            
            if not candidates:
                print("🔍 필터링 조건에 부합하는 리뷰 데이터가 존재하지 않습니다.")
                return []
                
            print(f"📦 [필터링 완료] 전체 데이터 중 {len(candidates)}건의 후보군을 대상으로 초고속 벡터 연산을 수행합니다. (DB 조회: {t_db_end-t_db_start:.3f}초)")
            
            search_results = []
            t_calc_start = time.time()
            
            for row in candidates:
                try:
                    # DB 벡터 복원 및 실수형 평탄화
                    target_vector = np.array(json.loads(row["embedding_vector"]), dtype=np.float32).flatten()
                    if target_vector.shape[0] != 1024:
                        continue
                except Exception:
                    continue
                
                sim_score = cosine_similarity(query_vector, target_vector)
                
                search_results.append({
                    "product_name": row["product_name"],
                    "brand_name": row["brand_name"],
                    "category": row["category"],
                    "review_score": row["review_score"],
                    "separated_sentence": row["separated_sentence"],
                    "display_name": row["display_name"],
                    "sentiment_label": row["sentiment_label"],
                    "similarity": sim_score
                })
                
            search_results.sort(key=lambda x: x["similarity"], reverse=True)
            top_results = search_results[:top_n]
            t_calc_end = time.time()
            
            print(f"⚡ [연산 완료] 코사인 유사도 랭킹 산출 완료! (벡터 연산: {t_calc_end-t_calc_start:.3f}초)\n")
            return top_results
            
    except Exception as e:
        print(f"❌ 검색 프로세스 중 에러 발생: {e}")
        return []
    finally:
        if 'connection' in locals() and connection.open:
            connection.close()

# 5. 🏃‍♂️ 실제 서비스 구동 테스트
if __name__ == "__main__":
    USER_QUERY = "트러블 안나고 순하면서 피부 진정에 좋은 쿠션팩트 찾고 있어"
    BRAND_COND = "차앤박"
    SENTIMENT_COND = "긍정"
    
    print(f"🔍 [유저 질문]: '{USER_QUERY}'")
    print(f"🎯 [필터 조건]: 브랜드='{BRAND_COND}', 감성='{SENTIMENT_COND}'\n")
    
    results = search_similar_reviews(
        query_text=USER_QUERY,
        brand_filter=BRAND_COND,
        sentiment_filter=SENTIMENT_COND,
        top_n=3
    )
    
    for idx, res in enumerate(results, 1):
        print(f"🏆 [추천 {idx}순위] 유사도 평점: {res['similarity']:.4f} ({int(res['similarity']*100)}% 매칭)")
        print(f"   📦 상품명  : [{res['brand_name']}] {res['product_name']} ({res['category']})")
        print(f"   ⭐ 고객평점: {res['review_score']}점 | AI 분석 속성: {res['display_name']} ({res['sentiment_label']})")
        print(f"   🎯 매칭문장: \"{res['separated_sentence']}\"")
        print("-" * 75)
