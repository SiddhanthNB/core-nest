import httpx
import app.utils.constants as constants
from .base_adapter import BaseAdapter

class OpenAIAdapter(BaseAdapter):

    def __init__(self):
        super().__init__()
        self._api_key = constants.SERVICES["openai"]["key"]
        self.model_name = constants.SERVICES["openai"]["generation"]["model"]
        self.generation_url = constants.SERVICES["openai"]["generation"]["url"]
        self.embedding_model = constants.SERVICES["openai"]["embedding"]["model"]
        self.embedding_url = constants.SERVICES["openai"]["embedding"]["url"]

    async def generate_response(self, params):
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}"
        }
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": params.system_prompt},
                {"role": "user", "content": params.user_prompt}
            ]
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(self.generation_url, headers=headers, json=payload)
            response.raise_for_status()
            response = response.json()
            response = response["choices"][0]["message"]["content"]

        return self.response_parser(response) if params.structured_output else response

    async def generate_embeddings(self, texts):
        """Generate embeddings using OpenAI's text-embedding-3-small model"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}"
        }
        payload = {
            "model": self.embedding_model,
            "input": texts,
            "encoding_format": "float"
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.embedding_url,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()

        return [item["embedding"] for item in data["data"]]
