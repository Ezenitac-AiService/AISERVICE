# uv add playwright beautifulsoup4 mysql-connector-python
# uv run playwright install chromium

import random, sys, time
from datetime import datetime
from pathlib import Path
from typing import Any
from bs4 import BeautifulSoup
from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from common.db_manager import DBManager

PRODUCT_DETAIL_URL = "https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo={product_code}"
MAX_PRODUCTS_PER_RUN = 100
MAX_RETRIES = 2
PAGE_TIMEOUT = 30_000
PRODUCT_DETAIL_TIMEOUT = 20_000
CLOUDFLARE_KEYWORDS = ['잠시만 기다려 주세요','접속 정보를 확인 중이에요','Cloudflare 보안 챌린지','challenges.cloudflare.com','cf-turnstile-response','__cf_chl_']

class CloudflareChallengeError(RuntimeError):
    pass

def normalize_text(value: Any) -> str:
    return '' if value is None else ' '.join(str(value).split()).strip()

def get_unmapped_products(connection, limit):
    sql = """SELECT product_id,product_code,product_name FROM products WHERE brand_id IS NULL AND is_active=1 ORDER BY product_id LIMIT %s"""
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(sql, (limit,)); return cursor.fetchall()
    finally:
        cursor.close()

def count_unmapped_products(connection):
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT COUNT(*) AS cnt FROM products WHERE brand_id IS NULL AND is_active=1")
        return int(cursor.fetchone()['cnt'])
    finally:
        cursor.close()

def get_brand_mapping(connection):
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT brand_id,brand_code FROM brands WHERE is_active=1 AND brand_code IS NOT NULL AND TRIM(brand_code)<>''")
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return {normalize_text(r['brand_code']):int(r['brand_id']) for r in rows if normalize_text(r['brand_code'])}

def is_cloudflare_challenge(page: Page) -> bool:
    html = page.content()
    try:
        body = normalize_text(page.locator('body').inner_text(timeout=3000))
    except Exception:
        body = ''
    return any(k in html or k in body for k in CLOUDFLARE_KEYWORDS)

def extract_brand_code(page: Page, product_code: str) -> str:
    url = PRODUCT_DETAIL_URL.format(product_code=product_code)
    for attempt in range(1, MAX_RETRIES+1):
        time.sleep(random.uniform(2.5, 5.0))
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=PAGE_TIMEOUT)
            if is_cloudflare_challenge(page):
                raise CloudflareChallengeError(product_code)
            page.wait_for_selector('meta[property="eg:brandId"]', state='attached', timeout=PRODUCT_DETAIL_TIMEOUT)
            soup = BeautifulSoup(page.content(), 'html.parser')
            meta = soup.select_one('meta[property="eg:brandId"]')
            code = normalize_text(meta.get('content')) if meta else ''
            if code:
                return code
        except CloudflareChallengeError:
            raise
        except PlaywrightTimeoutError:
            print(f'    ⚠️ 로딩 실패 {attempt}/{MAX_RETRIES}: {product_code}')
        except Exception as e:
            print(f'    ⚠️ 상세페이지 오류 {attempt}/{MAX_RETRIES}: {product_code} / {e}')
        if attempt < MAX_RETRIES:
            wait = random.uniform(8.0,15.0)
            print(f'    ⏳ {wait:.1f}초 후 재시도')
            time.sleep(wait)
    return ''

def update_product_brand(connection, product_id: int, brand_id: int):
    cursor = connection.cursor()
    try:
        cursor.execute("UPDATE products SET brand_id=%s WHERE product_id=%s AND brand_id IS NULL", (brand_id, product_id))
        connection.commit()
    except Exception:
        connection.rollback(); raise
    finally:
        cursor.close()

def main():
    print('='*60); print(f"상품 브랜드 매핑 시작: {datetime.now():%Y-%m-%d %H:%M:%S}"); print('='*60)
    db = DBManager(); playwright = browser = context = None
    try:
        db.connect(); connection = db.connection
        if connection is None: raise RuntimeError('DB 연결 실패')
        before = count_unmapped_products(connection)
        print(f'📌 현재 brand_id 미매핑 활성 상품: {before}개')
        if before == 0:
            print('✅ 매핑할 상품이 없습니다.'); return
        products = get_unmapped_products(connection, MAX_PRODUCTS_PER_RUN)
        brand_mapping = get_brand_mapping(connection)
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(locale='ko-KR', viewport={'width':1400,'height':900})
        page = context.new_page()
        success = 0; failed = []; cloudflare = False
        for idx, product in enumerate(products, start=1):
            product_id = int(product['product_id']); code = str(product['product_code']); name = str(product['product_name'])
            try:
                brand_code = extract_brand_code(page, code)
            except CloudflareChallengeError:
                cloudflare = True
                print('\n🛑 Cloudflare 보안 확인 페이지가 나타났습니다. 지금까지 성공한 결과는 이미 DB에 저장되었습니다.')
                break
            if not brand_code:
                failed.append((code,'','brand_code 없음'))
                print(f'  [{idx}/{len(products)}] ❌ {code} / {name}')
                continue
            brand_id = brand_mapping.get(brand_code)
            if brand_id is None:
                failed.append((code,brand_code,'brands 테이블 미등록'))
                print(f'  [{idx}/{len(products)}] ⚠️ {code} -> {brand_code} (미등록)')
                continue
            update_product_brand(connection, product_id, brand_id)
            success += 1
            print(f'  [{idx}/{len(products)}] {code} -> {brand_code} -> brand_id={brand_id}')
        after = count_unmapped_products(connection)
        print(f'\n✅ 이번 실행 성공: {success}개')
        print(f'⚠️ 이번 실행 일반 실패: {len(failed)}개')
        print(f'📌 남은 미매핑 활성 상품: {after}개')
        if failed:
            print('\n📋 실패 상품 일부:')
            for row in failed[:20]: print(f'  - {row[0]} / {row[1] or "-"} / {row[2]}')
        if cloudflare:
            print('\n⏸️ 잠시 후 다시 실행하면 brand_id가 NULL인 상품부터 이어집니다.')
        elif after > 0:
            print('\n⏸️ 아직 매핑할 상품이 남아 있습니다. 잠시 후 다시 실행하세요.')
        else:
            print('\n🎉 모든 활성 상품의 브랜드 매핑이 완료되었습니다.')
    except Exception as e:
        print(f'\n❌ 작업 실패: {e}')
    finally:
        if context is not None: context.close()
        if browser is not None: browser.close()
        if playwright is not None: playwright.stop()
        db.close()
    print('='*60); print(f"작업 종료: {datetime.now():%Y-%m-%d %H:%M:%S}"); print('='*60)

if __name__ == '__main__':
    main()