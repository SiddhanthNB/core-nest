"""
curl -X POST "https://api.mistral.ai/v1/embeddings" \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer ${MINSTRAL_API_KEY}" \
     -d '{"model": "mistral-embed", "input": ["Embed this sentence.", "As well as this one."]}'
"""

"""
curl --location "https://api.mistral.ai/v1/chat/completions" \
     --header 'Content-Type: application/json' \
     --header 'Accept: application/json' \
     --header "Authorization: Bearer ${MINSTRAL_API_KEY}" \
     --data '{
    "model": "ministral-8b-2410",
    "messages": [
     {
        "role": "user",
        "content": "What is the best French cheese?"
      }
    ]
  }'
"""

import httpx
from app.utils import constants
from .base_adapter import BaseAdapter

class MinstralAdapter(BaseAdapter):

    def __init__(self):
        super().__init__()
        self._api_key = constants.SERVICES["minstral"]["key"]
        self.generation_model = constants.SERVICES["minstral"]["generation"]["model"]
        self.generation_url = constants.SERVICES["minstral"]["generation"]["url"]
        self.embedding_model = constants.SERVICES["minstral"]["embedding"]["model"]
        self.embedding_url = constants.SERVICES["minstral"]["embedding"]["url"]

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
            response = await client.post(self.generation_url, headers=headers, json=payload)
            response.raise_for_status()
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
            response = await client.post(self.embedding_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        return [ item["embedding"] for item in data["data"] ]
