import json
import re
import subprocess
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

KST = timezone(timedelta(hours=9))

def run():
    res = subprocess.run(['docker', 'logs', 'aiservice-gateway'], capture_output=True, text=True, encoding='utf-8', errors='ignore')
    lines = res.stdout.splitlines() + res.stderr.splitlines()

    parsed = []
    for l in lines:
        l = l.strip()
        if l.startswith('{') and l.endswith('}'):
            try:
                item = json.loads(l)
                t_str = item.get('time_local', '')
                parts = t_str.split()
                dt_utc = datetime.strptime(parts[0], '%d/%b/%Y:%H:%M:%S').replace(tzinfo=timezone.utc)
                dt_kst = dt_utc.astimezone(KST)
                item['dt'] = dt_kst
                item['date'] = dt_kst.strftime('%Y-%m-%d')
                item['hour'] = dt_kst.hour
                
                try:
                    item['req_time'] = float(item.get('request_time', 0.0))
                except:
                    item['req_time'] = 0.0
                    
                parsed.append(item)
            except:
                pass

    # Ranges
    # This week: 2026-09-03 ~ 2026-09-09 (7 days)
    # Prev week: 2026-08-27 ~ 2026-09-02 (7 days)
    this_week = [l for l in parsed if '2026-09-03' <= l['date'] <= '2026-09-09']
    prev_week = [l for l in parsed if '2026-08-27' <= l['date'] <= '2026-08-02' or ('2026-08-27' <= l['date'] <= '2026-09-02')]

    def classify_bot(log):
        ua = (log.get('http_user_agent') or '').lower()
        uri = (log.get('request_uri') or '').lower()
        method = log.get('request_method') or ''
        
        # Obvious scanners/bots
        bot_keywords = ['bot', 'crawler', 'spider', 'zgrab', 'scrap', 'checker', 'curl', 'python', 'postman', 'censys', 'nmap', 'masscan']
        if any(b in ua for b in bot_keywords):
            return True
        if uri.startswith('/v1/') or uri.startswith('/fetch') or uri.startswith('/proxy') or uri.startswith('/@fs') or uri.startswith('/actuator') or uri.startswith('/cgi-bin') or uri.endswith('.bak') or uri.endswith('.php') or uri.endswith('.env'):
            return True
        if method == '' or method not in ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'HEAD']:
            return True
        return False

    tw_bots = [l for l in this_week if classify_bot(l)]
    tw_real = [l for l in this_week if not classify_bot(l)]

    pw_bots = [l for l in prev_week if classify_bot(l)]
    pw_real = [l for l in prev_week if not classify_bot(l)]

    # Real user sessions
    def get_session_stats(log_list):
        sessions = defaultdict(list)
        for log in sorted(log_list, key=lambda x: x['dt']):
            ukey = f"{log.get('remote_addr')}|{log.get('http_user_agent')}"
            sessions[ukey].append(log)
            
        session_count = 0
        durations = []
        pvs = []
        for ukey, ulogs in sessions.items():
            cur = [ulogs[0]]
            for i in range(1, len(ulogs)):
                diff = (ulogs[i]['dt'] - ulogs[i-1]['dt']).total_seconds()
                if diff > 1800:
                    session_count += 1
                    durations.append((cur[-1]['dt'] - cur[0]['dt']).total_seconds())
                    pvs.append(len(cur))
                    cur = [ulogs[i]]
                else:
                    cur.append(ulogs[i])
            if cur:
                session_count += 1
                durations.append((cur[-1]['dt'] - cur[0]['dt']).total_seconds())
                pvs.append(len(cur))
        return {
            'unique_users': len(sessions),
            'sessions': session_count,
            'avg_pv': round(sum(pvs)/len(pvs), 2) if pvs else 0,
            'avg_duration': round(sum(durations)/len(durations), 2) if durations else 0
        }

    tw_real_sessions = get_session_stats(tw_real)
    tw_total_sessions = get_session_stats(this_week)

    # Daily real vs bot
    daily_stats = []
    day_names = ['월', '화', '수', '목', '금', '토', '일']
    for d in sorted(set(l['date'] for l in this_week)):
        d_logs = [l for l in this_week if l['date'] == d]
        d_real = [l for l in d_logs if not classify_bot(l)]
        d_bot = [l for l in d_logs if classify_bot(l)]
        dt_obj = datetime.strptime(d, "%Y-%m-%d")
        dow = day_names[dt_obj.weekday()]
        daily_stats.append({
            'date': d,
            'dow': dow,
            'total': len(d_logs),
            'real': len(d_real),
            'bot': len(d_bot),
            'real_sessions': get_session_stats(d_real)['sessions']
        })

    # Service breakdown for REAL user traffic
    def classify_service_detail(uri):
        u = uri.split('?')[0].lower()
        if u in ['', '/', '/index.html']:
            return '통합 포털 메인 (/)'
        elif u.startswith('/changelog'):
            return '시스템 변경로그 (/changelog)'
        elif u.startswith('/ateam/pilos') or u.startswith('/api/stocks') or u.startswith('/api/pipeline'):
            return 'A-Team Pilos (주식 감정 분석)'
        elif u.startswith('/bteam/chata'):
            return 'B-Team 올리챗 A (Streamlit RAG)'
        elif u.startswith('/bteam/chatb') or u.startswith('/api/v1/search'):
            return 'B-Team 올원챗 B (FastAPI RAG)'
        elif u.startswith('/bteam/oliview'):
            return 'B-Team Oliview (리뷰 분석 대시보드)'
        elif u.startswith('/api/'):
            return '공통 API'
        elif u in ['/favicon.ico', '/robots.txt', '/sitemap.xml']:
            return '정적 메타'
        else:
            return '기타 요청'

    real_service_counter = Counter(classify_service_detail(l.get('request_uri', '')) for l in tw_real)
    all_service_counter = Counter(classify_service_detail(l.get('request_uri', '')) for l in this_week)

    # Real user devices
    real_devices = Counter()
    for l in tw_real:
        ua = l.get('http_user_agent', '')
        if 'Mobile' in ua or 'Android' in ua or 'iPhone' in ua:
            real_devices['Mobile'] += 1
        elif ua:
            real_devices['Desktop'] += 1
        else:
            real_devices['Unknown'] += 1

    # Real user OS
    real_os = Counter()
    for l in tw_real:
        ua = l.get('http_user_agent', '')
        if 'Windows' in ua:
            real_os['Windows'] += 1
        elif 'Android' in ua:
            real_os['Android'] += 1
        elif 'iPhone' in ua or 'iPad' in ua:
            real_os['iOS'] += 1
        elif 'Macintosh' in ua or 'Mac OS' in ua:
            real_os['macOS'] += 1
        elif 'Linux' in ua:
            real_os['Linux'] += 1
        else:
            real_os['Other'] += 1

    # Status codes
    tw_status = Counter(l.get('status') for l in this_week)
    tw_real_status = Counter(l.get('status') for l in tw_real)

    # Latencies of real user requests
    real_lats = [l['req_time'] for l in tw_real]
    real_lats.sort()
    n = len(real_lats)

    out = {
        'period': '2026-09-03 ~ 2026-09-09',
        'comparison_period': '2026-08-27 ~ 2026-09-02',
        'total_requests': len(this_week),
        'prev_total_requests': len(prev_week),
        'real_requests': len(tw_real),
        'prev_real_requests': len(pw_real),
        'bot_requests': len(tw_bots),
        'prev_bot_requests': len(pw_bots),
        'real_sessions': tw_real_sessions,
        'daily_stats': daily_stats,
        'real_services': dict(real_service_counter.most_common()),
        'all_services': dict(all_service_counter.most_common()),
        'real_devices': dict(real_devices.most_common()),
        'real_os': dict(real_os.most_common()),
        'status_all': dict(tw_status.most_common()),
        'status_real': dict(tw_real_status.most_common()),
        'latency_real': {
            'avg': round(sum(real_lats)/n, 4) if n else 0,
            'p50': round(real_lats[int(n*0.5)], 4) if n else 0,
            'p90': round(real_lats[int(n*0.9)], 4) if n else 0,
            'p95': round(real_lats[int(n*0.95)], 4) if n else 0,
            'p99': round(real_lats[int(n*0.99)], 4) if n else 0,
            'max': round(real_lats[-1], 4) if n else 0
        }
    }

    with open('analytics/weekly_detailed_metrics.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("Calculated detailed metrics successfully:")
    print(json.dumps(out, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    run()
