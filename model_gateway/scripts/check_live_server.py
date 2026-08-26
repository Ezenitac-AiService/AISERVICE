import urllib.request
import json
import time

endpoints = [
    ("시스템 헬스체크", "http://127.0.0.1:8081/health"),
    ("GPU 진단 헬스체크", "http://127.0.0.1:8081/api/health"),
    ("웹 대시보드 UI", "http://127.0.0.1:8081/dashboard/"),
    ("모델 목록 카탈로그 API", "http://127.0.0.1:8081/v1/models"),
    ("포트 8000 별칭 헬스체크", "http://127.0.0.1:8000/health"),
]

print("=" * 70)
print("🔍 LLM 서비스 컨테이너 실시간 접속성 최종 검증")
print("=" * 70)

for name, url in endpoints:
    try:
        t0 = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": "HealthChecker/1.0"})
        with urllib.request.urlopen(req, timeout=5) as res:
            elapsed = (time.time() - t0) * 1000
            data = res.read().decode('utf-8', errors='replace')
            print(f"✅ [HTTP {res.status} OK] {name} ({elapsed:.1f}ms)")
            print(f"   URL: {url}")
            if "html" in res.headers.get("content-type", "").lower() or "<!doctype html>" in data[:50].lower():
                print(f"   Response: [HTML Web UI Rendered, Size: {len(data):,} bytes]")
            else:
                print(f"   Response: {data[:160]}")
    except Exception as e:
        print(f"❌ [FAIL] {name} ({url}) -> {e}")
    print("-" * 70)
