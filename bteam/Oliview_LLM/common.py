"""common.py - vllm_serv 교육용 예제 스크립트 공통 헬퍼 모듈

================================================================================
[비전공자 훈련생을 위한 공통 모듈 안내]
이 모듈은 AI 서비스 개발 실습 시 반복해서 쓰이는 공통 기능(이중 서버 자동 탐색,
헬스체크, 클라이언트 생성기, 타임스탬프 계산, TTFT 및 TPS 성능 측정, <think> 정제 및 스트리밍 필터)을 제공합니다.
================================================================================
"""

import os
import sys
import json
import time
import re
import datetime
from pathlib import Path
import httpx
from openai import OpenAI

# [추론 비활성화 공통 시스템 지시어]
NO_THINK_SYSTEM_PROMPT = "당신은 IT 및 AI 기술 전문 어시스턴트입니다. 생각 과정(<think>, Thinking Process, Draft/Identify 등)을 절대 작성하지 마시고, 첫 글자부터 즉시 최종 한국어 답변만 작성하세요."


def load_project_env() -> None:
    """프로젝트 루트의 .env 파일을 읽어 환경변수로 로드합니다."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        os.environ.setdefault(key, value)


load_project_env()


def clean_think_tags(text: str, show_think: bool = False) -> str:
    """<think>...</think> 태그, Thinking Process 및 Identify Key Concepts/Draft 등 높은 온도의 모든 CoT 고찰 블록을 완벽히 세척합니다."""
    if not text:
        return ""

    think_part = ""
    answer_part = text

    # 1. 표준 <think>...</think> 태그 처리
    if "<think>" in text and "</think>" in text:
        parts = text.split("</think>", 1)
        think_part = parts[0].replace("<think>", "").strip()
        answer_part = parts[1].strip()
    elif "</think>" in text:
        parts = text.split("</think>", 1)
        think_part = parts[0].replace("<think>", "").strip()
        answer_part = parts[1].strip()

    # 2. 고온(high temp) 및 비표준 추론 모델의 English CoT 정규식 감지 및 세척
    cot_patterns = [
        r"Thinking Process:",
        r"Drafting:",
        r"Drafting the Definition:",
        r"Identify Key Concepts:",
        r"Draft Potential Answers:",
        r"Analyze the Request:",
        r"Draft Potential:",
        r"Final Polish:",
        r"Internal Monologue:"
    ]

    is_cot_present = any(re.search(pat, answer_part, re.IGNORECASE) for pat in cot_patterns) or ("Analyze" in answer_part and "Draft" in answer_part) or ("Final Polish" in answer_part)

    if is_cot_present:
        lines = answer_part.splitlines()
        think_lines = []
        answer_lines = []
        in_thinking = False

        for line in lines:
            s_line = line.strip()
            # 추론 키워드 또는 번호 매긴 추론 단계(1. Analyze..., 2. Identify..., 4. Final Polish 등) 헤더 감지
            if any(re.search(pat, s_line, re.IGNORECASE) for pat in cot_patterns) or re.match(r"^\d+\.\s+(Identify|Analyze|Draft|Determine|Construct|Check|Refine|Review|Final)", s_line, re.IGNORECASE) or s_line.startswith("<think>"):
                in_thinking = True
                think_lines.append(line)
                continue

            if in_thinking:
                # 불필요한 총괄 지침 항목 스킵
                if s_line.startswith("- Goal:") or s_line.startswith("- Role:") or s_line.startswith("- Task:") or s_line.startswith("- Constraint:") or s_line.startswith("Or simpler:"):
                    think_lines.append(line)
                    continue

                # 불릿 포인트(*) 내에 한글 답변이 포함되어 있는 경우 추출
                if s_line.startswith("*") or s_line.startswith("-"):
                    if re.search(r"[가-힣]", s_line):
                        s_clean = re.sub(r'^\s*[\*\-]\s*"?', "", s_line).rstrip('"')
                        s_clean = re.sub(r'\s*\([^)]*\)\s*$', "", s_clean).strip()
                        if s_clean:
                            answer_lines.append(s_clean)
                            in_thinking = False
                            continue
                    think_lines.append(line)
                    continue

                # 일반 본문 문장이 등장한 경우 추출
                if s_line:
                    s_clean = re.sub(r'^\s*[\*\-]\s*"?', "", s_line).rstrip('"')
                    s_clean = re.sub(r'\s*\([^)]*\)\s*$', "", s_clean).strip()
                    answer_lines.append(s_clean)
                    in_thinking = False
                    continue
                think_lines.append(line)
            else:
                answer_lines.append(line)

        if not think_part and think_lines:
            think_part = "\n".join(think_lines).replace("<think>", "").replace("</think>", "").strip()

        if answer_lines:
            answer_part = "\n".join(answer_lines).replace("<think>", "").replace("</think>", "").strip()
        else:
            answer_part = text.replace("<think>", "").replace("</think>", "").strip()

    answer_part = answer_part.replace("<think>", "").replace("</think>", "").strip()

    # show_think=True 인 경우 생각 과정과 최종 답변을 시각적으로 구분 표시
    if show_think and think_part:
        return f"🧠 [AI 생각 과정 <think>]:\n{think_part}\n\n💬 [AI 최종 답변]:\n{answer_part}"
    
    return answer_part


class StreamThinkFilter:
    """실시간 스트리밍 도중 수신되는 <think>...</think> 및 Thinking Process: 토큰을 필터링하는 파서"""
    def __init__(self):
        self.buffer = ""
        self.in_thinking = False
        self.thinking_done = False

    def process_token(self, token: str) -> str:
        if self.thinking_done:
            return token
        
        self.buffer += token
        
        # 1. <think>... 영역 감지
        if "<think>" in self.buffer and "</think>" not in self.buffer:
            self.in_thinking = True
            return ""
        
        if "</think>" in self.buffer:
            text = self.buffer.split("</think>")[-1]
            self.buffer = ""
            self.thinking_done = True
            return text.lstrip()

        # 2. Thinking Process: 및 Identify/Draft 영역 감지
        thinking_keywords = ["Thinking Process:", "Thinking Process", "Drafting the Definition", "Identify Key Concepts:", "Draft Potential"]
        if any(kw in self.buffer for kw in thinking_keywords):
            self.in_thinking = True
            if "\n\n" in self.buffer:
                parts = self.buffer.split("\n\n")
                for part in parts[1:]:
                    s = part.strip()
                    if s and not s.startswith("*") and not s.startswith("Role:") and not s.startswith("Task:") and not s.startswith("Constraint:") and not s.startswith("Goal:") and not s.startswith("Idea") and not s.startswith("1.") and not s.startswith("2.") and not s.startswith("3."):
                        self.thinking_done = True
                        self.buffer = ""
                        return part.lstrip()
            return ""
        
        # 3. 추론 태그가 없는 순수 답변 텍스트인 경우 버퍼 플러시
        if not self.in_thinking and len(self.buffer) > 15:
            text = self.buffer
            self.buffer = ""
            self.thinking_done = True
            return text

        return ""

    def flush(self) -> str:
        if self.thinking_done:
            return ""
        text = self.buffer
        if "</think>" in text:
            text = text.split("</think>", 1)[-1]
        text = text.replace("<think>", "").replace("</think>", "").strip()
        return text


def load_sample_config() -> dict:
    """config.json 파일과 환경변수에서 활성 주소 및 모델/토큰 토폴로지 설정을 읽어옵니다."""
    active_host = get_server_host()
    default_model = os.getenv("DEFAULT_MODEL", "qwen3.5-4b")
    config = {
        "server_host": active_host,
        "primary_server_host": "http://127.0.0.1",
        "fallback_server_host": "http://vllm-serv-gateway",
        "main_port": int(os.getenv("MAIN_PORT", os.getenv("MODEL_GATEWAY_PORT", 8081))),
        "embedding_port": int(os.getenv("EMBEDDING_PORT", 8090)),
        "rerank_port": int(os.getenv("RERANK_PORT", 8091)),
        "default_model": default_model,
        "embedding_model": os.getenv("EMBEDDING_MODEL", "bge-m3"),
        "rerank_model": os.getenv("RERANK_MODEL", "bge-reranker-v2-m3"),
        "default_temperature": 0.3,
        "default_max_tokens": 1024,
        "benchmark_max_tokens": 2048,
        "no_think_max_tokens": 512,
        "gpu_info": {
            "device_name": "NVIDIA GeForce RTX 3060 / GTX 1070 Auto Detect",
            "total_vram_mb": 8192,
            "cuda_version": "12.1",
            "reserved_vram_embedding_reranker_mb": 1211,
            "available_llm_vram_mb": 6981
        },
        "model_benchmarks": {
            "qwen3.5-2b": {"recommended_context_length": 65536, "max_context_length": 131072, "peak_vram_mb": 2450, "tpot_tok_per_sec": 53.98, "status": "ACTIVE_DEFAULT", "description": "상시 서빙 모델 (64K Standard / 128K Ultra, 54 TPS)"},
            "qwen3.5-4b": {"recommended_context_length": 32768, "max_context_length": 49152, "peak_vram_mb": 3950, "tpot_tok_per_sec": 34.96, "status": "BATCH_QUALITY", "description": "고품질 배치 모델 (32K Standard, 35 TPS)"},
            "qwen3.5-9b": {"recommended_context_length": 2048, "max_context_length": 4096, "peak_vram_mb": 7120, "tpot_tok_per_sec": 43.69, "status": "AVAILABLE", "description": "고성능 추론 대형 모델 (2K 추천 / 4K 최대)"},
            "gemma4-e2b": {"recommended_context_length": 8192, "max_context_length": 16384, "peak_vram_mb": 2680, "tpot_tok_per_sec": 52.79, "status": "AVAILABLE", "description": "Gemma 소형 모델 (8K 추천 / 16K 최대)"},
            "gemma4-e4b": {"recommended_context_length": 4096, "max_context_length": 8192, "peak_vram_mb": 4210, "tpot_tok_per_sec": 41.68, "status": "AVAILABLE", "description": "Gemma 중형 모델 (4K 추천 / 8K 최대)"},
            "gemma4-12b": {"recommended_context_length": 2048, "max_context_length": 4096, "peak_vram_mb": 8900, "tpot_tok_per_sec": 30.52, "status": "AVAILABLE", "description": "[신규] Gemma 12B 대용량 모델 (RTX 3060 12GB)"},
            "bge-m3": {"recommended_context_length": 2048, "max_context_length": 4096, "peak_vram_mb": 605, "tpot_tok_per_sec": 7.46, "status": "ACTIVE_EMBEDDING", "description": "임베딩 전용 (독립 포트 8090)"},
            "bge-reranker-v2-m3": {"recommended_context_length": 2048, "max_context_length": 4096, "peak_vram_mb": 606, "tpot_tok_per_sec": 7.30, "status": "ACTIVE_RERANK", "description": "리랭킹 전용 (독립 포트 8091)"}
        }
    }

    samples_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    config_file = samples_dir / "config.json"
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in data.items():
                    if not k.startswith("_") and v is not None:
                        config[k] = v
        except Exception:
            pass

    config["server_host"] = active_host
    if os.getenv("DEFAULT_MODEL"):
        config["default_model"] = os.getenv("DEFAULT_MODEL")
    return config


def get_server_host() -> str:
    """로컬 게이트웨이(127.0.0.1 / vllm-serv-gateway)를 1순위로 감지합니다."""
    env_host = os.getenv("SERVER_HOST") or os.getenv("MODEL_GATEWAY_HOST") or os.getenv("OPENAI_BASE_URL")
    if env_host:
        return _format_host_url(env_host)

    local_hosts = ["http://127.0.0.1", "http://vllm-serv-gateway", "http://host.docker.internal"]
    for host in local_hosts:
        try:
            r = httpx.get(f"{host}:8081/v1/models", timeout=1.0, headers={"Connection": "close"})
            if r.status_code == 200:
                return host
        except Exception:
            pass

    return "http://127.0.0.1"


def get_available_llm_models() -> list:
    """현재 활성화된 서버(/v1/models)에 실제 탑재된 LLM 대화 모델 목록만 동적으로 조회하여 반환합니다."""
    cfg = load_sample_config()
    host = cfg["server_host"]
    port = cfg["main_port"]
    url = f"{host}:{port}/v1/models"

    default_all_llms = ["qwen3.5-2b", "qwen3.5-4b", "qwen3.5-9b", "gemma4-e2b", "gemma4-e4b"]

    try:
        r = httpx.get(url, timeout=3.0, headers={"Connection": "close"})
        if r.status_code == 200:
            models_data = r.json().get("data", [])
            server_models = [m["id"] for m in models_data]
            # 임베딩/리랭커 모델 제외한 순수 LLM 대화 모델만 필터링
            llm_models = [m for m in server_models if m not in ["bge-m3", "bge-reranker-v2-m3"]]
            if llm_models:
                return llm_models
    except Exception:
        pass

    return default_all_llms


def _format_host_url(host: str) -> str:
    """URL 문자열 스킴(http://)을 통일하고 포트 번호 결합을 위한 순수 호스트 명을 획득합니다."""
    host = host.strip().rstrip("/")
    if not host.startswith("http://") and not host.startswith("https://"):
        host = f"http://{host}"
    
    parts = host.split("://", 1)
    scheme = parts[0]
    rest = parts[1]
    if ":" in rest:
        rest = rest.split(":", 1)[0]
    return f"{scheme}://{rest}"


def get_openai_client(port: int = None) -> OpenAI:
    """OpenAI 공식 파이썬 SDK 클라이언트 객체를 생성하여 반환합니다."""
    cfg = load_sample_config()
    host = cfg["server_host"]
    if port is None:
        port = cfg["main_port"]
    base_url = f"{host}:{port}/v1"
    api_key = os.environ.get("OPENAI_API_KEY", "EMPTY")
    return OpenAI(base_url=base_url, api_key=api_key)


def get_httpx_client(timeout: float = 120.0) -> httpx.Client:
    """REST API 직접 호출을 위한 httpx 동기 클라이언트 세션을 생성합니다."""
    return httpx.Client(timeout=timeout)


def check_server_health(host: str = None, port: int = 8081, service_name: str = "vllm_serv 메인 API") -> bool:
    """지정된 서버 포트로 헬스체크(/health 또는 /v1/models)를 보내 정상 구동 여부를 미리 검사합니다."""
    if host is None:
        host = get_server_host()
    else:
        host = _format_host_url(host)

    target_base = f"{host}:{port}"

    for endpoint in ["/health", "/v1/models"]:
        url = f"{target_base}{endpoint}"
        try:
            resp = httpx.get(url, timeout=3.0, headers={"Connection": "close"})
            if resp.status_code == 200:
                return True
            if resp.status_code == 503:
                print(f"⚠️ [{service_name}] 서버 백엔드 모델 로딩 중... (잠시 후 다시 시도해 주세요)")
                return False
        except (httpx.ConnectError, httpx.TimeoutException):
            continue

    print(f"❌ [{service_name}] 서버 연결 실패 (대상 주소: {target_base})")
    return False


def print_section_header(title: str) -> None:
    """실습 구분을 쉽게 돕는 시각적 구분선 헤더를 출력합니다."""
    print("\n" + "=" * 65)
    print(f"📌 {title}")
    print("=" * 65)


def print_performance_summary(
    mode_name: str,
    t_start: float,
    t_end: float,
    t_first: float = None,
    gen_tokens: int = 0,
    finish_reason: str = "stop"
) -> dict:
    """요청 시각, 완료 시각, 첫 토큰 응답 지연(TTFT), 초당 생성 속도(TPS)를 측정하고 시각화합니다."""
    start_str = datetime.datetime.fromtimestamp(t_start).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    end_str = datetime.datetime.fromtimestamp(t_end).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    total_elapsed = t_end - t_start

    print(f"\n📊 [{mode_name} 성능 측정 지표]")
    print(f"   ⏱️ 요청 시작 시각  : {start_str}")
    
    ttft = None
    tps = 0.0
    if t_first is not None:
        ttft = t_first - t_start
        first_str = datetime.datetime.fromtimestamp(t_first).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        print(f"   ⏱️ 첫 토큰(답변시작): {first_str} (TTFT 첫 토큰 대기지연: {ttft:.2f}초)")
        gen_time = t_end - t_first
        if gen_time > 0 and gen_tokens > 0:
            tps = gen_tokens / gen_time
            print(f"   ⏱️ 답변 완결 생성시간: {gen_time:.2f}초 (답변 시작 후 평균 생성 속도: {tps:.1f} tokens/s)")
    else:
        if total_elapsed > 0 and gen_tokens > 0:
            tps = gen_tokens / total_elapsed

    print(f"   ⏱️ 전체 완료 시각  : {end_str} (총 소요시간: {total_elapsed:.2f}초)")
    if gen_tokens > 0:
        print(f"   📊 생성 토큰 수     : {gen_tokens}토큰 | 평균 속도: {tps:.1f} tokens/s")
    print(f"   📊 응답 완결 사유   : {finish_reason}")

    return {
        "mode": mode_name,
        "total_elapsed": total_elapsed,
        "ttft": ttft,
        "gen_tokens": gen_tokens,
        "tps": tps,
        "finish_reason": finish_reason
    }


def print_gpu_vram_benchmark_header(model_name: str = None) -> None:
    """RTX 3060 / GTX 1070 3종 동시 서빙 사양과 지정된 모델의 가용 스펙 정보를 출력합니다."""
    cfg = load_sample_config()
    gpu = cfg.get("gpu_info", {})
    benchmarks = cfg.get("model_benchmarks", {})
    
    print("\n🖥️ [RTX 3060 / GTX 1070 3종 동시 서빙 VRAM 벤치마크 스펙]")
    print(f"   • 활성 서버: {cfg.get('server_host')} ({gpu.get('device_name', 'GPU')} {gpu.get('total_vram_mb', 12288)} MB VRAM)")
    print(f"   • 동시 서빙 데몬: LLM 메인(8081) + BGE-M3(8090) + BGE-Reranker(8091)")

    if model_name and model_name in benchmarks:
        info = benchmarks[model_name]
        print(f"   👉 현재 모델 [{model_name}]: 피크 VRAM {info.get('peak_vram_mb')}MB | 추천맥락 {info.get('recommended_context_length')} / 최대 {info.get('max_context_length')}토큰 | 속도 {info.get('tpot_tok_per_sec')} TPS")
