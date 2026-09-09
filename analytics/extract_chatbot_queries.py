import subprocess
import json
import re

def extract():
    results = {}
    for c in ['oliview_chatbot_a', 'oliview_chatbot_b']:
        res = subprocess.run(['docker', 'logs', c], capture_output=True)
        lines = res.stdout.decode('utf-8', errors='replace').splitlines()
        queries = []
        for l in lines:
            if 'incoming query:' in l or '"query":' in l or 'query=' in l:
                # parse json if possible
                if l.startswith('{') and l.endswith('}'):
                    try:
                        data = json.loads(l)
                        msg = data.get('message', '')
                        if 'incoming query:' in msg:
                            q = msg.split('incoming query:')[1].strip()
                            queries.append({
                                'timestamp': data.get('timestamp'),
                                'query': q,
                                'logger': data.get('logger')
                            })
                    except:
                        pass
        results[c] = queries
    
    with open('analytics/chatbot_queries.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    extract()
