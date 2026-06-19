from openai import APIConnectionError, APIStatusError, APITimeoutError

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.core.config import Settings, get_settings
from app.models.schemas import (
    AppConfig,
    BackendStatus,
    ChatRequest,
    ChatResponse,
    ContinueRequest,
    ProviderConfig,
    SpecFileRow,
    SpecScanResponse,
    SpecSourceConfig,
)
from app.services.chat import ChatService
from app.services.spec_context import SpecContextService
from app.services.vllm_client import VllmClient


def create_app() -> FastAPI:
    settings = get_settings()
    api = FastAPI(title=settings.app_name, version="1.0.0")
    api.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    spec_context = SpecContextService(settings.project_root)
    chat_service = ChatService(settings, spec_context)

    def get_spec_context() -> SpecContextService:
        return spec_context

    def get_chat_service() -> ChatService:
        return chat_service

    @api.get("/")
    async def root(settings_dep: Settings = Depends(get_settings)) -> dict[str, str]:
        return {
            "app": settings_dep.app_name,
            "status": "ok",
            "health": "/health",
            "config": "/api/config",
            "docs": "/docs",
        }

    @api.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/api/config", response_model=AppConfig)
    async def config(settings_dep: Settings = Depends(get_settings)) -> AppConfig:
        return AppConfig(
            app_name=settings_dep.app_name,
            vllm_base_url=settings_dep.vllm_base_url,
            default_model=settings_dep.default_model,
            default_provider_id=settings_dep.resolved_default_provider_id,
            providers=[
                ProviderConfig(
                    id=provider.id,
                    label=provider.label,
                    runtime=provider.runtime,
                    base_url=provider.base_url,
                    model=provider.model,
                    description=provider.description,
                    max_input_tokens=provider.max_input_tokens,
                )
                for provider in settings_dep.providers
            ],
            default_spec_source_id=settings_dep.default_spec_source_id,
            spec_sources=[
                SpecSourceConfig(
                    id=source.id,
                    label=source.label,
                    root_path=str(source.root_path),
                    exists=source.root_path.exists() and source.root_path.is_dir(),
                    description=source.description,
                )
                for source in settings_dep.spec_sources
            ],
            default_temperature=settings_dep.default_temperature,
            default_max_tokens=settings_dep.default_max_tokens,
            default_num_ctx=settings_dep.default_num_ctx,
            min_reserved_output_tokens=settings_dep.min_reserved_output_tokens,
            spec_prompt_token_budget=settings_dep.spec_prompt_token_budget,
            spec_prompt_max_context_fraction=settings_dep.spec_prompt_max_context_fraction,
        )

    @api.get("/api/backend", response_model=BackendStatus)
    async def backend_status(
        provider_id: str | None = Query(default=None),
        settings_dep: Settings = Depends(get_settings),
    ) -> BackendStatus:
        provider = settings_dep.provider_for_id(provider_id)
        model_client = VllmClient(
            base_url=provider.base_url,
            api_key=settings_dep.vllm_api_key,
            timeout_seconds=settings_dep.request_timeout_seconds,
        )
        try:
            models = await model_client.list_models()
            return BackendStatus(
                status="ok",
                provider_id=provider.id,
                provider_label=provider.label,
                base_url=model_client.base_url,
                model=provider.model,
                models=models,
            )
        except APIConnectionError:
            return BackendStatus(
                status="error",
                provider_id=provider.id,
                provider_label=provider.label,
                base_url=model_client.base_url,
                model=provider.model,
                models=[],
                detail=(
                    f"{provider.label} is not reachable at {model_client.base_url}. "
                    "Use the DGX Spark option when vLLM is running on port 8042, or the M1 Mac option when Ollama is running on port 11434."
                ),
            )
        except APITimeoutError:
            return BackendStatus(
                status="error",
                provider_id=provider.id,
                provider_label=provider.label,
                base_url=model_client.base_url,
                model=provider.model,
                models=[],
                detail=f"Timed out while connecting to {provider.label} at {model_client.base_url}.",
            )
        except APIStatusError as exc:
            return BackendStatus(
                status="error",
                provider_id=provider.id,
                provider_label=provider.label,
                base_url=model_client.base_url,
                model=provider.model,
                models=[],
                detail=f"The OpenAI-compatible model server returned HTTP {exc.status_code}: {exc.message}",
            )
        except Exception as exc:
            return BackendStatus(
                status="error",
                provider_id=provider.id,
                provider_label=provider.label,
                base_url=model_client.base_url,
                model=provider.model,
                models=[],
                detail=str(exc),
            )

    @api.get("/api/specs", response_model=SpecScanResponse)
    async def specs(
        spec_source_id: str | None = Query(default=None),
        service: SpecContextService = Depends(get_spec_context),
        settings_dep: Settings = Depends(get_settings),
    ) -> SpecScanResponse:
        spec_source = settings_dep.spec_source_for_id(spec_source_id)
        rows, note = service.scan_token_usage(spec_source.root_path)
        return SpecScanResponse(
            spec_source_id=spec_source.id,
            spec_source_label=spec_source.label,
            spec_root=str(spec_source.root_path),
            spec_root_exists=spec_source.root_path.exists() and spec_source.root_path.is_dir(),
            note=note,
            total_estimated_tokens=sum(row.estimated_tokens for row in rows),
            files=[SpecFileRow(**row.__dict__) for row in rows],
        )

    @api.post("/api/chat", response_model=ChatResponse)
    async def chat(
        request: ChatRequest,
        service: ChatService = Depends(get_chat_service),
    ) -> ChatResponse:
        return await service.chat(request)

    @api.post("/api/chat/stream")
    async def chat_stream(
        request: ChatRequest,
        service: ChatService = Depends(get_chat_service),
    ) -> StreamingResponse:
        return StreamingResponse(
            service.chat_events(request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @api.post("/api/chat/continue", response_model=ChatResponse)
    async def continue_chat(
        request: ContinueRequest,
        service: ChatService = Depends(get_chat_service),
    ) -> ChatResponse:
        return await service.continue_chat(request)

    return api


app = create_app()
