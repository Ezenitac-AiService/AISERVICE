import os
import sys
import json
import re
import subprocess
from datetime import datetime
from collections import Counter, defaultdict

def fetch_docker_logs(container_name):
    print(f"Fetching logs from container: {container_name}...")
    res = subprocess.run(['docker', 'logs', container_name], capture_output=True, text=True, encoding='utf-8', errors='ignore')
    return res.stdout.splitlines() + res.stderr.splitlines()

def parse_user_agent(ua):
    if not ua or ua == '-':
        return {'device': 'Unknown', 'os': 'Unknown', 'browser': 'Unknown', 'is_inapp': False, 'inapp_type': 'None'}
    
    device = 'Desktop'
    is_inapp = False
    inapp_type = 'None'
    
    # InApp check
    if 'KAKAOTALK' in ua:
        is_inapp = True
        inapp_type = 'KakaoTalk'
    elif 'Instagram' in ua:
        is_inapp = True
        inapp_type = 'Instagram'
    elif 'FB_IAB' in ua or 'FBAN' in ua:
        is_inapp = True
        inapp_type = 'Facebook'
    elif 'NAVER' in ua:
        is_inapp = True
        inapp_type = 'Naver'

    # Mobile check
    if 'Mobile' in ua or 'Android' in ua or 'iPhone' in ua or 'iPad' in ua:
        if 'iPad' in ua or 'Tablet' in ua:
            device = 'Tablet'
        else:
            device = 'Mobile'
    elif 'bot' in ua.lower() or 'crawler' in ua.lower() or 'spider' in ua.lower():
        device = 'Bot/Crawler'

    # OS
    os_name = 'Other'
    if 'Windows NT 10.0' in ua:
        os_name = 'Windows 10/11'
    elif 'Windows' in ua:
        os_name = 'Windows (Other)'
    elif 'Android' in ua:
        match = re.search(r'Android\s+([0-9\.]+)', ua)
        os_name = f"Android {match.group(1)}" if match else "Android"
    elif 'iPhone OS' in ua or 'iPhone' in ua:
        match = re.search(r'OS\s+([0-9_]+)', ua)
        ver = match.group(1).replace('_', '.') if match else ""
        os_name = f"iOS {ver}" if ver else "iOS"
    elif 'Macintosh' in ua or 'Mac OS X' in ua:
        os_name = 'macOS'
    elif 'Linux' in ua:
        os_name = 'Linux'

    # Browser
    browser = 'Other'
    if is_inapp:
        browser = inapp_type + ' In-App'
    elif 'Edg/' in ua:
        browser = 'Edge'
    elif 'Chrome/' in ua:
        browser = 'Chrome'
    elif 'Safari/' in ua and 'Chrome/' not in ua:
        browser = 'Safari'
    elif 'Firefox/' in ua:
        browser = 'Firefox'
    elif 'curl' in ua or 'Postman' in ua or 'python' in ua.lower():
        browser = 'API Tool (curl/python)'

    return {
        'device': device,
        'os': os_name,
        'browser': browser,
        'is_inapp': is_inapp,
        'inapp_type': inapp_type
    }

def classify_service(uri):
    uri_clean = uri.split('?')[0].lower()
    if uri_clean == '/' or uri_clean == '/index.html':
        return '통합 포털 랜딩 (/)'
    elif uri_clean.startswith('/bteam/oliview/api/'):
        return 'B-Team Oliview API'
    elif uri_clean.startswith('/bteam/oliview'):
        return 'B-Team Oliview 웹'
    elif uri_clean.startswith('/bteam/chata'):
        return 'B-Team 올리챗 A (Streamlit)'
    elif uri_clean.startswith('/bteam/chatb') or uri_clean.startswith('/api/v1/search'):
        return 'B-Team 올원챗 B (FastAPI RAG)'
    elif uri_clean.startswith('/ateam/pilos') or uri_clean.startswith('/api/stocks') or uri_clean.startswith('/api/pipeline'):
        return 'A-Team Pilos 웹/API'
    elif uri_clean.startswith('/api/'):
        return '공통 API'
    elif uri_clean in ['/favicon.ico', '/robots.txt', '/sitemap.xml']:
        return '정적 메타 리소스'
    else:
        return '기타/직접 호출'

