import json
import re
import subprocess
from collections import Counter

def analyze_chatbot_and_db():
    print("Extracting Chatbot B logs...")
    res_b = subprocess.run(['docker', 'logs', 'oliview_chatbot_b'], capture_output=True, text=True, encoding='utf-8', errors='ignore')
    chatb_logs = res_b.stdout.splitlines() + res_b.stderr.splitlines()
    
    queries = []
    brands_queried = []
    categories_queried = []
    skin_types = []
    
    for line in chatb_logs:
        # extract query patterns
        if "query=" in line or "query':" in line or '"query":' in line:
            queries.append(line)
        # Check intent extraction or search logs
        m_query = re.search(r'"query":\s*"([^"]+)"', line)
        if m_query:
            queries.append(m_query.group(1))
            
        m_brand = re.search(r'"brand":\s*"([^"]+)"', line)
        if m_brand:
            brands_queried.append(m_brand.group(1))
            
        m_cat = re.search(r'"category":\s*"([^"]+)"', line)
        if m_cat:
            categories_queried.append(m_cat.group(1))

    # Also search keywords in gateway logs for chat requests
    res_gw = subprocess.run(['docker', 'logs', 'aiservice-gateway'], capture_output=True, text=True, encoding='utf-8', errors='ignore')
    gw_logs = res_gw.stdout.splitlines()
    
    stock_requests = Counter()
    for line in gw_logs:
        if '/api/stocks/' in line:
            m = re.search(r'/api/stocks/([0-9]+)', line)
            if m:
                stock_requests[m.group(1)] += 1

    # Extract db info
    res_db = subprocess.run(['docker', 'exec', 'bteam_db', 'mysql', '-ugp123', '-pGP123!', 'oliview_project', '-e', 'SELECT brand_id, brand_name_ko FROM brands LIMIT 20;'], capture_output=True, text=True, encoding='utf-8', errors='ignore')
    
    stock_names = {
        '005930': '삼성전자',
        '000660': 'SK하이닉스',
        '005380': '현대차',
        '005490': 'POSCO홀딩스',
        '035420': 'NAVER',
        '035720': '카카오',
        '068270': '셀트리온',
        '034020': '두산에너빌리티',
        '247540': '에코프로비엠',
        '373220': 'LG에너지솔루션'
    }
    
    named_stocks = {f"{stock_names.get(k, k)} ({k})": v for k, v in stock_requests.most_common()}
    
    detail_data = {
        'chatbot_queries_count': len(queries),
        'chatbot_sample_queries': queries[:20],
        'chatbot_brands': Counter(brands_queried).most_common(),
        'chatbot_categories': Counter(categories_queried).most_common(),
        'stock_popularity': named_stocks
    }
    
    with open('analytics/deep_dive_metrics.json', 'w', encoding='utf-8') as f:
        json.dump(detail_data, f, ensure_ascii=False, indent=2)
        
    print("Deep dive metrics saved to analytics/deep_dive_metrics.json")
    print("Stock Popularity:", named_stocks)

if __name__ == '__main__':
    analyze_chatbot_and_db()
