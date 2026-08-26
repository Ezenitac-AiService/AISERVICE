import csv
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def crawl_unique_brands():
    # 1. 수정된 파일명 'Categories_ID.csv'에서 카테고리 고유번호 읽기
    category_ids = []
    try:
        with open('Categories_ID.csv', mode='r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            for row in reader:
                # 중분류 ID(Intermediate_Category_ID)를 리스트에 수집
                if row.get('Intermediate_Category_ID'):
                    category_ids.append(row['Intermediate_Category_ID'])
    except FileNotFoundError:
        print("⚠️ 'Categories_ID.csv' 파일을 찾을 수 없습니다. 파일명과 위치를 확인해 주세요.")
        return

    # 중복을 제거하기 위해 딕셔너리 사용 { '브랜드ID': '브랜드명' }
    unique_brands = {}

    print(f"총 {len(category_ids)}개의 카테고리를 순회하며 브랜드를 수집합니다...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        
        # 2. 각 카테고리 페이지 순회
        for idx, cat_id in enumerate(category_ids, 1):
            # 올리브영 카테고리 URL 구조
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
                    brand_name = brand.get('data-brndnm')
                    
                    if brand_id and brand_name:
                        # 딕셔너리에 저장하여 자동 중복 제거
                        unique_brands[brand_id] = brand_name
                        
            except Exception as e:
                print(f"카테고리 {cat_id} 처리 중 오류 발생: {e}")
                
        browser.close()

    # 4. 수집된 브랜드 데이터를 CSV로 저장
    save_brands_to_csv(unique_brands)


def save_brands_to_csv(brands_dict):
    if not brands_dict:
        print("추출된 브랜드 데이터가 없습니다.")
        return
        
    # 출력 파일명을 'Brand_ID.csv'로 변경
    filename = 'Brand_ID.csv'
    
    with open(filename, mode='w', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file)
        
        # 헤더 작성
        writer.writerow(['Brand_ID', 'Brand_Name'])
        
        # 딕셔너리 데이터를 행 단위로 작성
        for b_id, b_name in brands_dict.items():
            writer.writerow([b_id, b_name])
            
    print(f"✅ 총 {len(brands_dict)}개의 중복 없는 고유 브랜드 데이터가 '{filename}' 파일로 성공적으로 저장되었습니다!")

if __name__ == "__main__":
    crawl_unique_brands()