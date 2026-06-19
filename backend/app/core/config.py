from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
DGX_QWEN_CODER_MAX_INPUT_TOKENS = 262_144
M1_QWEN_CODER_MAX_INPUT_TOKENS = 32_768
DGX_QWEN_CODER_SPEC_PROMPT_BUDGET = int(DGX_QWEN_CODER_MAX_INPUT_TOKENS * 0.30)


@dataclass(frozen=True)
class ServerProvider:
    id: str
    label: str
    runtime: str
    base_url: str
    model: str
    description: str
    max_input_tokens: int


@dataclass(frozen=True)
class SpecSource:
    id: str
    label: str
    root_path: Path
    description: str


class Settings(BaseSettings):
    app_name: str = "QScript Coding Assistant API"
    environment: str = Field(default="development", alias="APP_ENV")

    project_root: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[3],
        alias="PROJECT_ROOT",
    )
    generated_dir_name: str = "generated-src-txt"
    default_spec_source_id: str = Field(default="project_spec", alias="APP_DEFAULT_SPEC_SOURCE")
    usb_spec_root: Path = Field(default=Path("/media/peterstroessler/C6B5-FBEC/spec"), alias="USB_SPEC_ROOT")

    cors_origins: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://192.168.1.196:5173",
        ],
        alias="CORS_ORIGINS",
    )

    vllm_base_url: str = Field(default="http://127.0.0.1:8042/v1", alias="VLLM_BASE_URL")
    vllm_api_key: str = Field(default="dummy", alias="VLLM_API_KEY")
    default_model: str = Field(default="Qwen/Qwen3-Coder-30B-A3B-Instruct", alias="VLLM_MODEL")
    default_provider_id: str | None = Field(default=None, alias="APP_DEFAULT_PROVIDER")
    dgx_vllm_base_url: str = Field(default="http://127.0.0.1:8042/v1", alias="DGX_VLLM_BASE_URL")
    dgx_vllm_model: str = Field(default="Qwen/Qwen3-Coder-30B-A3B-Instruct", alias="DGX_VLLM_MODEL")
    m1_ollama_base_url: str = Field(default="http://127.0.0.1:11434/v1", alias="M1_OLLAMA_BASE_URL")
    m1_ollama_model: str = Field(default="qwen2.5-coder:3b", alias="M1_OLLAMA_MODEL")
    default_max_tokens: int = Field(default=8192, alias="VLLM_MAX_TOKENS")
    default_temperature: float = Field(default=0.2, alias="VLLM_TEMPERATURE")
    default_num_ctx: int = Field(default=DGX_QWEN_CODER_MAX_INPUT_TOKENS, alias="VLLM_NUM_CTX")
    min_reserved_output_tokens: int = Field(default=8192, alias="VLLM_RESERVED_OUTPUT_TOKENS")
    spec_prompt_token_budget: int = Field(default=DGX_QWEN_CODER_SPEC_PROMPT_BUDGET, alias="SPEC_PROMPT_TOKEN_BUDGET")
    spec_prompt_max_context_fraction: float = Field(default=0.30, alias="SPEC_PROMPT_MAX_CONTEXT_FRACTION")
    request_timeout_seconds: float = Field(default=600.0, alias="VLLM_TIMEOUT_SECONDS")

    model_config = SettingsConfigDict(
        env_file=ROOT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def generated_dir(self) -> Path:
        return self.project_root / self.generated_dir_name

    @property
    def providers(self) -> list[ServerProvider]:
        return [
            ServerProvider(
                id="dgx_vllm_qwen",
                label="DGX Spark: vLLM / Qwen3-Coder 30B A3B",
                runtime="vllm",
                base_url=self.dgx_vllm_base_url,
                model=self.dgx_vllm_model,
                description="Use this when the DGX Spark vLLM server is running on port 8042.",
                max_input_tokens=self.default_num_ctx,
            ),
            ServerProvider(
                id="m1_ollama_qwen_coder",
                label="M1 Mac: Ollama / qwen2.5-coder:3b",
                runtime="ollama",
                base_url=self.m1_ollama_base_url,
                model=self.m1_ollama_model,
                description="Use this on the M1 Mac with Ollama's OpenAI-compatible API on port 11434.",
                max_input_tokens=M1_QWEN_CODER_MAX_INPUT_TOKENS,
            ),
        ]

    @property
    def resolved_default_provider_id(self) -> str:
        if self.default_provider_id:
            return self.default_provider_id
        if "11434" in self.vllm_base_url or self.default_model == self.m1_ollama_model:
            return "m1_ollama_qwen_coder"
        return "dgx_vllm_qwen"

    def provider_for_id(self, provider_id: str | None) -> ServerProvider:
        selected = provider_id or self.resolved_default_provider_id
        if selected == "m1_ollama_gpt_oss":
            selected = "m1_ollama_qwen_coder"
        for provider in self.providers:
            if provider.id == selected:
                return provider
        return self.providers[0]

    @property
    def resolved_usb_spec_root(self) -> Path:
        username = os.getenv("USER") or os.getenv("USERNAME") or ""
        candidates = [
            self.usb_spec_root,
            Path("/media/peterstroessler/C6B5-FBEC/spec"),
            Path("/mnt/C6B5-FBEC/spec"),
            Path("/media/C6B5-FBEC/spec"),
            Path("/run/media/C6B5-FBEC/spec"),
            Path("/Volumes/Untitled/spec"),
            Path("/mnt/Untitled/spec"),
            Path("/media/Untitled/spec"),
            Path("/run/media/Untitled/spec"),
        ]

        if username:
            candidates.extend(
                [
                    Path("/media") / username / "C6B5-FBEC" / "spec",
                    Path("/run/media") / username / "C6B5-FBEC" / "spec",
                    Path("/media") / username / "Untitled" / "spec",
                    Path("/run/media") / username / "Untitled" / "spec",
                ]
            )

        seen: set[Path] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            if candidate.exists() and candidate.is_dir():
                return candidate

        return self.usb_spec_root

    @property
    def spec_sources(self) -> list[SpecSource]:
        return [
            SpecSource(
                id="project_spec",
                label="Project spec folder",
                root_path=self.project_root / "spec",
                description="Use the spec folder inside this project.",
            ),
            SpecSource(
                id="usb_untitled_spec",
                label="External device: C6B5-FBEC/spec",
                root_path=self.resolved_usb_spec_root,
                description=(
                    "Use the spec folder on the mounted external device C6B5-FBEC. "
                    "DGX/Linux usually uses /media/$USER/C6B5-FBEC/spec, "
                    "/run/media/$USER/C6B5-FBEC/spec, or /mnt/C6B5-FBEC/spec."
                ),
            ),
        ]

    def spec_source_for_id(self, spec_source_id: str | None) -> SpecSource:
        selected = spec_source_id or self.default_spec_source_id
        for source in self.spec_sources:
            if source.id == selected:
                return source
        return self.spec_sources[0]


@lru_cache
def get_settings() -> Settings:
    return Settings()
