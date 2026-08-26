import os
import re
import time
import pymysql
import pandas as pd
from soynlp.normalizer import emoticon_normalize
from datetime import datetime

# 1. 🗄️ 데이터베이스 연결 정보 설정
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "192.168.0.8"),
    "user": os.getenv("DB_USER", "GP"),
    "password": os.getenv("DB_PASSWORD", "GP123!"),
    "database": "oliview_project",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor
}

# 2. 🛠️ 이모지 및 특수문자 완벽 박멸 전처리 함수
def preprocess_text(text):
    if pd.isna(text) or not str(text).strip():
        return ""

    text = str(text).strip()

    # [1단계] 스마트폰 컬러 이모지 제거
    emoji_pattern = re.compile(
        "[" "\U00010000-\U0010FFFF" "\u2000-\u3300" "]+", flags=re.UNICODE
    )
    text = emoji_pattern.sub("", text)

    # [2단계] 순수 한글, 숫자, 필수 문장부호만 남기기
    cleaned_text = re.sub(r"[^가-힣0-9!?.,\s]", "", text)

    # [3단계] 무분별한 자음/모음 반복 줄이기
    normalized_text = emoticon_normalize(cleaned_text, num_repeats=2)

    # [4단계] 연속된 공백 청소
    final_text = re.sub(r"\s+", " ", normalized_text).strip()

    return final_text

# 3. 🔄 마지막으로 전처리한 review_id 가져오는 함수 (변경된 테이블명 반영)
def get_last_processed_id(connection):
    history_file = "last_processed_id.txt"
    
    # 1순위: 로컬 기록 파일이 존재하면 해당 ID 반환
    if os.path.exists(history_file):
        with open(history_file, "r") as f:
            try:
                file_id = int(f.read().strip())
                if file_id > 0:
                    return file_id
            except ValueError:
                pass
                
    # 2순위: DB의 review_preprocessing 테이블에서 가장 큰 ID 확인 (과거 데이터 추적용)
    with connection.cursor() as cursor:
        cursor.execute("SELECT MAX(review_id) as max_id FROM review_preprocessing")
        result = cursor.fetchone()
        if result and result["max_id"] is not None:
            return int(result["max_id"])
            
    # 3순위: 완전히 처음 시작하는 경우 0번부터 시작 (과거 데이터부터 처리)
    return 0

# 4. 💾 마지막으로 전처리한 review_id 저장하는 함수
def save_last_processed_id(review_id):
    history_file = "last_processed_id.txt"
    with open(history_file, "w") as f:
        f.write(str(review_id))

# 5. 🚀 메인 실시간 전처리 프로세스
def run_realtime_preprocessing():
    try:
        connection = pymysql.connect(**DB_CONFIG)
        
        # 시작 지점 ID 가져오기
        last_id = get_last_processed_id(connection)
        
        if last_id == 0:
            print("📜 전처리 기록이 없습니다. 데이터베이스 내 모든 과거 데이터부터 전처리를 시작합니다.")
        else:
            print(f"🔄 마지막 전처리 확인 지점 (review_id: {last_id}) 이후부터 전처리를 재개합니다.")
        
        save_last_processed_id(last_id)

        while True:
            with connection.cursor() as cursor:
                # [단계 1] 전처리에 필요한 최소한의 컬럼(review_id, review_content)만 효율적으로 조회
                sql_select = """
                    SELECT review_id, review_content
                    FROM reviews 
                    WHERE review_id > %s 
                    ORDER BY review_id ASC 
                    LIMIT 500
                """
                cursor.execute(sql_select, (last_id,))
                new_reviews = cursor.fetchall()

                # 신규 및 과거 데이터가 더 이상 없으면 실시간 대기 모드로 진입
                if not new_reviews:
                    time.sleep(5)
                    continue

                print(f"📦 전처리 대상 데이터 {len(new_reviews)}건 확보 (현재 review_id: {last_id} 이후 처리 중...)")

                # 이번 배치에서 읽어온 원본 데이터 중 가장 큰 review_id 확보 (추후 업데이트 및 마커용)
                max_id_in_batch = int(new_reviews[-1]["review_id"])

                # DataFrame 변환 및 전처리 함수 적용
                df = pd.DataFrame(new_reviews)
                df["cleaned_content"] = df["review_content"].apply(preprocess_text)

                # 내용이 완전히 비어버린 리뷰 제외 (공백만 남은 리뷰 필터링)
                df_filtered = df[df["cleaned_content"] != ""]

                # [단계 2] 변경된 테이블(review_preprocessing)에 맞춤형 대량 삽입 (Bulk Insert)
                if not df_filtered.empty:
                    sql_insert = """
                        INSERT INTO review_preprocessing (
                            review_id, cleaned_content
                        ) VALUES (%s, %s)
                        ON DUPLICATE KEY UPDATE 
                            cleaned_content = VALUES(cleaned_content)
                    """
                    
                    # 튜플화 과정에서 NaN 값을 검사하여 안전하게 None으로 치환 (에러 원천 차단)
                    insert_data = [
                        (
                            None if pd.isna(row["review_id"]) else row["review_id"],
                            None if pd.isna(row["cleaned_content"]) else row["cleaned_content"]
                        )
                        for _, row in df_filtered.iterrows()
                    ]
                    
                    cursor.executemany(sql_insert, insert_data)

                # [추가 단계] DDL 연동: 배치 안의 모든 원본 리뷰에 전처리 완료 시각(preprocessed_at) 업데이트
                sql_update_status = """
                    UPDATE reviews 
                    SET preprocessed_at = %s 
                    WHERE review_id > %s AND review_id <= %s
                """
                current_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute(sql_update_status, (current_now, last_id, max_id_in_batch))
                
                # 모든 DB 반영 사항 트랜잭션 커밋
                connection.commit()

                # [단계 3] 기준점 갱신 및 기록
                last_id = max_id_in_batch
                save_last_processed_id(last_id)
                
                print(f"   ↳ 🎉 전처리 완료 후 테이블 반영 및 원본 상태 업데이트 완료. (최신 마커 ID: {last_id})")

    except KeyboardInterrupt:
        print("\n🛑 사용자에 의해 전처리 모니터링이 중단되었습니다.")
    except Exception as e:
        print(f"❌ 에러 발생: {e}")
    finally:
        if 'connection' in locals() and connection.open:
            connection.close()
            print("🔌 데이터베이스 연결 종료.")

if __name__ == "__main__":
    run_realtime_preprocessing()
