from typing import Optional
from fastapi import HTTPException, status
from pydantic import BaseModel, Field, field_validator

class CompletionSchema(BaseModel):
    user_prompt: str = Field(..., description="User input prompt")
    system_prompt: Optional[str] = Field(default="You are a helpful assistant", description="System prompt for the assistant")
    structured_output: Optional[bool] = Field(default=False, description="Whether the output should be structured")
    provider: Optional[str] = Field(None, description="The provider to use for completion")

    @field_validator("user_prompt")
    @classmethod
    def validate_user_prompt(cls, v):
        if not v or not v.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'user_prompt' cannot be empty")
        return v

    @field_validator('provider')
    @classmethod
    def validate_provider(cls, v):
        valid_providers = ['google', 'openai', 'openrouter', 'groq', 'minstral']
        if v and v not in valid_providers:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Provider '{v}' is not supported. Supported providers are: {valid_providers}")
        return v
