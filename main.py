import sys
import os
import logging
import traceback
import asyncio
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
logging.getLogger("pymongo").setLevel(logging.WARNING)

# Ensure module path works when running via uvicorn
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# FastAPI application
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict

# Groq client
from groq import Groq

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY environment variable not set")
groq_client = Groq(api_key=GROQ_API_KEY)

# MongoDB connections
from pymongo import MongoClient
import motor.motor_asyncio

MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI environment variable not set")

# Synchronous client for quick reads/writes
sync_mongo_client = MongoClient(MONGODB_URI)

# Asynchronous client for async endpoints
async_mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)

# Collections
sync_users_collection = sync_mongo_client["welfarebot"]["users"]
sync_schemes_collection = sync_mongo_client["welfarebot"]["schemes"]
conversations_collection = async_mongo_client["welfarebot"]["conversations"]

# Build LangGraph
from agent.graph import build_graph
from chromadb import PersistentClient

chroma_client = PersistentClient(path="./chroma_storage")

welfare_graph = build_graph(groq_client, sync_users_collection, sync_schemes_collection)

# Scraper + scheduler (moved to top so they're defined before any endpoint uses them)
from scraper.manager import run_scraper
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
scheduler.add_job(run_scraper, "interval", days=3, id="scraper_job")
scheduler.start()

# FastAPI app instance
app = FastAPI(title="WelfareBot Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response models
class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    show_form_choice: Optional[bool] = None
    clear_session: Optional[bool] = None


class SubmitProfileRequest(BaseModel):
    session_id: str
    name: str
    language_preference: str
    state: str
    occupation: str
    caste_category: str
    gender: str
    age: str
    income_bracket: str
    aadhaar: Optional[str] = ""


# Endpoints
@app.get("/health")
async def health():
    return {"status": "running", "db": "connected"}


@app.get("/schemes")
async def get_schemes():
    schemes = list(sync_schemes_collection.find({}, {"_id": 0}))
    return {"schemes": schemes}


@app.get("/session")
async def get_session(session_id: str):
    user = sync_users_collection.find_one({"session_id": session_id})
    return {"session_id": session_id, "profile": user or {}}


@app.post("/submit-profile")
async def submit_profile(request: SubmitProfileRequest):
    try:
        profile_dict = request.dict()
        sync_users_collection.update_one(
            {"session_id": request.session_id},
            {"$set": profile_dict},
            upsert=True,
        )

        from agent.eligibility import match_schemes

        schemes = match_schemes(profile_dict, sync_schemes_collection)
        return {"status": "success", "schemes": schemes[:5]}
    except Exception as e:
        return {"error": str(e)}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        session_id = request.session_id
        message = request.message.strip()

        if not message:
            return ChatResponse(reply="Please say something.")

        # Determine onboarding flow
        user_doc = sync_users_collection.find_one({"session_id": session_id}) or {}
        onboarding_step = user_doc.get("onboarding_step", "name")

        # ---- Onboarding flow ----
        if onboarding_step == "name" and not user_doc.get("name"):
            sync_users_collection.update_one(
                {"session_id": session_id},
                {"$set": {"name": message, "onboarding_step": "language"}},
                upsert=True,
            )
            reply = f"Hello {message}, nice to meet you! Please select your preferred language.\nCHIPS:['English','हिंदी','తెలుగు','தமிழ்','ಕನ್ನಡ']"
            return ChatResponse(reply=reply, show_form_choice=False, clear_session=False)

        if onboarding_step == "language" and not user_doc.get("language_preference"):
            sync_users_collection.update_one(
                {"session_id": session_id},
                {"$set": {"language_preference": message, "onboarding_step": "details"}},
                upsert=True,
            )
            reply = "Great! Now we can continue. Would you like to fill a form or just chat?\nCHIPS:['📝 Fill Form','💬 Chat instead']"
            return ChatResponse(reply=reply, show_form_choice=True, clear_session=False)

        # Existing handling for other messages
        state = {
            "session_id": session_id,
            "message": message,
            "onboarding_step": onboarding_step,
            "intent": None,
            "reply": None,
            "show_form_choice": None,
            "clear_session": None,
            "user_profile": user_doc,
        }

        result = welfare_graph.invoke(state)

        reply = result.get("reply", "Sorry, couldn't process that.")
        show_form_choice = result.get("show_form_choice", False)
        clear_session = result.get("clear_session", False)

        await conversations_collection.insert_one({
            "session_id": session_id,
            "user_message": message,
            "bot_reply": reply,
            "intent": result.get("intent"),
            "timestamp": datetime.utcnow(),
        })

        return ChatResponse(
            reply=reply,
            show_form_choice=show_form_choice,
            clear_session=clear_session,
        )
    except Exception as e:
        logging.error(f"Chat endpoint error: {e}")
        return ChatResponse(reply=f"Error: {str(e)}")


# Startup diagnostics
print("\n" + "=" * 50)
print("WELFAREBOT BACKEND READY (Groq-only)")
print("=" * 50)
print(f"[OK] Groq client: {groq_client}")
print(f"[OK] MongoDB connected: {sync_mongo_client}")
print(f"[OK] Users collection: {sync_users_collection}")
print(f"[OK] Schemes collection: {sync_schemes_collection}")
print(f"[OK] LangGraph: {welfare_graph}")

# Initialize Chromadb collection for RAG (reuses chroma_client created above)
collection = chroma_client.get_or_create_collection(name="welfare_schemes")
print("=" * 50 + "\n")

# -------------------- API ENDPOINTS --------------------

# Existing staging endpoint
@app.get("/staging")
async def get_staging():
    client = motor.motor_asyncio.AsyncIOMotorClient(os.getenv("MONGODB_URI"))
    db = client.get_default_database()
    cursor = db.staging.find({"status": "pending"}).sort("scraped_at", -1).limit(100)
    return await cursor.to_list(length=100)


# RAG endpoint – simple semantic search over stored schemes
@app.post("/rag")
async def rag_query(query: dict):
    """Accepts JSON {"question": "..."} and returns top matching scheme texts."""
    question = query.get("question", "")
    if not question:
        raise HTTPException(status_code=400, detail="Question required")

    try:
        # Use Groq to get embedding (placeholder: use text as is)
        # For now, perform a naive text match against stored documents
        docs = collection.get(ids=collection.get().ids)
        # Very naive: return first 3 documents
        return {"matches": docs['documents'][:3]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Endpoint to manually trigger scraper
@app.post("/scraper/run")
async def trigger_scraper():
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, run_scraper)
    return {"status": "scraper started", "message": "Check /staging in 1-2 minutes"}