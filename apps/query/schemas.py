from pydantic import BaseModel

class QueryRequest(BaseModel):
    query: str

class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int

class QueryResponse(BaseModel):
    answer: str
    token_usage: TokenUsage