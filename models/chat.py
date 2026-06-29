from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class ChatRequest(BaseModel):
    session_id: str
    message: str

class Chip(BaseModel):
    label: str
    value: str

class ChatResponse(BaseModel):
    reply: str
    chips: Optional[List[Chip]] = None
    details: Optional[Dict[str, Any]] = None
    show_form_choice: Optional[bool] = None
    open_form: Optional[bool] = None
    clear_session: Optional[bool] = None
    intent: Optional[str] = None

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
    land_size: Optional[str] = "0"
    email: Optional[str] = ""
    email_reminders: Optional[bool] = True
    aadhaar: Optional[str] = ""
