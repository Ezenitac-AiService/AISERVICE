import os
import time
import json
import httpx
import pymysql
import numpy as np  # ⚡ 초고속 코사인 유사도 행렬 연산을 위한 라이브러리
from datetime import datetime
from common import load_sample_config

# 1. 🗄️ 데이터베이스 설정 정보
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "192.168.0.8"),
    "user": os.getenv("DB_USER", "GP"),
    "password": os.getenv("DB_PASSWORD", "GP123!"),
    "database": "oliview_project",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor
}

# 📡 기존 성공 코드의 설정 로드 방식을 그대로 적용
config = load_sample_config()
SERVER_HOST = config["server_host"]
RERANK_PORT = config["rerank_port"]
EMBED_PORT = config.get("embed_port", 8090)

if not SERVER_HOST.startswith("http://") and not SERVER_HOST.startswith("https://"):
    BASE_URL = f"http://{SERVER_HOST}"
else:
    BASE_URL = SERVER_HOST

EMBEDDING_SERVER_URL = f"{BASE_URL}:{EMBED_PORT}/v1/embeddings"
RERANK_SERVER_URL = f"{BASE_URL}:{RERANK_PORT}/v1/embeddings"

EMBED_MODEL = "bge-m3"
RERANK_MODEL = "bge-reranker-v2-m3"


# 2. 🧠 [Stage 1] 8090 포트 기반 질문 벡터 변환 함수 (성공 규격 복원 완료)
def get_query_embedding(query_text):
    try:
        payload = {"input": query_text}
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(EMBEDDING_SERVER_URL, json=payload, headers={"Connection": "close"})
            resp.raise_for_status()
            res = resp.json()
            # 💡 [성공 코드 정밀 매핑] 'data'의 0번째 요소 내부 'embedding'을 추출해야 1차원 벡터가 됩니다.
            return res["data"][0]["embedding"]
    except Exception as e:
        print(f"⚠️ 1단계 질문 임베딩 생성 실패: {e}")
        return None



# 3. 🎯 [Stage 2] 8091 포트 기반 후보 문서들 벡터 획득 및 리랭킹 점수 계산 함수 (최종 완결본)
def get_rerank_scores(query_text, documents):
    try:
        with httpx.Client(timeout=15.0) as client:
            # 질문 벡터 획득
            r_q = client.post(RERANK_SERVER_URL, json={"input": query_text}, headers={"Connection": "close"}).json()
            
            # 💡 [성공 코드 구조 100% 복원] 'data' 리스트의 0번째 방 내부 'embedding'을 추출해야 에러가 나지 않습니다.
            raw_q = np.asarray(r_q["data"][0]["embedding"], dtype=np.float32)
            
            # 차원이 (토큰수, 1024) 형태인 2차원이면 토큰축(axis=0) 평균을 내어 (1024,)로 축소
            if raw_q.ndim == 2:
                q_vec = np.mean(raw_q, axis=0)
            else:
                q_vec = raw_q.flatten()

            # 후보 문장들 벡터 일괄 획득
            r_docs = client.post(RERANK_SERVER_URL, json={"input": documents}, headers={"Connection": "close"}).json()
            doc_datas = r_docs["data"]

            scores = []
            for d in doc_datas:
                # 💡 리스트 형태인 doc_datas 내부 요소 d에서 'embedding' 추출
                raw_d = np.asarray(d["embedding"], dtype=np.float32)
                
                # 문서 벡터도 마찬가지로 2차원 구조일 경우 토큰축 평균을 취해 (1024,) 벡터로 변환
                if raw_d.ndim == 2:
                    d_vec = np.mean(raw_d, axis=0)
                else:
                    d_vec = raw_d.flatten()
                
                # 고속 코사인 유사도 연산
                dot = np.dot(q_vec, d_vec)
                norm1 = np.linalg.norm(q_vec)
                norm2 = np.linalg.norm(d_vec)
                sim = float(dot / (norm1 * norm2)) if (norm1 * norm2) > 0 else 0.0
                scores.append(sim)
                
            return scores
    except Exception as e:
        print(f"⚠️ 2단계 교재식 리랭커 연산 실패: {e}")
        return None



