import httpx
import utils.constants as constants
from utils.inference_providers.services.base_service import BaseService

class OpenRouterService(BaseService):

    def __init__(self):
        super().__init__()
        self._api_key = constants.SERVICES["openrouter"]["key"]
        self._url = constants.SERVICES["openrouter"]["url"]
        self.model_name = constants.SERVICES["openrouter"]["model"]

    async def get_response(self, params):
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
            response = response["choices"][0]["message"]["content"]
            return self.response_parser(response) if params.structured_output else response
