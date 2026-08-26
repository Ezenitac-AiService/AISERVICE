import json
import os
import pandas as pd
import mysql.connector
from datetime import datetime

# 💡 원격 DB 접속 정보 (본인 환경에 맞게 수정하세요)
DB_CONFIG = {
    'host': '192.168.0.8',      # 원격 DB IP 주소
    'user': 'GP',    # DB 아이디
    'password': 'GP123!',# DB 비밀번호
    'database': 'oliview_project',# 사용할 데이터베이스 이름
    'port': 3306,
    'charset': 'utf8mb4'
}

def get_db_mapping(product_code):
    """
    DB에서 해당 상품의 진짜 숫자형 product_id와 
    { '옵션번호(option_number)': '옵션ID(product_option_id)' } 매핑 사전을 가져옵니다.
    """
    mapping = { 'product_id': None, 'options': {} }
    
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        
        query = """
            SELECT p.product_id, po.product_option_id, po.option_number 
            FROM products p
            LEFT JOIN product_options po ON p.product_id = po.product_id
            WHERE p.product_code = %s
        """
        cursor.execute(query, (product_code,))
        rows = cursor.fetchall()
        
        for row in rows:
            # 1. 숫자형 product_id 저장
            if mapping['product_id'] is None:
                mapping['product_id'] = row['product_id']
                
            # 2. 옵션 번호 매핑 (예: "018" -> 15)
            if row['option_number'] is not None and row['product_option_id'] is not None:
                opt_num = str(row['option_number']).strip()
                mapping['options'][opt_num] = row['product_option_id']
                
    except mysql.connector.Error as err:
        print(f"❌ DB 연결/조회 에러: {err}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()
            
    return mapping


def process_reviews_from_json(json_filename, csv_filename):
    # 1. JSON 파일 읽기
    try:
        with open(json_filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"[{json_filename}] 파일을 찾을 수 없습니다.")
        return
        
    raw_reviews = data.get("reviews", [])
    crawl_info = data.get("crawlInfo", {})
    product_code = crawl_info.get("goodsNumber", "") # "A000000202425"
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 2. DB에서 상품 ID 및 옵션 번호 매핑 정보 가져오기
    print(f"🔍 DB에서 [{product_code}] 상품 정보를 불러옵니다...")
    db_data = get_db_mapping(product_code)
    real_product_id = db_data['product_id']
    option_mapping = db_data['options']
    
    if real_product_id is None:
        print("⚠️ 경고: DB의 products 테이블에 해당 상품 코드가 존재하지 않습니다. 먼저 상품을 등록해주세요.")
        return
        
    print(f"  -> 상품 DB ID: {real_product_id}")
    print(f"  -> {len(option_mapping)}개의 옵션 번호 매핑 고리를 찾았습니다!")

    # 3. 기존 CSV 데이터 불러오기 (시간 갱신 목적)
    existing_data = {}
    if os.path.exists(csv_filename):
        df_existing = pd.read_csv(csv_filename)
        for _, row in df_existing.iterrows():
            existing_data[str(row['review_id'])] = row.to_dict()
            
    processed_list = []
    
    for rev in raw_reviews:
        review_id = str(rev.get("reviewId", ""))
        
        # ⭐️ JSON의 itemNumber (옵션 번호) 추출
        goods_dto = rev.get("goodsDto", {})
        item_number = str(goods_dto.get("itemNumber", "")).strip()
        
        # 사전에 해당 옵션 번호가 있으면 옵션 DB ID 반환, 없으면 None(빈값)
        matched_option_id = option_mapping.get(item_number, None)
        
        content = rev.get("content", "")
        score = rev.get("reviewScore", 0)
        date = rev.get("createdDateTime", "")
        
        # 시간 갱신 로직
        if review_id in existing_data:
            first_collected = existing_data[review_id]['first_collected_at']
            last_collected = current_time
        else:
            first_collected = current_time
            last_collected = current_time
            
        # ERD 구조에 맞춘 최종 데이터
        processed_list.append({
            "review_id": review_id,
            "product_id": real_product_id,           # 문자열 코드가 아닌 DB의 숫자 ID
            "product_option_id": matched_option_id,  # 매칭된 옵션의 숫자 ID
            "review_content": content,
            "review_score": score,
            "review_date": date,
            "first_collected_at": first_collected,
            "last_collected_at": last_collected
        })
        
    # 4. CSV 저장
    df_new = pd.DataFrame(processed_list)
    df_new.to_csv(csv_filename, index=False, encoding="utf-8-sig")
    print(f"✅ 총 {len(df_new)}개의 리뷰 데이터가 옵션 번호 기준으로 완벽하게 매칭되어 저장되었습니다.")

if __name__ == "__main__":
    INPUT_JSON = "oliveyoung_A000000202425_raw_reviews.json"
    OUTPUT_CSV = "oliveyoung_reviews_final.csv"
    
    process_reviews_from_json(INPUT_JSON, OUTPUT_CSV)