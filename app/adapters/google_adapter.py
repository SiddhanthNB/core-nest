import json
import asyncio
from fastapi import HTTPException
from app.utils import constants
import google.generativeai as genai
from .base_adapter import BaseAdapter

class GoogleAdapter(BaseAdapter):

    def __init__(self):
        super().__init__()
        self.model_name = constants.SERVICES['google']['model']
        genai.configure(api_key=constants.SERVICES['google']['key'])

    async def generate_response(self, params):
        model = genai.GenerativeModel(model_name=self.model_name, system_instruction=params.system_prompt)
        response = await asyncio.to_thread(model.generate_content, params.user_prompt)
        response = response.text
        return self._response_parser(response) if params.structured_output else response

    async def generate_embeddings(self, params):
        pass

    def _response_parser(self, response):
        text = response.strip()
        if text.startswith("```json") and text.endswith("```"):
            json_str = text[len("```json"): -len("```")].strip()
            return json.loads(json_str)
        else:
            raise HTTPException(status_code=500, detail="Response is not in expected JSON format")
