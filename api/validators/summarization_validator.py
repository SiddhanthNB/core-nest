from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator

class SummarizationValidator(BaseModel):
    corpus: str = Field(..., description="Text corpus to be summarized")

    @field_validator("corpus")
    @classmethod
    def validate_corpus(cls, v):
        if not v or not v.strip():
            raise HTTPException(status_code=400, detail="'corpus' cannot be empty or blank") 
        return v
