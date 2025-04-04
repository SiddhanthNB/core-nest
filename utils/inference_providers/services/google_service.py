import json
import asyncio
from fastapi import HTTPException
import utils.constants as constants
import google.generativeai as genai
from utils.inference_providers.services.base_service import BaseService

class GoogleService(BaseService):
    
    def __init__(self):
        super().__init__()
        self.model_name = constants.SERVICES['google']['model']
        genai.configure(api_key=constants.SERVICES['google']['key'])

    async def get_response(self, params):
        model = genai.GenerativeModel(model_name=self.model_name, system_instruction=params.system_prompt)
        response = await asyncio.to_thread(model.generate_content, params.user_prompt)
        response = response.text
        return self.response_parser(response) if params.structured_output else response
    
    def response_parser(self, response):
        text = response.strip()
        if text.startswith("```json") and text.endswith("```"):
            json_str = text[len("```json"): -len("```")].strip()
            return json.loads(json_str)
        else:
            raise HTTPException(status_code=500, detail="Response is not in expected JSON format")
