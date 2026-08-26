import csv
import sys
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# ============================================================
# 프로젝트 경로 및 DBManager 설정
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 세 번째 파일에서 생성한 DBManager 임포트
from common.db_manager2 import DBManager

def crawl_unique_brands():
    # 1. 'Categories_ID.csv'에서 카테고리 고유번호 읽기
    category_ids = []
    try:
        with open('categories_crawling/Categories_ID.csv', mode='r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row.get('Intermediate_Category_ID'):
                    category_ids.append(row['Intermediate_Category_ID'])
    except FileNotFoundError:
        print("⚠️ 'Categories_ID.csv' 파일을 찾을 수 없습니다. 파일명과 위치를 확인해 주세요.")
        return

    unique_brands = {}
    print(f"총 {len(category_ids)}개의 카테고리를 순회하며 브랜드를 수집합니다...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        
        # 2. 각 카테고리 페이지 순회
        for idx, cat_id in enumerate(category_ids, 1):
            url = f"https://www.oliveyoung.co.kr/store/display/getMCategoryList.do?dispCatNo={cat_id}"
            print(f"[{idx}/{len(category_ids)}] 카테고리 ID {cat_id} 탐색 중...")
            
            try:
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)
                
                html = page.content()
                soup = BeautifulSoup(html, 'html.parser')
                
                # 3. 브랜드 리스트 추출 (ul.brand_list > li > input 구조)
                brand_inputs = soup.select('ul.brand_list > li > input[type="checkbox"]')
                
                for brand in brand_inputs:
                    brand_id = brand.get('value')
                    
                    # [핵심 수정 부분] 속성값이 아닌, 눈에 보이는 label 텍스트(풀네임)를 가져옵니다.
                    label_tag = brand.find_next_sibling('label')
                    if label_tag:
                        brand_name = label_tag.get_text(strip=True)
                    else:
                        brand_name = brand.get('data-brndnm') # 예비용
                    
                    if brand_id and brand_name:
                        unique_brands[brand_id] = brand_name
                        
            except Exception as e:
                print(f"카테고리 {cat_id} 처리 중 오류 발생: {e}")
                
        browser.close()

    # 4. 수집된 브랜드 데이터를 DB로 바로 저장
    save_brands_to_db(unique_brands)


def save_brands_to_db(brands_dict):
    if not brands_dict:
        print("추출된 브랜드 데이터가 없습니다.")
        return
        
    db = DBManager()
    collected_at = datetime.now()
    
    try:
        db.connect()
        
        sql = """
            INSERT INTO brands (
                brand_code,
                brand_name,
                first_collected_at,
                last_seen_at,
                is_active
            )
            VALUES (%s, %s, %s, %s, 1)
            ON DUPLICATE KEY UPDATE
                brand_name = VALUES(brand_name),
                last_seen_at = VALUES(last_seen_at),
                is_active = 1
        """
        
        brand_data = [
            (b_id, b_name, collected_at, collected_at)
            for b_id, b_name in brands_dict.items()
        ]
        
        db.executemany(sql, brand_data)
        db.commit()
        
        print(f"✅ 총 {len(brands_dict)}개의 중복 없는 고유 브랜드 데이터가 DB에 성공적으로 저장되었습니다!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ DB 저장 중 오류가 발생했습니다: {e}")
        
    finally:
        db.close()


if __name__ == "__main__":
    crawl_unique_brands()