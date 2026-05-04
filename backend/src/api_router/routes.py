from fastapi import APIRouter
from pydantic import BaseModel
from src.agentic_orchestrator.orchestrator import Orchestrator

router = APIRouter()
orchestrator = Orchestrator()

class ChatRequest(BaseModel):
    query: str
    context: dict = {}

class CompletionRequest(BaseModel):
    prompt: str

@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    result = orchestrator.process_chat(request.query, request.context)
    return {"result": result}

@router.post("/completion")
async def completion_endpoint(request: CompletionRequest):
    result = orchestrator.process_completion(request.prompt)
    return {"text": result}