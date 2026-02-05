# routes/chat.py - RAG-Powered AI Chatbot with BidWise Knowledge Base (OpenAI)

import logging
from typing import Optional, List, Dict
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from openai import OpenAI

from config import get_settings
from services.vector_search import get_job_matcher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["Chat"])


# -------------------------------------------------------------------
# Request / Response Models
# -------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    message: str
    conversation_id: str
    sources: Optional[List[Dict]] = None


# -------------------------------------------------------------------
# In-memory conversation store (Redis in production)
# -------------------------------------------------------------------

conversations: Dict[str, List[Dict]] = {}


# -------------------------------------------------------------------
# Load BidWise knowledge base
# -------------------------------------------------------------------

KNOWLEDGE_BASE = ""
knowledge_file = Path(__file__).parent.parent / "knowledge_base" / "bidwise_docs.md"

if knowledge_file.exists():
    KNOWLEDGE_BASE = knowledge_file.read_text()
    logger.info(f"Loaded knowledge base ({len(KNOWLEDGE_BASE)} chars)")
else:
    logger.warning(f"Knowledge base not found at {knowledge_file}")


# -------------------------------------------------------------------
# OpenAI Client
# -------------------------------------------------------------------

def get_openai_client() -> OpenAI:
    settings = get_settings()
    logger.info(f"OpenAI key loaded: {bool(settings.OPENAI_API_KEY)}")

    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not configured"
        )

    return OpenAI(api_key=settings.OPENAI_API_KEY)


# -------------------------------------------------------------------
# Vector Search (Freelancer RAG)
# -------------------------------------------------------------------

def search_freelancer_context(query: str, top_k: int = 5) -> List[Dict]:
    try:
        matcher = get_job_matcher()
        collection = matcher.vectorstore._collection

        if collection.count() == 0:
            return []

        results = matcher.vectorstore.similarity_search_with_score(
            query=query,
            k=min(top_k, collection.count())
        )

        context = []
        for doc, score in results:
            context.append({
                "user_id": doc.metadata.get("user_id"),
                "username": doc.metadata.get("username"),
                "title": doc.metadata.get("title"),
                "skills": doc.metadata.get("skills", "").split(",") if doc.metadata.get("skills") else [],
                "experience_level": doc.metadata.get("experience_level"),
                "content": doc.page_content,
                "relevance": round(1 - score, 3)
            })

        return context

    except Exception as e:
        logger.error(f"Vector search failed: {e}", exc_info=True)
        return []


# -------------------------------------------------------------------
# Prompt Builder
# -------------------------------------------------------------------

def build_system_prompt(user_query: str, freelancer_context: List[Dict]) -> str:
    prompt = f"""
You are BidWise AI Assistant, a helpful chatbot for the BidWise freelancing platform.

=== BIDWISE KNOWLEDGE BASE ===
{KNOWLEDGE_BASE}
"""

    if freelancer_context:
        prompt += "\n=== AVAILABLE FREELANCERS ===\n"
        for i, f in enumerate(freelancer_context[:3], 1):  # limit to reduce token cost
            skills = ", ".join(f["skills"]) if f["skills"] else "Not specified"
            prompt += f"""
Freelancer {i}:
- Username: {f["username"]}
- Title: {f["title"]}
- Skills: {skills}
- Experience: {f["experience_level"]}
- Match Score: {f["relevance"]:.0%}
"""

    prompt += """
=== INSTRUCTIONS ===
- Answer questions about BidWise
- Help with navigation and usage
- Recommend freelancers only from the provided list
- Be concise and clear
- Do not hallucinate features

User question:
"""

    return prompt + user_query


# -------------------------------------------------------------------
# Chat Endpoint
# -------------------------------------------------------------------

@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    authorization: Optional[str] = Header(None)
):
    try:
        conversation_id = (
            request.conversation_id
            or f"conv_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
        )

        if conversation_id not in conversations:
            conversations[conversation_id] = []

        history = conversations[conversation_id]

        freelancer_context = []
        keywords = ["find", "hire", "developer", "freelancer", "designer", "expert"]

        if any(k in request.message.lower() for k in keywords):
            freelancer_context = search_freelancer_context(request.message)
            if freelancer_context:
                logger.info(f"RAG context: {len(freelancer_context)} freelancers")

        system_prompt = build_system_prompt(request.message, freelancer_context)

        client = get_openai_client()

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": request.message},
                ],
                temperature=0.3,
            )

            assistant_message = response.choices[0].message.content.strip()
            logger.info("OpenAI response generated successfully")

        except Exception as openai_error:
            logger.error(f"OpenAI API error: {openai_error}", exc_info=True)
            raise HTTPException(
                status_code=503,
                detail="AI service temporarily unavailable"
            )

        history.append({"role": "user", "content": request.message})
        history.append({"role": "assistant", "content": assistant_message})

        if len(history) > 20:
            conversations[conversation_id] = history[-20:]

        sources = None
        if freelancer_context:
            sources = [
                {"username": f["username"], "relevance": f"{f['relevance']:.0%}"}
                for f in freelancer_context[:3]
            ]

        return ChatResponse(
            message=assistant_message,
            conversation_id=conversation_id,
            sources=sources
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Chat failed")
        raise HTTPException(
            status_code=500,
            detail={"error": "Chat failed", "message": str(e)}
        )


# -------------------------------------------------------------------
# Utilities
# -------------------------------------------------------------------

@router.delete("/{conversation_id}")
async def clear_conversation(conversation_id: str):
    if conversation_id in conversations:
        del conversations[conversation_id]
        return {"status": "cleared", "conversation_id": conversation_id}
    raise HTTPException(status_code=404, detail="Conversation not found")


@router.get("/health")
async def chat_health():
    matcher = get_job_matcher()
    return {
        "status": "healthy",
        "openai_configured": True,
        "knowledge_base_loaded": bool(KNOWLEDGE_BASE),
        "knowledge_base_size": len(KNOWLEDGE_BASE),
        "indexed_freelancers": matcher.get_collection_stats()["total_indexed"],
        "active_conversations": len(conversations)
    }
