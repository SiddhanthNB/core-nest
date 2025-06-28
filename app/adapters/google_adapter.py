import json
import httpx
from fastapi import HTTPException
import app.utils.constants as constants
from .base_adapter import BaseAdapter

class GoogleAdapter(BaseAdapter):

    def __init__(self):
        super().__init__()
        self.api_key = constants.SERVICES['google']['key']
        self.base_url = constants.SERVICES['google']['base_url']
        self.generation_model = constants.SERVICES['google']['generation']['model']
        self.embedding_model = constants.SERVICES['google']['embedding']['model']

    async def generate_response(self, params):
        url = f"{self.base_url}{self.generation_model}{constants.SERVICES['google']['generation']['verb']}"
        headers = {
            "Content-Type": "application/json"
        }
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
            response = await client.post(
                url,
                headers=headers,
                json=payload,
                params={"key": self.api_key}
            )
            response.raise_for_status()
            data = response.json()
            response_text = data["candidates"][0]["content"]["parts"][0]["text"]

        return self.response_parser(response_text) if params.structured_output else response_text

    async def generate_embeddings(self, texts):
        url = f"{self.base_url}{self.generation_model}{constants.SERVICES['google']['embedding']['verb']}"
        headers = {
            "Content-Type": "application/json"
        }
        requests = []
        for text in texts:
            requests.append({
                "model": f"models/{self.embedding_model}",
                "content": {
                    "parts": [{"text": text}]
                }
            })
        payload = {
            "requests": requests
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=headers,
                json=payload,
                params={"key": self.api_key}
            )
            response.raise_for_status()
            data = response.json()

            embeddings = [ result["embedding"]["values"] for result in data.get("embedding_batch_results", []) ]

        return embeddings

    # def _response_parser(self, response):
    #     text = response.strip()
    #     if text.startswith("```json") and text.endswith("```"):
    #         json_str = text[len("```json"): -len("```")].strip()
    #         return json.loads(json_str)
    #     else:
    #         raise HTTPException(status_code=500, detail="Response is not in expected JSON format")
