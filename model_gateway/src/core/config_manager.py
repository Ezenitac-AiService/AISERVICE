import os
import json
import time
import tempfile
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, field_validator

from enum import Enum

class TaskTypeEnum(str, Enum):
    LLM = "llm"
    EMBEDDING = "embedding"
    RERANK = "rerank"

class ConnectionPoolConfig(BaseModel):
    max_keepalive_connections: int = 20
    max_connections: int = 100

class ServerConfig(BaseModel):
    """FR-002 & FR-008: Pydantic v2 기반 서버 설정 규격."""
    host: str = "0.0.0.0"
    port: int = 8081
    backend_port: int = 8089
    embedding_backend_port: int = 8090
    rerank_backend_port: int = 8091
    embedding_enabled: bool = True
    rerank_enabled: bool = True
    auxiliary_max_crashes: int = 3
    allowed_subnets: List[str] = Field(default_factory=lambda: ["127.0.0.1", "192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12"])
    firewall_auto_allow: bool = True
    vram_limit_mb: int = 11264
    vram_max_capacity_mb: Optional[int] = None
    healthcheck_timeout_s: int = 120
    graceful_drain_timeout_s: float = 5.0
    connection_pool: ConnectionPoolConfig = Field(default_factory=ConnectionPoolConfig)
    api_key_enabled: bool = False
    api_keys: List[Dict[str, Any]] = Field(default_factory=list)
    admin_secret: str = "aiservice"
    speculative_decoding: Dict[str, Any] = Field(default_factory=lambda: {"enabled": False, "draft_model": "qwen3.5-2b"})
    structured_output: Dict[str, Any] = Field(default_factory=lambda: {"enabled": True, "strict_json_schema": True})
    # Spec 031: GPU Queue & Sliding Timeout Configuration
    max_gpu_concurrent_slots: int = 1      # 가변 슬롯 (단일 GPU 기본값 1, 환경변수 MAX_GPU_CONCURRENT_SLOTS)
    queue_capacity: int = 30               # 최대 큐 용량 (FR-009)
    heartbeat_interval_s: float = 15.0     # SSE Keep-Alive 주기 (FR-002)
    coalescing_window_s: float = 5.0       # Request Coalescing 윈도우 (FR-011)
    model_config = {"extra": "allow"}

    @field_validator("port", "backend_port", "embedding_backend_port", "rerank_backend_port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not (1024 <= v <= 65535):
            raise ValueError(f"Port must be between 1024 and 65535, got {v}")
        return v

class ModelCatalogEntry(BaseModel):
    """FR-001: Pydantic v2 기반 단일 모델 명세 규격."""
    name: str
    repo_id: str
    filename: str
    clip_filename: Optional[str] = None
    target_dir: str
    model_path: str
    clip_path: Optional[str] = None
    chat_template: Optional[str] = None
    default_n_ctx: int = 4096
    vram_est_mb: int
    requires_mmproj: bool = False
    quant_type: str
    size_gb: float
    task_type: TaskTypeEnum = TaskTypeEnum.LLM
    default_port: Optional[int] = None

class ModelContextProfileEntry(BaseModel):
    """098-benchmark-all-serviced-models: Pydantic v2 기반 단일 모델 컨텍스트 윈도우 프로필 엔티티."""
    max_context_length: int = 4096
    recommended_context_length: int = 4096
    binary_search_steps: List[Dict[str, Any]] = Field(default_factory=list)
    peak_vram_mb: int = 4200
    tpot_tok_per_sec: float = 0.0
    scaling_tested: bool = True
    is_supported: bool = True
    last_tested_at: Optional[str] = None

class ConfigManager:
    """Manages system configuration with same-directory atomic replace, chmod 0600, Pydantic v2 validation, and memory caching."""

    DEFAULT_CONFIG = {
        "current_model": "qwen3.5-2b",
        "current_n_ctx": 65536,
        "available_presets": ["gemma4-e2b", "gemma4-e4b", "gemma4-12b", "qwen3.5-2b", "qwen3.5-4b", "qwen3.5-9b"]
    }

    def __init__(self, config_path: str = "config/model_config.json"):
        if not os.path.isabs(config_path) and not os.path.exists(config_path):
            pkg_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            candidate = os.path.join(pkg_root, config_path)
            if os.path.exists(candidate) or os.path.exists(os.path.dirname(candidate)):
                config_path = candidate

        self.config_path = config_path
        self._cache: Optional[Dict[str, Any]] = None
        self._server_config_cache: Optional[Dict[str, Any]] = None
        self._model_catalog_cache: Optional[Dict[str, Any]] = None
        self._platform_profiles_cache: Optional[Dict[str, Any]] = None
        self._ensure_config_exists()


    def _ensure_config_exists(self) -> None:
        dir_name = os.path.dirname(self.config_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        if not os.path.exists(self.config_path):
            if self.config_path.endswith("server_config.json"):
                self.save_config(ServerConfig().model_dump())
            else:
                self.save_config(self.DEFAULT_CONFIG)


    def get_config(self) -> dict:
        """Returns cached configuration if available, otherwise reads from file."""
        if self._cache is not None:
            return self._cache.copy()
        if not os.path.exists(self.config_path):
            self._ensure_config_exists()
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._cache = json.load(f)
                return self._cache.copy()
        except Exception:
            return self.DEFAULT_CONFIG.copy()

    def save_config(self, config: dict) -> None:
        """Saves configuration using same-directory atomic replace and chmod 0600 permissions."""
        self._write_atomic(config)
        self._cache = config.copy()

    def _write_atomic(self, config: dict) -> None:
        """FR-003 & FR-008: Writes config to temp file in SAME dir with chmod 0600 and os.replace."""
        target_dir = os.path.dirname(self.config_path) or "."
        os.makedirs(target_dir, exist_ok=True)

        with tempfile.NamedTemporaryFile("w", dir=target_dir, delete=False, encoding="utf-8") as tf:
            temp_name = tf.name
            json.dump(config, tf, indent=4)
            tf.flush()
            os.fsync(tf.fileno())

        try:
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, self.config_path)
        except Exception:
            if os.path.exists(temp_name):
                os.remove(temp_name)
            raise

    def get(self, key: str, default: Any = None) -> Any:
        cfg = self.get_config()
        return cfg.get(key, default)

    def set(self, key: str, val: Any) -> None:
        cfg = self.get_config()
        cfg[key] = val
        self.save_config(cfg)

    def update_config(self, **kwargs) -> dict:
        current = self.get_config()
        current.update(kwargs)
        self.save_config(current)
        return current.copy()


    def invalidate_cache(self) -> None:
        """Explicitly invalidates memory cache."""
        self._cache = None

    def get_default_model(self) -> str:
        """Returns the single source of truth default active model."""
        # 1. Environment variable
        env_model = os.environ.get("FAST_LLM_MODEL") or os.environ.get("SYNTHESIS_LLM_MODEL") or os.environ.get("DEFAULT_MODEL")
        if env_model:
            return env_model
        # 2. Server config
        server_cfg = self.get_server_config()
        if "default_model" in server_cfg and server_cfg["default_model"]:
            return server_cfg["default_model"]
        # 3. Model config
        cfg = self.get_config()
        return cfg.get("current_model", "qwen3.5-2b")

    def get_current_n_ctx(self) -> int:
        """Returns the single source of truth current context window size."""
        env_ctx = os.environ.get("DEFAULT_CONTEXT_WINDOW") or os.environ.get("LLAMA_N_CTX")
        if env_ctx:
            try:
                return int(env_ctx)
            except ValueError:
                pass
        server_cfg = self.get_server_config()
        if "current_n_ctx" in server_cfg and server_cfg["current_n_ctx"]:
            return int(server_cfg["current_n_ctx"])
        cfg = self.get_config()
        return int(cfg.get("current_n_ctx", 16384))

    def get_dynamic_serving_profile(self) -> Dict[str, Any]:
        """Calculates dynamic hardware profile and serving parameters via 3-axis decoupled evaluation engine."""
        try:
            from src.core.gpu_detector import detect_hardware_capabilities
            profile = detect_hardware_capabilities()
            return profile.model_dump()
        except Exception as e:
            return {
                "recommended_model": self.get_default_model(),
                "dynamic_n_ctx": self.get_current_n_ctx(),
                "use_flash_attn": False,
                "use_q8_kv": True,
                "force_all_gpu_layers": True
            }

    # -------------------------------------------------------------------------
    # FR-001: Model Catalog JSON 외부화 및 Pydantic 검증 로더
    # -------------------------------------------------------------------------
    _model_catalog_cache: Optional[Dict[str, Any]] = None

    def get_model_catalog(self) -> Dict[str, Any]:
        """FR-001: config/model_catalog.json에서 모델 카탈로그를 로드하고 캐싱합니다."""
        if self._model_catalog_cache:
            return self._model_catalog_cache.copy()

        catalog_path = os.path.join(os.path.dirname(self.config_path), "model_catalog.json")
        if not os.path.exists(catalog_path):
            pkg_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            candidate = os.path.join(pkg_root, "config", "model_catalog.json")
            if os.path.exists(candidate):
                catalog_path = candidate

        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                catalog = json.load(f)
            if catalog:
                self._model_catalog_cache = catalog
                return catalog.copy()
            return {}
        except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
            print(f"[ConfigManager] Warning: model_catalog.json load failed: {e}")
            return {}

    MODEL_KEY_ALIASES = {
        "gemma4-2b": "gemma4-e2b",
        "gemma4-4b": "gemma4-e4b",
        "gemma-4-2b": "gemma4-e2b",
        "gemma-4-4b": "gemma4-e4b",
        "gemma-4-12b": "gemma4-12b",
    }

    def resolve_model_id(self, model_id: str) -> str:
        """Resolves legacy or alternate model ID keys to standard catalog keys."""
        return self.MODEL_KEY_ALIASES.get(model_id, model_id)

    def get_model_config(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Returns catalog configuration dictionary for a given model ID or alias."""
        resolved_id = self.resolve_model_id(model_id)
        catalog = self.get_model_catalog()
        return catalog.get(resolved_id)

    def get_absolute_path(self, path: Optional[str]) -> Optional[str]:
        """Converts a relative path to absolute path relative to project root."""
        if not path:
            return None
        if os.path.isabs(path):
            return path
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.abspath(os.path.join(project_root, path))

    # -------------------------------------------------------------------------
    # FR-002: Server Config JSON 외부화 및 Pydantic v2 로더
    # -------------------------------------------------------------------------
    _server_config_cache: Optional[Dict[str, Any]] = None

    def get_server_config(self) -> Dict[str, Any]:
        """FR-002: config/server_config.json에서 Pydantic v2 기반 서버 설정을 로드합니다.

        환경변수 LLAMA_PORT, LLAMA_HOST가 설정되어 있으면 JSON 값을 오버라이드합니다.
        """
        if self._server_config_cache is not None:
            return self._server_config_cache.copy()

        if self.config_path.endswith("server_config.json"):
            server_config_path = self.config_path
        else:
            server_config_path = os.path.join(os.path.dirname(self.config_path), "server_config.json")

        if not os.path.exists(server_config_path):
            pkg_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            candidate = os.path.join(pkg_root, "config", "server_config.json")
            if os.path.exists(candidate):
                server_config_path = candidate

        raw_config = {}
        try:
            with open(server_config_path, "r", encoding="utf-8") as f:
                raw_config = json.load(f)
        except Exception as e:
            print(f"[ConfigManager] Warning: server_config.json load failed (using defaults): {e}")

        try:
            parsed_cfg = ServerConfig(**raw_config)
            config = parsed_cfg.model_dump()
        except Exception as e:
            print(f"[ConfigManager] Warning: ServerConfig parsing warning (using defaults): {e}")
            config = ServerConfig().model_dump()

        env_port = os.environ.get("LLAMA_PORT")
        if env_port is not None:
            try:
                config["port"] = int(env_port)
            except ValueError:
                pass

        env_secret = os.environ.get("VLLM_ADMIN_SECRET")
        if env_secret:
            config["admin_secret"] = env_secret

        self._server_config_cache = config
        return config.copy()

    def save_server_config(self, config_dict: Dict[str, Any]) -> None:
        """Saves server_config.json atomically with chmod 0600 and invalidates cache."""
        if self.config_path.endswith("server_config.json"):
            server_config_path = self.config_path
        else:
            server_config_path = os.path.join(os.path.dirname(self.config_path), "server_config.json")

        dir_name = os.path.dirname(server_config_path)
        with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
            json.dump(config_dict, tf, indent=4, ensure_ascii=False)
            tf.flush()
            os.fsync(tf.fileno())
            temp_name = tf.name

        try:
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, server_config_path)
            self._server_config_cache = config_dict.copy()
        except Exception:
            if os.path.exists(temp_name):
                os.remove(temp_name)
            raise

    def get_vram_max_capacity_mb(self) -> int:
        """FR-004: Returns dynamic VRAM capacity in MB via NVML detection, platform profile matching, or server config."""
        cfg = self.get_server_config()
        cap = cfg.get("vram_max_capacity_mb")
        if cap is not None and isinstance(cap, int) and cap > 0:
            return cap

        try:
            from src.core.gpu_detector import GPUManager
            vram_info = GPUManager.get_gpu_vram_info()
            if vram_info and vram_info.get("total_mb", 0) > 0:
                return vram_info["total_mb"]
        except Exception:
            pass

        try:
            from src.core.cpu_detector import CPUHardwareDetector
            matched_id = CPUHardwareDetector.match_platform_profile()
            profile = self.get_platform_profile(matched_id)
            if profile and "vram_mb" in profile:
                return profile["vram_mb"]
        except Exception:
            pass

        return 11264


    def _write_atomic_server_config(self, config: dict, **kwargs) -> None:
        """Saves server_config.json atomically."""
        config.update(kwargs)
        if self.config_path.endswith("server_config.json"):
            server_config_path = self.config_path
        else:
            server_config_path = os.path.join(os.path.dirname(self.config_path), "server_config.json")

        target_dir = os.path.dirname(server_config_path) or "."
        os.makedirs(target_dir, exist_ok=True)

        with tempfile.NamedTemporaryFile("w", dir=target_dir, delete=False, encoding="utf-8") as tf:
            temp_name = tf.name
            json.dump(config, tf, indent=4)
            tf.flush()
            os.fsync(tf.fileno())

        try:
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, server_config_path)
        except Exception:
            if os.path.exists(temp_name):
                os.remove(temp_name)
            raise

        self._server_config_cache = config.copy()


    def invalidate_all_caches(self) -> None:
        """모든 설정 캐시를 무효화합니다."""
        self._cache = None
        self._model_catalog_cache = None
        self._server_config_cache = None
        self._platform_profiles_cache = None

    # -------------------------------------------------------------------------
    # FR-006: Platform Profiles JSON 외부화 및 로더
    # -------------------------------------------------------------------------
    _platform_profiles_cache: Optional[Dict[str, Any]] = None

    def get_platform_profiles(self) -> Dict[str, Any]:
        """FR-006: config/platform_profiles.json에서 타겟 플랫폼 프로필을 로드하고 캐싱합니다."""
        if self._platform_profiles_cache is not None:
            return self._platform_profiles_cache.copy()

        profiles_path = os.path.join(os.path.dirname(self.config_path), "platform_profiles.json")
        try:
            with open(profiles_path, "r", encoding="utf-8") as f:
                profiles = json.load(f)
            self._platform_profiles_cache = profiles
            return profiles.copy()
        except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
            print(f"[ConfigManager] ⚠️ platform_profiles.json 로드 실패: {e}")
            self._platform_profiles_cache = {}
            return {}

    def get_platform_profile(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """단일 타겟 플랫폼 프로필 정보를 조회합니다."""
        profiles = self.get_platform_profiles()
        return profiles.get(profile_id)

    def get_allowed_subnets(self) -> List[str]:
        """FR-001 & FR-002: 정적 프로필 설정과 듀얼 NIC 활성 LAN IP 기반 동적 CIDR 대역을 결합하여 중복 제거된 allowed_subnets 반환."""
        from src.core.network_detector import NetworkDetector

        base_subnets = ["127.0.0.1", "192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12"]

        server_cfg = self.get_server_config()
        cfg_subnets = server_cfg.get("allowed_subnets", [])

        profile_subnets = []
        try:
            from src.core.cpu_detector import CPUHardwareDetector
            matched_id = CPUHardwareDetector.match_platform_profile()
            profile = self.get_platform_profile(matched_id)
            if profile and "network" in profile and "allowed_subnets" in profile["network"]:
                profile_subnets = profile["network"]["allowed_subnets"]
        except Exception:
            pass

        dynamic_subnets = []
        try:
            active_ips = NetworkDetector.get_active_lan_ips()
            for ip in active_ips:
                if ip.startswith("192.168."):
                    dynamic_subnets.append("192.168.0.0/16")
                elif ip.startswith("10."):
                    dynamic_subnets.append("10.0.0.0/8")
                elif ip.startswith("172."):
                    dynamic_subnets.append("172.16.0.0/12")
                elif ip and ip != "127.0.0.1":
                    parts = ip.split(".")
                    if len(parts) == 4:
                        dynamic_subnets.append(f"{'.'.join(parts[:3])}.0/24")
        except Exception:
            pass

        combined = base_subnets + cfg_subnets + profile_subnets + dynamic_subnets
        return list(dict.fromkeys([s for s in combined if s]))

    def get_detected_network_info(self) -> Dict[str, Any]:
        """FR-002: 듀얼 NIC 미할당 포트 필터링 및 활성 LAN IP와 네트워크 바인딩 정보를 탐지합니다."""
        from src.core.network_detector import NetworkDetector
        from src.core.firewall_manager import FirewallManager

        server_cfg = self.get_server_config()
        bind_host = server_cfg.get("host", "0.0.0.0")
        api_port = server_cfg.get("port", 8081)
        backend_port = server_cfg.get("backend_port", 8089)

        active_ips = NetworkDetector.get_active_lan_ips()
        
        # Fire firewall port allow attempt if enabled
        if server_cfg.get("firewall_auto_allow", True):
            try:
                fm = FirewallManager()
                fm.ensure_service_ports_open([api_port, backend_port])
            except Exception as e:
                print(f"[ConfigManager] ⚠️ 방화벽 개방 시도 경고: {e}")

        return {
            "bind_host": bind_host,
            "api_port": api_port,
            "backend_port": backend_port,
            "detected_active_ips": active_ips,
            "allowed_subnets": self.get_allowed_subnets()
        }

    def load_model_context_profiles(self) -> Dict[str, Any]:
        """098-benchmark-all-serviced-models: Loads config/model_context_profiles.json cache atomically."""
        profiles_path = os.path.join(os.path.dirname(self.config_path), "model_context_profiles.json")
        if not os.path.exists(profiles_path):
            profiles_path = "config/model_context_profiles.json"
        try:
            with open(profiles_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"generated_at": "", "system_hardware": {}, "profiles": {}}

    def save_model_context_profiles(self, profiles_data: Dict[str, Any]) -> None:
        """098-benchmark-all-serviced-models: Atomically saves config/model_context_profiles.json with chmod 0600."""
        profiles_path = os.path.join(os.path.dirname(self.config_path), "model_context_profiles.json")
        if not self.config_path.endswith("server_config.json") and not os.path.isabs(self.config_path):
            profiles_path = "config/model_context_profiles.json"
        target_dir = os.path.dirname(profiles_path) or "."
        os.makedirs(target_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=target_dir, delete=False, encoding="utf-8") as tf:
            json.dump(profiles_data, tf, indent=2, ensure_ascii=False)
            tf.flush()
            os.fsync(tf.fileno())
            temp_name = tf.name
        try:
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, profiles_path)
        except Exception:
            if os.path.exists(temp_name):
                os.remove(temp_name)
            raise

    def merge_and_save_model_context_profiles(self, new_profiles: Dict[str, Any], system_hardware: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Atomically loads existing profiles, merges new_profiles into existing profiles, and saves."""
        current_data = self.load_model_context_profiles()
        existing_profiles = current_data.get("profiles", {})
        if not isinstance(existing_profiles, dict):
            existing_profiles = {}

        for m_id, prof in new_profiles.items():
            existing_profiles[m_id] = prof

        hardware = system_hardware if system_hardware else current_data.get("system_hardware", {})
        merged_data = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "system_hardware": hardware,
            "profiles": existing_profiles
        }
        self.save_model_context_profiles(merged_data)
        return merged_data