def run_analysis():
    print("Starting Comprehensive Log Analysis...")
    raw_lines = fetch_docker_logs('aiservice-gateway')
    
    parsed_logs = []
    for line in raw_lines:
        line = line.strip()
        if line.startswith('{') and line.endswith('}'):
            try:
                item = json.loads(line)
                parsed_logs.append(item)
            except Exception:
                continue
    
    print(f"Total Parsed Gateway Access Logs: {len(parsed_logs)}")

    # Time Parsing
    # Example format: "24/Aug/2026:07:49:23 +0000"
    for log in parsed_logs:
        t_str = log.get('time_local', '')
        try:
            # Parse standard nginx time
            dt = datetime.strptime(t_str.split()[0], "%d/%b/%Y:%H:%M:%S")
            log['dt'] = dt
            log['date_str'] = dt.strftime("%Y-%m-%d")
            log['hour_str'] = dt.strftime("%Y-%m-%d %H:00")
            log['hour_of_day'] = dt.hour
        except Exception:
            log['dt'] = None
            log['date_str'] = 'Unknown'
            log['hour_str'] = 'Unknown'
            log['hour_of_day'] = -1
        
        # User Agent Info
        ua_info = parse_user_agent(log.get('http_user_agent', ''))
        log.update(ua_info)
        
        # Service Classification
        log['service_category'] = classify_service(log.get('request_uri', ''))
        
        # Request Time / Latency
        try:
            log['req_time_num'] = float(log.get('request_time', 0.0))
        except:
            log['req_time_num'] = 0.0
            
        try:
            up_t = log.get('upstream_response_time', '0')
            log['upstream_time_num'] = float(up_t) if up_t != '-' and up_t != '' else 0.0
        except:
            log['upstream_time_num'] = 0.0
            
        try:
            log['bytes_sent_num'] = int(log.get('body_bytes_sent', 0))
        except:
            log['bytes_sent_num'] = 0

    # 1. Temporal Analysis
    date_counter = Counter(log['date_str'] for log in parsed_logs if log['date_str'] != 'Unknown')
    hour_counter = Counter(log['hour_of_day'] for log in parsed_logs if log['hour_of_day'] != -1)
    
    # 2. Device & Environment Analysis
    device_counter = Counter(log['device'] for log in parsed_logs)
    os_counter = Counter(log['os'] for log in parsed_logs)
    browser_counter = Counter(log['browser'] for log in parsed_logs)
    inapp_counter = Counter(log['inapp_type'] for log in parsed_logs if log['is_inapp'])
    
    # 3. User & Session Analysis
    # Session identification: IP + UA + 30 min inactivity threshold
    sessions = defaultdict(list)
    for log in sorted([l for l in parsed_logs if l['dt']], key=lambda x: x['dt']):
        user_key = f"{log.get('remote_addr')}|{log.get('http_user_agent')}"
        sessions[user_key].append(log)
    
    total_distinct_users = len(sessions)
    total_sessions_count = 0
    session_durations = []
    session_pv_counts = []
    
    for user_key, u_logs in sessions.items():
        current_session_logs = [u_logs[0]]
        for i in range(1, len(u_logs)):
            diff_sec = (u_logs[i]['dt'] - u_logs[i-1]['dt']).total_seconds()
            if diff_sec > 1800: # 30 mins
                # end session
                total_sessions_count += 1
                s_dur = (current_session_logs[-1]['dt'] - current_session_logs[0]['dt']).total_seconds()
                session_durations.append(s_dur)
                session_pv_counts.append(len(current_session_logs))
                current_session_logs = [u_logs[i]]
            else:
                current_session_logs.append(u_logs[i])
        if current_session_logs:
            total_sessions_count += 1
            s_dur = (current_session_logs[-1]['dt'] - current_session_logs[0]['dt']).total_seconds()
            session_durations.append(s_dur)
            session_pv_counts.append(len(current_session_logs))

    # 4. Service & Endpoint Popularity
    service_counter = Counter(log['service_category'] for log in parsed_logs)
    uri_counter = Counter(log.get('request_uri', '').split('?')[0] for log in parsed_logs)
    
    # 5. Status Codes & Error Diagnostics
    status_counter = Counter(log.get('status') for log in parsed_logs)
    errors_404 = Counter(log.get('request_uri', '').split('?')[0] for log in parsed_logs if log.get('status') == 404)
    errors_500 = Counter(log.get('request_uri', '').split('?')[0] for log in parsed_logs if log.get('status') in [500, 502, 503, 504])
    
    # 6. Latency Analysis
    latencies = [log['req_time_num'] for log in parsed_logs]
    latencies.sort()
    n_lat = len(latencies)
    avg_latency = sum(latencies) / n_lat if n_lat else 0
    p50_lat = latencies[int(n_lat * 0.50)] if n_lat else 0
    p90_lat = latencies[int(n_lat * 0.90)] if n_lat else 0
    p95_lat = latencies[int(n_lat * 0.95)] if n_lat else 0
    p99_lat = latencies[int(n_lat * 0.99)] if n_lat else 0
    max_lat = latencies[-1] if n_lat else 0
    
    # Slowest Endpoints
    endpoint_latency = defaultdict(list)
    for log in parsed_logs:
        uri_clean = log.get('request_uri', '').split('?')[0]
        endpoint_latency[uri_clean].append(log['req_time_num'])
        
    slow_endpoints = []
    for uri, lats in endpoint_latency.items():
        if len(lats) >= 5: # at least 5 requests
            slow_endpoints.append({
                'uri': uri,
                'count': len(lats),
                'avg_latency': sum(lats)/len(lats),
                'p95_latency': sorted(lats)[int(len(lats)*0.95)],
                'max_latency': max(lats)
            })
    slow_endpoints.sort(key=lambda x: x['avg_latency'], reverse=True)

    # 7. Chatbot B & A Log Analysis (Queries & Intents)
    print("Fetching Chatbot B logs...")
    chatb_lines = fetch_docker_logs('oliview_chatbot_b')
    chatb_queries = []
    for l in chatb_lines:
        if 'query=' in l or 'search' in l or 'POST /api/v1/search' in l:
            chatb_queries.append(l)
            
    print(f"Chatbot B matched query logs: {len(chatb_queries)}")

    summary_metrics = {
        'total_requests': len(parsed_logs),
        'time_range': {
            'start': parsed_logs[0]['time_local'] if parsed_logs else '',
            'end': parsed_logs[-1]['time_local'] if parsed_logs else ''
        },
        'user_stats': {
            'unique_users_estimated': total_distinct_users,
            'total_sessions_estimated': total_sessions_count,
            'avg_pv_per_session': round(sum(session_pv_counts)/len(session_pv_counts), 2) if session_pv_counts else 0,
            'avg_session_duration_sec': round(sum(session_durations)/len(session_durations), 2) if session_durations else 0
        },
        'traffic_by_date': dict(sorted(date_counter.items())),
        'traffic_by_hour': dict(sorted(hour_counter.items())),
        'devices': dict(device_counter.most_common()),
        'os': dict(os_counter.most_common(10)),
        'browsers': dict(browser_counter.most_common(10)),
        'inapp_browsers': dict(inapp_counter.most_common()),
        'service_shares': dict(service_counter.most_common()),
        'top_endpoints': dict(uri_counter.most_common(20)),
        'status_codes': dict(status_counter.most_common()),
        'errors_404_top': dict(errors_404.most_common(10)),
        'errors_500_top': dict(errors_500.most_common(10)),
        'latency_stats': {
            'avg': round(avg_latency, 4),
            'p50': round(p50_lat, 4),
            'p90': round(p90_lat, 4),
            'p95': round(p95_lat, 4),
            'p99': round(p99_lat, 4),
            'max': round(max_lat, 4)
        },
        'slow_endpoints_top': slow_endpoints[:15]
    }
    
    os.makedirs('analytics', exist_ok=True)
    with open('analytics/summary_metrics.json', 'w', encoding='utf-8') as f:
        json.dump(summary_metrics, f, ensure_ascii=False, indent=2)
        
    print("Summary metrics successfully saved to analytics/summary_metrics.json")

if __name__ == '__main__':
    run_analysis()
