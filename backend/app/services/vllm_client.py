from collections.abc import AsyncIterator

from openai import AsyncOpenAI


class VllmClient:
    def __init__(self, base_url: str, api_key: str, timeout_seconds: float) -> None:
        self.base_url = base_url
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout_seconds,
        )

    async def list_models(self) -> list[str]:
        models = await self.client.models.list()
        return [getattr(model, "id", "") for model in getattr(models, "data", []) if getattr(model, "id", "")]

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model_name: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        response = await self.client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=float(temperature),
            max_tokens=int(max_tokens),
            stream=False,
        )
        return response.choices[0].message.content or ""

    async def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        model_name: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        stream = await self.client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=float(temperature),
            max_tokens=int(max_tokens),
            stream=True,
        )

        async for chunk in stream:
            delta = None
            try:
                delta = chunk.choices[0].delta.content
            except Exception:
                delta = None
            if delta:
                yield delta

