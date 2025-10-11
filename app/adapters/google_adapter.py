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

    async def generate_response(self, params):
        headers = { "Content-Type": "application/json" }
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
            response = await client.post(self._generation_url, headers=headers, json=payload, params={"key": self.api_key})
            response.raise_for_status()
            data = response.json()
            response_text = data["candidates"][0]["content"]["parts"][0]["text"]

        return self.response_parser(response_text) if params.structured_output else response_text

    async def generate_embeddings(self, texts):
        headers = { "Content-Type": "application/json" }
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
            response = await client.post(self._embedding_url, headers=headers, json=payload, params={"key": self.api_key})
            response.raise_for_status()
            data = response.json()

        return [ result["values"] for result in data["embeddings"] ]
