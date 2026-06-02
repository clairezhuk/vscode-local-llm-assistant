import time
from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel
from src.agentic_orchestrator.orchestrator import Orchestrator
from fastapi.responses import StreamingResponse

router = APIRouter()
orchestrator = Orchestrator()

class ChatRequest(BaseModel):
    query: str
    context: dict = {}

class CompletionRequest(BaseModel):
    prompt: str

class ConfirmRequest(BaseModel):
    action: str

# @router.post("/chat")
# async def chat_endpoint(request: ChatRequest):
#     start_time = time.time()
#     print(f"\n[{datetime.now().strftime('%H:%M:%S')}] START /chat")
    
#     response = orchestrator.process_chat(request.query, request.context)
    
#     elapsed = time.time() - start_time
#     usage = response.get("usage", {})
#     print(f"[{datetime.now().strftime('%H:%M:%S')}] END /chat | Time: {elapsed:.2f}s | Tokens: {usage}")
    
#     return {
#         "result": response.get("result", ""),
#         "usage": usage,
#         "intent": response.get("intent", 0)
#     }


@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    return StreamingResponse(
        orchestrator.process_chat(request.query, request.context),
        media_type="application/x-ndjson"
    )

@router.post("/command-confirm")
async def confirm_endpoint(request: ConfirmRequest):
    if request.action == "accept":
        result = orchestrator.execute_confirmed()
    else:
        result = orchestrator.reject_command()
    return {"result": result}

@router.post("/completion")
async def completion_endpoint(request: CompletionRequest):
    start_time = time.time()
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] START /completion")
    
    response = orchestrator.process_completion(request.prompt)
    
    elapsed = time.time() - start_time
    print(f"[{datetime.now().strftime('%H:%M:%S')}] END /completion | Time: {elapsed:.2f}s | Tokens: {response['usage']}")
    
    return {"text": response["text"]}