import json
from collections.abc import AsyncIterator

from app.core.config import ServerProvider, Settings
from app.models.schemas import ChatMessage, ChatRequest, ChatResponse, ContinueRequest
from app.services.html import message_to_html, source_to_html
from app.services.source_output import CONTINUE_TAIL_CHARS, extract_source_only, save_generated_txt
from app.services.spec_context import SpecContextService, render_token_report
from app.services.vllm_client import VllmClient


class ChatService:
    def __init__(self, settings: Settings, spec_context: SpecContextService) -> None:
        self.settings = settings
        self.spec_context = spec_context

    def _runtime_options(self, request: ChatRequest | ContinueRequest) -> tuple[ServerProvider, VllmClient, str, float, int]:
        provider = self.settings.provider_for_id(request.provider_id)
        client = VllmClient(
            base_url=provider.base_url,
            api_key=self.settings.vllm_api_key,
            timeout_seconds=self.settings.request_timeout_seconds,
        )
        model = request.model or provider.model
        temperature = (
            self.settings.default_temperature
            if request.temperature is None
            else float(request.temperature)
        )
        max_tokens = request.max_tokens or self.settings.default_max_tokens
        return provider, client, model, temperature, int(max_tokens)

    @staticmethod
    def _history_dicts(history: list[ChatMessage]) -> list[dict[str, str]]:
        return [{"role": item.role, "content": item.content} for item in history]

    def _num_ctx(self, request_num_ctx: int | None, provider: ServerProvider) -> int:
        ceiling = max(4096, int(provider.max_input_tokens or self.settings.default_num_ctx))
        requested = int(request_num_ctx or min(self.settings.default_num_ctx, ceiling))
        return min(max(4096, requested), ceiling)

    def _spec_token_budget(self, num_ctx: int) -> int:
        ratio_budget = int(num_ctx * self.settings.spec_prompt_max_context_fraction)
        return min(self.settings.spec_prompt_token_budget, ratio_budget)

    async def chat(self, request: ChatRequest) -> ChatResponse:
        provider, client, model, temperature, max_tokens = self._runtime_options(request)
        spec_source = self.settings.spec_source_for_id(request.spec_source_id)
        reserve_output_tokens = max(
            self.settings.min_reserved_output_tokens,
            int(request.reserve_output_tokens or self.settings.min_reserved_output_tokens),
        )
        num_ctx = self._num_ctx(request.num_ctx, provider)

        assembly = self.spec_context.assemble_prompt(
            user_message=request.message,
            history=self._history_dicts(request.history),
            num_ctx=num_ctx,
            reserve_output_tokens=reserve_output_tokens,
            spec_root=spec_source.root_path,
            spec_token_budget=self._spec_token_budget(num_ctx),
        )
        raw_answer = await client.complete(
            system_prompt=assembly.system_prompt,
            user_prompt=assembly.user_prompt,
            model_name=model,
            temperature=temperature,
            max_tokens=max(512, max_tokens),
        )
        source = extract_source_only(raw_answer)
        saved_file = save_generated_txt(
            content=raw_answer,
            user_message=request.message,
            generated_dir=self.settings.generated_dir,
            prefix="source",
        )
        report = render_token_report(
            assembly,
            provider.base_url,
            model,
            extra=f"spec_source: {spec_source.label}\nspec_root: {spec_source.root_path}",
        )
        if saved_file:
            report += f"\n\nSaved generated TXT: {saved_file}\nTXT format: UTF-8, tabs preserved, CRLF line endings."
        else:
            report += "\n\nNo TXT file was saved because no source code could be extracted."
        return ChatResponse(
            assistant_text=source,
            assistant_html=source_to_html(source),
            token_report=report,
            saved_file=saved_file,
        )

    async def chat_events(self, request: ChatRequest) -> AsyncIterator[str]:
        provider, client, model, temperature, max_tokens = self._runtime_options(request)
        spec_source = self.settings.spec_source_for_id(request.spec_source_id)
        reserve_output_tokens = max(
            self.settings.min_reserved_output_tokens,
            int(request.reserve_output_tokens or self.settings.min_reserved_output_tokens),
        )
        num_ctx = self._num_ctx(request.num_ctx, provider)

        assembly = self.spec_context.assemble_prompt(
            user_message=request.message,
            history=self._history_dicts(request.history),
            num_ctx=num_ctx,
            reserve_output_tokens=reserve_output_tokens,
            spec_root=spec_source.root_path,
            spec_token_budget=self._spec_token_budget(num_ctx),
        )
        token_report = render_token_report(
            assembly,
            provider.base_url,
            model,
            extra=f"spec_source: {spec_source.label}\nspec_root: {spec_source.root_path}",
        )
        yield self._sse("meta", {"token_report": token_report})

        raw_answer = ""
        try:
            async for delta in client.stream(
                system_prompt=assembly.system_prompt,
                user_prompt=assembly.user_prompt,
                model_name=model,
                temperature=temperature,
                max_tokens=max(512, max_tokens),
            ):
                raw_answer += delta
                yield self._sse("delta", {"text": delta})

            source = extract_source_only(raw_answer)
            saved_file = save_generated_txt(
                content=raw_answer,
                user_message=request.message,
                generated_dir=self.settings.generated_dir,
                prefix="source",
            )
            final_report = token_report
            if saved_file:
                final_report += f"\n\nSaved generated TXT: {saved_file}\nTXT format: UTF-8, tabs preserved, CRLF line endings."
            else:
                final_report += "\n\nNo TXT file was saved because no source code could be extracted."

            yield self._sse(
                "final",
                {
                    "assistant_text": source,
                    "assistant_html": source_to_html(source),
                    "token_report": final_report,
                    "saved_file": saved_file,
                },
            )
        except Exception as exc:
            yield self._sse("error", {"message": str(exc), "html": message_to_html(str(exc), "assistant-error")})

    async def continue_chat(self, request: ContinueRequest) -> ChatResponse:
        provider, client, model, temperature, max_tokens = self._runtime_options(request)
        last_user, last_assistant = self._last_user_and_assistant(request.history)
        if not last_assistant:
            return ChatResponse(
                assistant_text="",
                assistant_html=message_to_html("No assistant output available to continue.", "assistant-error"),
                token_report="No previous assistant output available.",
                saved_file=None,
            )

        base_text = extract_source_only(last_assistant).rstrip()
        tail = base_text[-CONTINUE_TAIL_CHARS:]
        continue_prompt = (
            "Continue the previous code output exactly where it stopped.\n"
            "Return exactly one final source output.\n"
            "Return the marker FINAL_ANSWER_SOURCE on its own line, then the final source code.\n"
            "Do not include Markdown fences, <think> tags, explanations, or repeated earlier lines.\n\n"
            f"Original user request:\n{last_user or '[unknown]'}\n\n"
            f"Last output tail:\n{tail}"
        )
        raw_answer = await client.complete(
            system_prompt=(
                "You are a coding assistant. Return FINAL_ANSWER_SOURCE on its own line, then source code only. "
                "Do not include Markdown, HTML, <think> tags, or explanations."
            ),
            user_prompt=continue_prompt,
            model_name=model,
            temperature=min(float(temperature), 0.2),
            max_tokens=max(512, max_tokens),
        )
        final_content = base_text + "\n" + extract_source_only(raw_answer).lstrip()
        saved_file = save_generated_txt(
            content=final_content,
            user_message=last_user or "continued_program",
            generated_dir=self.settings.generated_dir,
            prefix="continued_source",
        )
        report = (
            f"backend: OpenAI-compatible model server\nbase_url: {provider.base_url}\nmodel: {model}\n"
            "[Continuation mode]\nFinal answer saved."
        )
        if saved_file:
            report += f"\nSaved generated TXT: {saved_file}\nTXT format: UTF-8, tabs preserved, CRLF line endings."
        return ChatResponse(
            assistant_text=final_content,
            assistant_html=source_to_html(final_content),
            token_report=report,
            saved_file=saved_file,
        )

    @staticmethod
    def _last_user_and_assistant(history: list[ChatMessage]) -> tuple[str | None, str | None]:
        last_user = None
        last_assistant = None
        for message in reversed(history):
            if last_assistant is None and message.role == "assistant" and message.content.strip():
                last_assistant = message.content
            elif last_user is None and message.role == "user" and message.content.strip():
                last_user = message.content
            if last_user and last_assistant:
                break
        return last_user, last_assistant

    @staticmethod
    def _sse(event: str, payload: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