# 4. 📐 코사인 유사도 기본 연산 함수 (1단계용)
def cosine_similarity(v1, v2):
    dot_product = np.dot(v1, v2)
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)
    if norm_v1 == 0 or norm_v2 == 0:
        return 0.0
    return float(dot_product / (norm_v1 * norm_v2))


# 5. 🚀 2단계(Two-Stage) 하이브리드 벡터 검색 메인 함수 (LIKE 필터 추가본)
def search_and_rerank_reviews(query_text, brand_filter=None, sentiment_filter=None, keyword_filter=None, fetch_k=20, top_n=3):
    raw_query_vector = get_query_embedding(query_text)
    if raw_query_vector is None:
        print("❌ 질문 임베딩 결과가 누락되어 검색을 종료합니다.")
        return []
    
    query_vector = np.asarray(raw_query_vector, dtype=np.float32).flatten()
    
    connection = None
    try:
        connection = pymysql.connect(**DB_CONFIG)
        with connection.cursor() as cursor:
            # 기본 SQL 쿼리문
            sql_select = """
                SELECT 
                    ras.aspect_sentence_id, ras.separated_sentence, ras.embedding_vector,
                    vlas.product_name, vlas.brand_name, vlas.category,
                    vlas.review_score, vlas.display_name, vlas.sentiment_label
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
                
            # 💡 [추가] 상품명(product_name) 또는 카테고리(category)에 키워드가 포함되어 있는지 LIKE 필터링 [1]
            if keyword_filter:
                sql_select += " AND (vlas.product_name LIKE %s OR vlas.category LIKE %s)"
                like_pattern = f"%{keyword_filter}%"
                params.append(like_pattern)
                params.append(like_pattern)
                
            cursor.execute(sql_select, params)
            candidates = cursor.fetchall()
            
            if not candidates:
                print(f"🔍 조건 및 키워드('{keyword_filter}')에 부합하는 리뷰 데이터가 없습니다.")
                return []
                
            # 1단계 코사인 유사도 연산 가동
                       
            stage1_results = []
            for row in candidates:
                try:
                    # DB 저장 문자열 파싱 및 벡터화
                    target_vector = np.asarray(json.loads(row["embedding_vector"]), dtype=np.float32).flatten()
                    
                    # 💡 [정밀 수정] .shape는 튜플을 반환하므로 .size == 1024 개수로 검증해야 안전합니다.
                    if target_vector.size != 1024: 
                        continue
                except Exception as eval_err: 
                    continue
                
                sim_score = cosine_similarity(query_vector, target_vector)
                stage1_results.append({**row, "cosine_sim": sim_score})

                
            # 유사도 내림차순 정렬 후 상위 fetch_k(20건) 1차 선별
            stage1_results.sort(key=lambda x: x["cosine_sim"], reverse=True)
            subset_candidates = stage1_results[:fetch_k]
            
            print(f"📦 [Stage 1 완료] 키워드 필터 적용 후 {len(candidates)}건 중 코사인 유사도 상위 {len(subset_candidates)}건 1차 선별 완료.")
            
            if not subset_candidates:
                print("⚠️ 코사인 유사도 연산 결과 1차 선별된 후보가 존재하지 않습니다.")
                return []
            
            # 2단계 정밀 재순위화 (Stage 2)
            rerank_docs = [row["separated_sentence"] for row in subset_candidates]
            
            print(f"🔥 [Stage 2 시작] 교재 9단계 메커니즘 가동, 1차 후보군 {len(rerank_docs)}건 정밀 재정렬 진행 중...")
            t_rerank_start = time.time()
            rerank_scores = get_rerank_scores(query_text, rerank_docs)
            t_rerank_end = time.time()
            
            if not rerank_scores:
                print("⚠️ 리랭킹 연산 오류로 인해 1단계 코사인 유사도 결과를 기반으로 최종 출력합니다.")
                rerank_scores = [row["cosine_sim"] for row in subset_candidates]
                
            final_reranked_results = []
            for i, row in enumerate(subset_candidates):
                final_reranked_results.append({
                    "product_name": row["product_name"],
                    "brand_name": row["brand_name"],
                    "category": row["category"],
                    "review_score": row["review_score"],
                    "separated_sentence": row["separated_sentence"],
                    "display_name": row["display_name"],
                    "sentiment_label": row["sentiment_label"],
                    "cosine_similarity": row["cosine_sim"],
                    "rerank_score": rerank_scores[i]
                })
                
                        # 리랭커 정밀 점수를 기준으로 내림차순 최종 재정렬
            final_reranked_results.sort(key=lambda x: x["rerank_score"], reverse=True)
            
            # 💡 [고도화: 상품명 기준 중복 제거 (De-duplication) 로직]
            unique_final_results = []
            seen_products = set()  # 이미 추천 목록에 담긴 상품명을 저장하는 집합
            
            for res in final_reranked_results:
                p_name = res["product_name"]
                
                # 이미 본 상품명이라면 최종 상위 결과에 담지 않고 패스(skip)합니다.
                if p_name in seen_products:
                    continue
                    
                seen_products.add(p_name)
                unique_final_results.append(res)
                
                # 유저가 요청한 top_n(예: 3개)만큼 서로 다른 상품이 채워지면 루프를 즉시 종료합니다.
                if len(unique_final_results) == top_n:
                    break
            
            print(f"⚡ [2단계 아키텍처 완료] 상품명 중복 제거 후 {top_n}개의 고유 상품 최종 선별 완료! (리랭커 연산: {t_rerank_end-t_rerank_start:.3f}초)\n")
            return unique_final_results  # 💡 중복이 제거된 고유 상품 리스트 반환

            
    except Exception as e:
        print(f"❌ 2단계 하이브리드 검색 중 오류 발생: {e}")
        return []
    finally:
        if connection and connection.open:
            connection.close()



# 6. 🏃‍♂️ 실제 서비스 구동 테스트
if __name__ == "__main__":
    USER_QUERY = "트러블 안나고 순하면서 피부 진정에 좋은 쿠션팩트 찾고 있어"
    BRAND_COND = "차앤박"
    SENTIMENT_COND = "긍정"
    KEYWORD_COND = "쿠션"  # 💡 SQL LIKE 문에 매핑될 필터 키워드
    
    print(f"🔍 [유저 질문]: '{USER_QUERY}'")
    print(f"🎯 [필터 조건]: 브랜드='{BRAND_COND}', 감성='{SENTIMENT_COND}', 키워드='{KEYWORD_COND}'\n")
    
    final_results = search_and_rerank_reviews(
        query_text=USER_QUERY,
        brand_filter=BRAND_COND,
        sentiment_filter=SENTIMENT_COND,
        keyword_filter=KEYWORD_COND,  # 💡 인자 추가
        fetch_k=20,
        top_n=3
    )
    
    for idx, res in enumerate(final_results, 1):
        print(f"🏆 [최종 추천 {idx}순위] 리랭커 매칭 점수: {res['rerank_score']:.4f}")
        print(f"   📊 (1단계 코사인 유사도 참고 점수: {res['cosine_similarity']:.4f})")
        print(f"   📦 상품명  : [{res['brand_name']}] {res['product_name']} ({res['category']})")
        print(f"   ⭐ 고객평점: {res['review_score']}점 | AI 분석 속성: {res['display_name']} ({res['sentiment_label']})")
        print(f"   🎯 매칭문장: \"{res['separated_sentence']}\"")
        print("-" * 75)


