from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class ChatRequest(BaseModel):
    query: str
    context: dict = {}

class CompletionRequest(BaseModel):
    prompt: str

@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    return {"result": f"Test chat response for: {request.query}"}

@router.post("/completion")
async def completion_endpoint(request: CompletionRequest):
    return {"text": " # test autocomplete"}