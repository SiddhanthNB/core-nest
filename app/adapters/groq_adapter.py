import httpx
from app.utils import constants
from .base_adapter import BaseAdapter

class GroqAdapter(BaseAdapter):

    def __init__(self):
        super().__init__()
        self._api_key = constants.SERVICES["groq"]["key"]
        self._generation_url = constants.SERVICES["groq"]["generation"]["url"]
        self.generation_model = constants.SERVICES["groq"]["generation"]["model"]

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
            response = response.json()
            response = response["choices"][0]["message"]["content"]

        return self.response_parser(response) if params.structured_output else response
