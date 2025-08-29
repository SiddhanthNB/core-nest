import json
from fastapi import HTTPException, status

class BaseAdapter:

    def __init__(self):
        pass

    def response_parser(self, response):
        text = response.strip()
        start_marker = "```json"
        end_marker = "```"

        if start_marker not in text:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No JSON block found in response")

        if end_marker not in text:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No JSON block found in response")

        start_idx = text.index(start_marker) + len(start_marker)
        end_idx = text.index(end_marker, start_idx)
        json_str = text[start_idx:end_idx].strip()

        return json.loads(json_str)
