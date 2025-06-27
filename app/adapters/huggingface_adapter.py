import httpx
import app.utils.constants as constants
from .base_adapter import BaseAdapter

class HuggingfaceAdapter(BaseAdapter):

    def __init__(self):
        super().__init__()
        self._api_key = constants.SERVICES["openai"]["key"]
        self._url = constants.SERVICES["openai"]["url"]
        self.model_name = constants.SERVICES["openai"]["model"]

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
            response = await client.post(self._url, headers=headers, json=payload)
            response.raise_for_status()
            response = response.json()
            response = response["choices"][0]["message"]

        return response
