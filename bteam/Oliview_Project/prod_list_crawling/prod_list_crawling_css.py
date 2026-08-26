import os
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import time
import random

# CSV 불러오기
try:
    brand_df = pd.read_csv(r'D:\bTEAM\Oliview\Oliview_Project\brand_crawling\Brand_ID.csv')
    cat_df = pd.read_csv(r'D:\bTEAM\Oliview\Oliview_Project\categories_crawling\Categories_ID.csv')
except FileNotFoundError as e:
    print(f"파일을 찾을 수 없습니다: {e}")
    exit()

def get_brand_id(brand_name):
    """브랜드 이름을 받아 Brand_ID.csv에서 고유 ID를 찾아 반환합니다."""
    match = brand_df[brand_df['Brand_Name'] == brand_name]
    if not match.empty:
        return match['Brand_ID'].iloc[0]
    return "ID_NOT_FOUND"

def scrape_all_categories(category_ids):
    """주어진 카테고리 ID 리스트를 순회하며 올리브영을 크롤링합니다."""
    scraped_dict = {}
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        for cat_id in category_ids:
            url = f"https://www.oliveyoung.co.kr/store/display/getCategoryShop.do?dispCatNo={cat_id}"
            print(f"카테고리 크롤링 진행 중: {cat_id}")
            
            try:
                # 1. 임의 사용자 에이전트 설정
                user_agents = [
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
                ]
                page.add_init_script(f"Object.defineProperty(navigator, 'userAgent', {{get: () => '{random.choice(user_agents)}'}})")

                # 2. 페이지 이동 전 임의 대기 추가 (human-like)
                time.sleep(random.uniform(2.0, 5.0)) # 2~5초 사이 대기

                page.goto(url)
                
                # 3. 타임아웃 시간 15초로 대기
                page.wait_for_selector('ul.cate_prd_list', timeout=15000) 
                html = page.content()
            except Exception as e:
                print(f"카테고리 {cat_id} 로딩 실패 (상품이 없거나 지연됨): {e}")
                continue

            soup = BeautifulSoup(html, 'html.parser')
            product_items = soup.select('ul.cate_prd_list > li')
            
            for item in product_items:
                try:
                    btn_zzim = item.select_one('button.btn_zzim')
                    if not btn_zzim:
                        continue
                        
                    product_code = btn_zzim.get('data-ref-goodsno', '').strip()
                    product_name = btn_zzim.get('data-ref-goodsnm', '').strip()
                    
                    # --- 3중 체크 방식의 브랜드명 추출 ---
                    # 1순위: 일반 상품의 속성('goodsrnd') 확인
                    brand_name = btn_zzim.get('data-ref-goodsrnd', '').strip()
                    
                    # 2순위: 아티스트 굿즈 등 특수 카테고리 속성('goodsbrand') 확인
                    if not brand_name:
                        brand_name = btn_zzim.get('data-ref-goodsbrand', '').strip()
                        
                    # 3순위: 둘 다 없으면 화면에 노출된 텍스트('span.tx_brand') 확인
                    if not brand_name:
                        brand_tag = item.select_one('span.tx_brand')
                        brand_name = brand_tag.text.strip() if brand_tag else ''
                    # ---------------------------------------------
                    
                    brand_id = get_brand_id(brand_name)
                    
                    a_tag = item.select_one('a')
                    category_id = a_tag.get('data-ref-dispcatno', '').strip() if a_tag else cat_id
                    product_url = a_tag.get('href', '') if a_tag else ''
                    
                    # --- [추가됨] 썸네일 이미지 URL 추출 ---
                    img_tag = item.select_one('.prd_thumb img')
                    image_url = img_tag.get('src', '').strip() if img_tag else ''
                    # ---------------------------------------------
                    
                    price_div = item.select_one('p.prd_price')
                    if price_div:
                        org_price_tag = price_div.select_one('span.tx_org span.tx_num')
                        cur_price_tag = price_div.select_one('span.tx_cur span.tx_num')
                        
                        product_price = org_price_tag.text.replace(',', '') if org_price_tag else (cur_price_tag.text.replace(',', '') if cur_price_tag else "0")
                        product_price_dc = cur_price_tag.text.replace(',', '') if cur_price_tag else product_price
                    else:
                        product_price, product_price_dc = "0", "0"

                    scraped_dict[product_code] = {
                        'product_code': product_code,
                        'category_id': category_id,
                        'brand_id': brand_id,
                        'brand_name': brand_name,
                        'product_name': product_name,
                        'product_price': int(product_price),
                        'product_price_dc': int(product_price_dc),
                        'product_url': product_url,
                        'image_url': image_url, # <--- 딕셔너리에 데이터 추가
                        'crawled_date': today_str
                    }
                    
                except Exception as e:
                    continue
                    
        browser.close()
        
    return list(scraped_dict.values())

def update_csv(new_data, filename='olive_young_products.csv'):
    """수집된 데이터를 CSV 파일에 병합합니다."""
    new_df = pd.DataFrame(new_data)
    if new_df.empty:
        print("수집된 데이터가 없습니다.")
        return

    new_df['product_code'] = new_df['product_code'].astype(str)

    if os.path.exists(filename):
        existing_df = pd.read_csv(filename)
        existing_df['product_code'] = existing_df['product_code'].astype(str)
        
        combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        
        final_df = combined_df.drop_duplicates(subset=['product_code'], keep='last')
        print(f"기존 파일에 {len(new_df)}개 검토 완료. (총 {len(final_df)}개 항목 저장 중...)")
    else:
        final_df = new_df
        print(f"새 CSV 파일 생성 완료. ({len(final_df)}개 항목)")
        
    final_df.to_csv(filename, index=False, encoding='utf-8-sig')

if __name__ == "__main__":
    print(f"--- 크롤링 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
    
    filtered_cat_df = cat_df[cat_df['Sub_Category'] != '전체']
    
    # 유일한 하위 카테고리 ID 만 추출
    unique_category_ids = filtered_cat_df['Sub_Category_ID'].dropna().astype(str).unique().tolist()
    print(f"총 {len(unique_category_ids)}개의 세부 카테고리(전체 제외)를 순회합니다.")
    
    # 카테고리 크롤링 진행
    crawled_data = scrape_all_categories(unique_category_ids)
    
    # CSV 업데이트
    update_csv(crawled_data)
    
    print("--- 크롤링 및 CSV 저장 자동화 작업 완료 ---")