import csv
import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def crawl_oliveyoung_categories():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        
        # ==========================================
        # 1단계: 메인 페이지에서 대/중분류 리스트 수집
        # ==========================================
        url = "https://www.oliveyoung.co.kr/store/main/main.do"
        print("올리브영 메인 페이지 접속 중 (대/중분류 수집)...")
        page.goto(url, wait_until="networkidle") 
        
        try:
            category_btn = page.wait_for_selector("#btnGnbOpen", state="visible", timeout=5000)
            category_btn.click()
            page.wait_for_selector("#gnbAllMenu", state="attached", timeout=5000)
            page.wait_for_timeout(1000) 
        except Exception as e:
            print(f"⚠️ 카테고리 메뉴를 여는 중 문제가 발생했습니다: {e}")

        html = page.content()
        soup = BeautifulSoup(html, 'html.parser')
        
        intermediate_data_list = []
        major_headers = soup.select('p.sub_depth')
        
        for p_tag in major_headers:
            major_a_tag = p_tag.select_one('a')
            if not major_a_tag:
                continue
                
            major_name_text = major_a_tag.text.strip()
            major_category_id = ""
            
            if major_a_tag.has_attr('data-ref-dispcatno'):
                major_category_id = major_a_tag['data-ref-dispcatno']
            elif major_a_tag.has_attr('href'):
                match = re.search(r"\('(\d+)'", major_a_tag['href'])
                if match:
                    major_category_id = match.group(1)
            
            ul_tag = p_tag.find_next_sibling('ul')
            if ul_tag:
                sub_items = ul_tag.select('li > a')
                
                for item in sub_items:
                    intermediate_name = item.text.strip()
                    intermediate_category_id = ""
                    
                    if item.has_attr('data-ref-dispcatno'):
                        intermediate_category_id = item['data-ref-dispcatno']
                    elif item.has_attr('href'):
                        match = re.search(r"\('(\d+)'", item['href'])
                        if match:
                            intermediate_category_id = match.group(1)
                    
                    if intermediate_category_id:
                        intermediate_data_list.append({
                            'Major_Category': major_name_text,
                            'Major_Category_ID': major_category_id,
                            'Intermediate_Category': intermediate_name,
                            'Intermediate_Category_ID': intermediate_category_id
                        })
                        
        print(f"✅ 총 {len(intermediate_data_list)}개의 중분류 카테고리를 찾았습니다.")
        print("==========================================")
        print("2단계: 각 중분류 페이지로 이동하여 소분류를 수집합니다. (시간이 소요됩니다)")
        print("==========================================")

        # ==========================================
        # 2단계: 각 중분류 페이지에 접속하여 소분류 수집
        # ==========================================
        final_categories_data = []
        
        for idx, data in enumerate(intermediate_data_list, 1):
            int_id = data['Intermediate_Category_ID']
            int_name = data['Intermediate_Category']
            
            print(f"[{idx}/{len(intermediate_data_list)}] '{int_name}' 소분류 탐색 중...")
            
            cat_url = f"https://www.oliveyoung.co.kr/store/display/getMCategoryList.do?dispCatNo={int_id}"
            
            try:
                # 1. 렌더링 완벽 대기: 통신이 잦아들 때까지 기다림 (핵심 변경점)
                page.goto(cat_url, wait_until="networkidle", timeout=15000)
                
                # 2. 소분류 리스트(ul.cate_list_box)가 DOM에 나타날 때까지 명시적으로 기다림
                try:
                    page.wait_for_selector('ul.cate_list_box', state='attached', timeout=3000)
                except:
                    pass # 소분류가 아예 없는 카테고리(예: 스킨케어 디바이스)를 위해 에러 무시
                
                cat_html = page.content()
                cat_soup = BeautifulSoup(cat_html, 'html.parser')
                
                sub_items = cat_soup.select('ul.cate_list_box > li > a')
                
                if not sub_items:
                    data['Sub_Category'] = ''
                    data['Sub_Category_ID'] = ''
                    final_categories_data.append(data)
                else:
                    for sub_a in sub_items:
                        sub_name = sub_a.text.strip()
                        sub_id = ""
                        
                        # class 속성에서 10자리 이상의 고유 번호 추출
                        if sub_a.has_attr('class'):
                            for cls in sub_a['class']:
                                if cls.isdigit() and len(cls) > 10:
                                    sub_id = cls
                                    break
                                    
                        # class에 없을 경우 href 함수 인자에서 추출
                        if not sub_id and sub_a.has_attr('href'):
                            match = re.search(r"\('(\d+)'", sub_a['href'])
                            if match:
                                sub_id = match.group(1)
                                
                        # '전체' 탭 등에서 ID를 못 찾았을 경우, 해당 중분류 ID를 그대로 사용 (이미지 구조 반영)
                        if not sub_id and sub_name == '전체':
                            sub_id = int_id
                        
                        new_row = data.copy()
                        new_row['Sub_Category'] = sub_name
                        new_row['Sub_Category_ID'] = sub_id
                        final_categories_data.append(new_row)
                        
            except Exception as e:
                print(f"⚠️ '{int_name}' 페이지 처리 중 오류 발생: {e}")
                data['Sub_Category'] = 'Error'
                data['Sub_Category_ID'] = 'Error'
                final_categories_data.append(data)

        browser.close()
        
        save_to_csv(final_categories_data)


def save_to_csv(data_list):
    if not data_list:
        print("추출된 데이터가 없습니다.")
        return
        
    filename = 'Categories_ID.csv'
    
    with open(filename, mode='w', encoding='utf-8-sig', newline='') as file:
        fieldnames = [
            'Major_Category', 'Major_Category_ID', 
            'Intermediate_Category', 'Intermediate_Category_ID',
            'Sub_Category', 'Sub_Category_ID'
        ]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        
        writer.writeheader()
        for data in data_list:
            writer.writerow(data)
            
    print(f"✅ 총 {len(data_list)}개의 데이터(소분류 포함)가 '{filename}' 파일로 완벽하게 저장되었습니다!")

if __name__ == "__main__":
    crawl_oliveyoung_categories()