import json
from fastapi import HTTPException
import utils.constants as constants

class ApiController:

    def __init__(self):
        self.valid_apps = ['ai-content-rag', 'ai-project-recommender']

    def auth_token_validator(self, auth):
        try:
            auth = json.loads(auth)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail='Invalid header structure')

        if not auth:
            raise HTTPException(status_code=400, detail='Mandatory header missing')
        
        if auth['client-name'] not in self.valid_apps:
            raise HTTPException(status_code=401, detail='Who are you?')
        
        if (auth['client-id'] != constants.CLIENT_ID) or (auth['client-secret'] != constants.CLIENT_SECRET):
            raise HTTPException(status_code=401, detail='Authentication failed')
