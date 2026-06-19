from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)
    provider_id: Optional[str] = None
    spec_source_id: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    num_ctx: Optional[int] = Field(default=None, ge=4096)
    reserve_output_tokens: Optional[int] = Field(default=None, ge=512)


class ChatResponse(BaseModel):
    assistant_text: str
    assistant_html: str
    token_report: str
    saved_file: Optional[str] = None


class ContinueRequest(BaseModel):
    history: list[ChatMessage] = Field(default_factory=list)
    provider_id: Optional[str] = None
    spec_source_id: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)


class BackendStatus(BaseModel):
    status: Literal["ok", "error"]
    provider_id: str
    provider_label: str
    base_url: str
    model: str
    models: list[str] = Field(default_factory=list)
    detail: Optional[str] = None


class ProviderConfig(BaseModel):
    id: str
    label: str
    runtime: str
    base_url: str
    model: str
    description: str
    max_input_tokens: int


class SpecSourceConfig(BaseModel):
    id: str
    label: str
    root_path: str
    exists: bool
    description: str


class AppConfig(BaseModel):
    app_name: str
    vllm_base_url: str
    default_model: str
    default_provider_id: str
    providers: list[ProviderConfig]
    default_spec_source_id: str
    spec_sources: list[SpecSourceConfig]
    default_temperature: float
    default_max_tokens: int
    default_num_ctx: int
    min_reserved_output_tokens: int
    spec_prompt_token_budget: int
    spec_prompt_max_context_fraction: float


class SpecFileRow(BaseModel):
    path: str
    kind: str
    chars: int
    estimated_tokens: int
    used_in_prompt: bool
    notes: str = ""


class SpecScanResponse(BaseModel):
    spec_source_id: str
    spec_source_label: str
    spec_root: str
    spec_root_exists: bool
    note: str
    total_estimated_tokens: int
    files: list[SpecFileRow]
