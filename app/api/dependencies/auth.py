import json
from fastapi import HTTPException, Header
import app.utils.constants as constants


def validate_auth_token(auth: str = Header(...)) -> dict:
    """
    FastAPI dependency to validate authentication token from header.

    Args:
        auth: JSON string containing client credentials

    Returns:
        dict: Parsed authentication data

    Raises:
        HTTPException: If authentication fails
    """
    valid_apps = ['ai-content-rag', 'ai-project-recommender']

    try:
        auth = json.loads(auth)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail='Invalid header structure')

    if (not auth) or ('client-name' not in auth) or ('client-id' not in auth) or ('client-secret' not in auth):
        raise HTTPException(status_code=400, detail='Mandatory header missing')

    if auth['client-name'] not in valid_apps:
        raise HTTPException(status_code=401, detail='Who are you?')

    if (auth['client-id'] != constants.CLIENT_ID) or (auth['client-secret'] != constants.CLIENT_SECRET):
        raise HTTPException(status_code=401, detail='Authentication failed')

    return auth
