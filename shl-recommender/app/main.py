"""
main.py
-------
FastAPI service exposing:
  GET  /health  → {"status": "ok"}
  POST /chat    → agent reply + recommendations

Run locally:
    uvicorn app.main:app --reload --port 8000

Then test with:
    curl http://localhost:8000/health
    curl -X POST http://localhost:8000/chat \
         -H "Content-Type: application/json" \
         -d '{"messages": [{"role": "user", "content": "I need to hire a Java developer"}]}'
"""

import os
import threading
from contextlib import asynccontextmanager
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

# Load .env file (works locally; on Render use dashboard env vars)
load_dotenv()

# ── startup: pre-load model & index ──────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs at startup. Kicks off index initialisation in a background thread
    so the port opens IMMEDIATELY — critical for Render's port scanner.
    The first /chat request will wait if init hasn't finished yet.
    """
    def _bg_init():
        try:
            from app.retrieval import initialise
            initialise()
            print("[startup] Ready.")
        except Exception as e:
            print(f"[startup] WARNING: Could not initialise retrieval: {e}")

    print("[startup] Starting background initialisation…")
    t = threading.Thread(target=_bg_init, daemon=True)
    t.start()
    yield   # server starts and port opens immediately
    print("[shutdown] Bye.")


# ── app ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "SHL Assessment Recommender",
    description = "Conversational agent for recommending SHL Individual Test Solutions.",
    version     = "1.0.0",
    lifespan    = lifespan,
)

# Allow all origins (needed for the evaluator to call your deployed endpoint)
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


# ── request / response models ─────────────────────────────────────────────────

class Message(BaseModel):
    role:    Literal["user", "assistant"]
    content: str

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Message content cannot be empty.")
        return v.strip()


class ChatRequest(BaseModel):
    messages: list[Message] = Field(
        ...,
        min_length = 1,
        description = "Full conversation history, alternating user/assistant turns.",
    )

    @field_validator("messages")
    @classmethod
    def must_have_user_message(cls, v: list[Message]) -> list[Message]:
        if not any(m.role == "user" for m in v):
            raise ValueError("At least one user message is required.")
        return v


class Recommendation(BaseModel):
    name:      str
    url:       str
    test_type: str


class ChatResponse(BaseModel):
    reply:               str
    recommendations:     list[Recommendation] = []
    end_of_conversation: bool = False


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Readiness check. Returns HTTP 200 when the service is up."""
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """
    Stateless chat endpoint.

    Accepts the full conversation history and returns the next agent turn
    plus, when appropriate, a structured shortlist of SHL recommendations.
    """
    from app.agent import chat as agent_chat

    # Convert Pydantic models to plain dicts for the agent
    messages_dicts = [
        {"role": m.role, "content": m.content}
        for m in request.messages
    ]

    try:
        result = agent_chat(messages_dicts)
    except Exception as e:
        # Never crash the server — return a graceful error reply
        raise HTTPException(
            status_code = 500,
            detail      = f"Agent error: {str(e)[:200]}",
        )

    return ChatResponse(
        reply               = result.get("reply", ""),
        recommendations     = [
            Recommendation(**rec)
            for rec in result.get("recommendations", [])
        ],
        end_of_conversation = result.get("end_of_conversation", False),
    )


# ── local dev entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host    = "0.0.0.0",
        port    = int(os.environ.get("PORT", 8000)),
        reload  = False,   # set True for local dev if you like
    )
