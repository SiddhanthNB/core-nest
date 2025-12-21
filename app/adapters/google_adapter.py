import httpx
from app.utils import constants
from .base_adapter import BaseAdapter

class GoogleAdapter(BaseAdapter):

    def __init__(self):
        super().__init__()
        base_url = constants.SERVICES['google']['base_url']
        self.api_key = constants.SERVICES['google']['key']
        self.embedding_model = constants.SERVICES['google']['embedding']['model']
        self.generation_model = constants.SERVICES['google']['generation']['model']
        self._generation_url = f"{base_url}{self.generation_model}{constants.SERVICES['google']['generation']['verb']}"
        self._embedding_url = f"{base_url}{self.embedding_model}{constants.SERVICES['google']['embedding']['verb']}"

    def _build_headers(self):
        return {"Content-Type": "application/json", "x-goog-api-key": self.api_key}

    async def generate_response(self, params):
        payload = {
            "contents": [
                {
                    "parts": [ { "text": params.user_prompt } ]
                }
            ]
        }
        if params.system_prompt:
            payload["system_instruction"] = {
                "parts": [
                    {
                        "text": params.system_prompt
                    }
                ]
            }
        async with httpx.AsyncClient() as client:
            response = await self._request_with_retries(
                client,
                "POST",
                self._generation_url,
                headers=self._build_headers(),
                json=payload
            )
            data = response.json()
            response_text = data["candidates"][0]["content"]["parts"][0]["text"]

        return self.response_parser(response_text) if params.structured_output else response_text

    async def generate_embeddings(self, texts):
        requests = []
        for text in texts:
            requests.append({
                "model": f"models/{self.embedding_model}",
                "content": {
                    "parts": [{"text": text}]
                }
            })
        payload = { "requests": requests }
        async with httpx.AsyncClient() as client:
            response = await self._request_with_retries(
                client,
                "POST",
                self._embedding_url,
                headers=self._build_headers(),
                json=payload
            )
            data = response.json()

        return [ result["values"] for result in data["embeddings"] ]
