import httpx
from app.utils import constants
from .base_adapter import BaseAdapter

class MistralAdapter(BaseAdapter):

    def __init__(self):
        super().__init__()
        self._api_key = constants.SERVICES["mistral"]["key"]
        self._generation_url = constants.SERVICES["mistral"]["generation"]["url"]
        self._embedding_url = constants.SERVICES["mistral"]["embedding"]["url"]
        self.generation_model = constants.SERVICES["mistral"]["generation"]["model"]
        self.embedding_model = constants.SERVICES["mistral"]["embedding"]["model"]

    async def generate_response(self, params):
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}"
        }
        payload = {
            "model": self.generation_model,
            "messages": [
                {"role": "system", "content": params.system_prompt},
                {"role": "user", "content": params.user_prompt}
            ]
        }
        async with httpx.AsyncClient() as client:
            response = await self._request_with_retries(
                client,
                "POST",
                self._generation_url,
                headers=headers,
                json=payload,
            )
            data = response.json()
            response = data["choices"][0]["message"]["content"]

        return self.response_parser(response) if params.structured_output else response

    async def generate_embeddings(self, texts):
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}"
        }
        payload = {
            "model": self.embedding_model,
            "input": texts,
        }
        async with httpx.AsyncClient() as client:
            response = await self._request_with_retries(
                client,
                "POST",
                self._embedding_url,
                headers=headers,
                json=payload,
            )
            data = response.json()

        return [ item["embedding"] for item in data["data"] ]
