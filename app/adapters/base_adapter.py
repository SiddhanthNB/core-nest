import json
from fastapi import HTTPException, status

class BaseAdapter:

    def __init__(self):
        pass

    def response_parser(self, response):
        if response.startswith('{') and response.endswith('}'):
            return json.loads(response)
        elif '```json' in response and '```' in response:
            return self._extract_json_block(response)
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No JSON block found in response")

    def _extract_json_block(self, text):
        text = text.strip()
        start_marker = "```json"
        end_marker = "```"

        start_idx = text.index(start_marker) + len(start_marker)
        end_idx = text.index(end_marker, start_idx)
        json_str = text[start_idx:end_idx].strip()

        return json.loads(json_str)
