from typing import Optional
from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator

class CompletionSchema(BaseModel):
    user_prompt: str = Field(..., description="User input prompt")
    system_prompt: Optional[str] = Field(default="You are a helpful assistant", description="System prompt for the assistant")
    structured_output: Optional[bool] = Field(default=False, description="Whether the output should be structured")

    @field_validator("user_prompt")
    @classmethod
    def validate_user_prompt(cls, v):
        if not v or not v.strip():
            raise HTTPException(status_code=400, detail="'user_prompt' cannot be empty")
        return v
