import json
import urllib.request

url = "http://127.0.0.1:8081/v1/models"
with urllib.request.urlopen(url) as response:
    data = json.loads(response.read().decode("utf-8"))

print(f"📦 [GET {url}] 총 모델 수: {len(data['data'])}개\n")
print(f"{'모델 ID':<20} | {'적정 컨텍스트':<12} | {'최대 컨텍스트':<12} | {'지원 여부':<10} | {'다운로드 여부'}")
print("-" * 75)
for m in data["data"]:
    sup_str = "✅ 지원" if m.get("is_supported") else "❌ 불가"
    avail_str = "💾 다운로드됨" if m.get("is_available") else "☁️ 미다운로드"
    rec_ctx = f"{m.get('recommended_context_length'):,}"
    max_ctx = f"{m.get('max_context_length'):,}"
    print(f"{m['id']:<20} | {rec_ctx:<12} | {max_ctx:<12} | {sup_str:<10} | {avail_str}")
