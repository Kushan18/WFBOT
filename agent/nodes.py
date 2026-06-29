import os
import re
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from pymongo import MongoClient
import motor.motor_asyncio
from groq import Groq
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY environment variable not set")
MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI environment variable not set")

# Initialize Groq client (will be set by main.py)
groq_client = None

# Initialize MongoDB clients (will be set by main.py)
sync_users_collection = None
sync_schemes_collection = None
conversations_collection = None

# Set up MongoDB connection if running standalone
if not groq_client:
    from pymongo import MongoClient
    import motor.motor_asyncio
    sync_mongo_client = MongoClient(MONGODB_URI)
    async_mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
    sync_users_collection = sync_mongo_client["welfarebot"]["users"]
    sync_schemes_collection = sync_mongo_client["welfarebot"]["schemes"]
    conversations_collection = async_mongo_client["welfarebot"]["conversations"]
    groq_client = Groq(api_key=GROQ_API_KEY)

# Logging
logger = logging.getLogger(__name__)

# ---------- Constants ----------
REQUIRED_FIELDS = [
    "name",
    "language_preference",
    "state",
    "occupation",
    "caste_category",
    "gender",
    "age",
    "income_bracket",
    "land_size",
]

SCHEME_KEYWORDS = [
    "scheme",
    "eligible",
    "scholarship",
    "benefit",
    "welfare",
    "apply",
    "government",
    "subsidy",
    "yojana",
    "assistance",
]

# Keywords that indicate user wants to find schemes for themselves (needs profile)
PROFILE_REQUIRED_KEYWORDS = [
    "eligible for",
    "am i eligible",
    "my schemes",
    "schemes for me",
    "what schemes",
    "find schemes",
    "match me",
]

# ---------- Helper Functions ----------
def safe_groq_chat(messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
    """Call Groq chat completion with retries and timeout.
    Returns the response text or an empty string on failure.
    """
    max_retries = 2
    for attempt in range(1, max_retries + 1):
        try:
            resp = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=temperature,
                timeout=10,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Groq chat error (attempt {attempt}): {e}")
            if attempt == max_retries:
                return ""
    return ""

def extract_first_name(text: str) -> str:
    """Extract a first name using regex patterns.
    Returns capitalized name or a fallback.
    """
    patterns = [
        r"my\s+name\s+is\s+(\w+)",
        r"i\s+am\s+(\w+)",
        r"i['']?m\s+(\w+)",
        r"call\s+me\s+(\w+)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).capitalize()
            
    # Try using Groq if text might be in Hindi/Telugu or complex
    try:
        prompt = f"""
        Extract the first name of the person from this message.
        The message might be in English, Hindi, Telugu, Tamil, or Kannada.
        Message: "{text}"
        
        Respond ONLY with the capitalized first name. Do not write anything else. If no name is found, respond with "Friend".
        """
        response = safe_groq_chat([{"role": "user", "content": prompt}], temperature=0.1)
        cleaned = response.strip().strip("'\".").capitalize()
        if cleaned and cleaned.lower() not in ["unknown", "friend"]:
            return cleaned
    except Exception as e:
        logger.warning(f"Groq name extraction failed: {e}")

    # Fallback - first word
    words = text.strip().split()
    if words:
        first_word = words[0].capitalize()
        skip_words = ["i", "hi", "hello", "hey", "the", "a", "an", "my", "am", "is", "welcome", "to", "welfarebot", "we", "help", "myself", "myself is"]
        if first_word.lower() not in skip_words:
            return first_word
    return "Friend"

def extract_and_normalize_field(field_name: str, message: str) -> str:
    """Use Groq to extract and normalize a profile field from user message."""
    standards = {
        "state": "One of the Indian states or Union Territories (e.g., 'Telangana', 'Andhra Pradesh', 'Delhi', 'Maharashtra', 'Karnataka', 'Tamil Nadu', etc. in standard English).",
        "occupation": "One of: 'student', 'farmer', 'daily wage', 'business', 'government', 'other'.",
        "caste_category": "One of: 'General', 'OBC', 'SC', 'ST', 'EWS'.",
        "gender": "One of: 'Male', 'Female', 'Other'.",
        "age": "Return the age as a number (e.g. 25).",
        "income_bracket": "Estimate the annual family income in Indian Rupees. Return it as a number (e.g., 150000) or 'unknown'.",
        "land_size": "Extract the land size in acres as a number (e.g. 2.5). If they don't own land or say 'no land', return '0'.",
        "email": "Extract the email address. If they skip, say no, or don't provide one, return 'skip'.",
    }
    
    prompt = f"""
    You are a data normalization assistant.
    Analyze the user's message and extract the value for the profile field '{field_name}'.
    The message might be in English, Hindi, Telugu, Tamil, or Kannada.
    
    Standard target format: {standards.get(field_name, '')}
    
    User Message: "{message}"
    
    Respond ONLY with the extracted and normalized value in English (no punctuation, no explanation). If you cannot extract the value, respond with 'unknown'.
    """
    
    try:
        messages = [{"role": "user", "content": prompt}]
        result = safe_groq_chat(messages, temperature=0.1)
        cleaned = result.strip().strip("'\"")
        if cleaned.lower() != "unknown":
            return cleaned
    except Exception as e:
        logger.warning(f"Groq field extraction failed: {e}")
    return message

# ---------- Intent Detection & Handlers ----------
def detect_intent(state: Dict[str, Any]) -> Dict[str, Any]:
    """Determine user intent for routing with smart detection.
    Updates `state["intent"].
    """
    message = state.get("message", "").lower()
    session_id = state.get("session_id")
    user_doc = sync_users_collection.find_one({"session_id": session_id}) or {}
    
    # Check if user is in middle of onboarding
    onboarding_step = user_doc.get("onboarding_step", "name")
    
    # Active onboarding steps - if user is in any of these, always route to onboarding
    active_onboarding_steps = [
        "language_preference", "form_chat_choice", "state", "occupation", 
        "caste_category", "gender", "age", "income_bracket", "confirmation"
    ]
    
    is_in_active_onboarding = onboarding_step in active_onboarding_steps
    
    # Scheme‑related keywords
    is_scheme_question = any(kw in message for kw in SCHEME_KEYWORDS)
    # Check if user wants personal scheme matching (needs profile)
    needs_profile = any(kw in message for kw in PROFILE_REQUIRED_KEYWORDS)
    profile_complete = all(user_doc.get(f) for f in REQUIRED_FIELDS)
    
    # Check if message looks like a name (simple heuristic: single word, not a keyword)
    words = message.strip().split()
    looks_like_name = len(words) <= 2 and not any(kw in message for kw in SCHEME_KEYWORDS + ["what", "how", "why", "tell", "know", "want", "need"])
    
    # Smart routing logic:
    # 1. If user is in active onboarding step, always continue onboarding
    if is_in_active_onboarding:
        intent = "onboarding"
    # 2. If user has name but not complete, continue onboarding
    elif onboarding_step != "complete" and user_doc.get("name"):
        intent = "onboarding"
    # 3. If user provides a name (looks like name and no name yet) -> onboarding
    elif looks_like_name and not user_doc.get("name"):
        intent = "onboarding"
    # 4. If user wants personal scheme matching but doesn't have complete profile -> onboarding
    elif needs_profile and not profile_complete:
        intent = "onboarding"
    # 5. If user wants personal scheme matching and has complete profile -> scheme_query
    elif needs_profile and profile_complete:
        intent = "scheme_query"
    # 6. If user asks general scheme questions (not personal) -> FAQ with general knowledge
    elif is_scheme_question:
        intent = "faq"
    # 7. Otherwise (general questions, greetings, etc.) -> FAQ with general knowledge
    else:
        intent = "faq"
    
    state["intent"] = intent
    state["user_profile"] = user_doc
    logger.info(f"detect_intent -> {intent} (onboarding_step: {onboarding_step})")
    return state

def handle_onboarding(state: Dict[str, Any]) -> Dict[str, Any]:
    """Collect missing profile fields step‑by‑step with Groq normalization."""
    session_id = state["session_id"]
    message = state["message"].strip()
    user_doc = sync_users_collection.find_one({"session_id": session_id}) or {}
    current_step = user_doc.get("onboarding_step", "name")

    def update_profile(updates: Dict[str, Any]):
        sync_users_collection.update_one(
            {"session_id": session_id},
            {"$set": updates},
            upsert=True,
        )

    # STEP 1 – name extraction
    if current_step == "name":
        name = extract_first_name(message)
        update_profile({"name": name, "onboarding_step": "language_preference"})
        state["reply"] = (
            f"Hi {name}! 😊\n\n"
            "Which language do you prefer?\n[English] [हिंदी] [తెలుగు] [தமிழ்] [ಕನ್ನಡ]"
        )
        state["onboarding_step"] = "language_preference"
        state["chips"] = ["English", "हिंदी", "తెలుగు", "தமிழ்", "ಕನ್ನಡ", "Start Over"]
        return state

    # STEP 2 – language preference
    if current_step == "language_preference":
        lang_map = {
            "hindi": "hi",
            "हिंदी": "hi",
            "telugu": "te",
            "తెలుగు": "te",
            "tamil": "ta",
            "தமிழ்": "ta",
            "kannada": "kn",
            "ಕನ್ನಡ": "kn",
        }
        lower_msg = message.lower()
        lang = "en"
        for key, code in lang_map.items():
            if key in lower_msg:
                lang = code
                break
        
        update_profile({"language_preference": lang, "onboarding_step": "form_chat_choice"})
        state["reply"] = (
            "I am here to help you find out your government schemes and benefits that you qualify for! "
            "How would you like to provide your details to continue? You can fill out a form or continue via chat."
        )
        state["onboarding_step"] = "form_chat_choice"
        state["chips"] = ["Fill Form", "Chat Instead", "Start Over"]
        return state

    # STEP 3 - Form / Chat Choice
    if current_step == "form_chat_choice":
        if any(w in message.lower() for w in ["chat", "chat instead", "just chat"]):
            update_profile({"onboarding_step": "state"})
            state["reply"] = "Great! Let's collect your details here in the chat. Which state are you from?"
            state["onboarding_step"] = "state"
            state["chips"] = ["Andhra Pradesh", "Telangana", "Delhi", "Maharashtra", "Tamil Nadu", "Karnataka", "Start Over"]
        elif any(w in message.lower() for w in ["form", "fill form"]):
            state["reply"] = "Please fill out the form displayed on your screen to find your schemes."
            state["show_form_choice"] = True
            state["chips"] = ["Fill Form", "Chat Instead", "Start Over"]
        else:
            state["reply"] = "Please choose: 'Fill Form' or 'Chat Instead'"
            state["chips"] = ["Fill Form", "Chat Instead", "Start Over"]
        return state

    # Subsequent fields order
    fields_order = [
        "state",
        "occupation",
        "caste_category",
        "gender",
        "age",
        "income_bracket",
        "land_size",
    ]
    questions = {
        "state": "Which state are you from?",
        "occupation": "What is your occupation? (student/farmer/daily wage/business/govt/other)",
        "caste_category": "Caste category? (SC/ST/OBC/General)",
        "gender": "Gender? (Male/Female/Other)",
        "age": "How old are you?",
        "income_bracket": "Annual family income in rupees?",
        "land_size": "How much agricultural land do you own (in acres)? (Enter 0 if none)",
    }
    field_chips = {
        "state": ["Andhra Pradesh", "Telangana", "Delhi", "Maharashtra", "Tamil Nadu", "Karnataka"],
        "occupation": ["Student", "Farmer", "Daily Wage", "Business", "Government", "Other"],
        "caste_category": ["General", "OBC", "SC", "ST"],
        "gender": ["Male", "Female", "Other"],
        "age": ["18-25", "26-35", "36-50", "50+"],
        "income_bracket": ["Below 1 Lakh", "1-2.5 Lakh", "2.5-5 Lakh", "5-10 Lakh", "Above 10 Lakh"],
        "land_size": ["0", "1", "2.5", "5", "10", "20"],
    }
    
    if current_step == "continue_confirm":
        if any(w in message.lower() for w in ["yes", "y", "yeah", "sure"]):
            update_profile({"onboarding_step": "state"})
            state["reply"] = "Great! Which state are you from?"
            state["onboarding_step"] = "state"
            state["chips"] = field_chips["state"] + ["Start Over"]
        else:
            state["intent"] = "faq"
            state["reply"] = "No problem! Feel free to ask me any question about welfare schemes."
            state["chips"] = ["Find My Schemes", "Start Over"]
        return state

    if current_step in fields_order:
        # Normalize the input field using Groq
        normalized_value = extract_and_normalize_field(current_step, message)
        
        # Save value
        updates = {current_step: normalized_value}
        
        # Move to next step
        next_step_index = fields_order.index(current_step) + 1
        next_step = fields_order[next_step_index] if next_step_index < len(fields_order) else "confirmation"
        updates["onboarding_step"] = next_step
        update_profile(updates)
        
        # Determine next missing field
        user_doc = sync_users_collection.find_one({"session_id": session_id}) or {}
        
        # Required fields check
        required_missing = [f for f in REQUIRED_FIELDS if not user_doc.get(f)]
        if not required_missing and user_doc.get("onboarding_step") == "confirmation":
            # Profile complete – show confirmation summary
            summary = (
                f"Please confirm your details:\n\n"
                f"Name: {user_doc.get('name')}\n"
                f"Language: {user_doc.get('language_preference')}\n"
                f"State: {user_doc.get('state')}\n"
                f"Occupation: {user_doc.get('occupation')}\n"
                f"Category: {user_doc.get('caste_category')}\n"
                f"Gender: {user_doc.get('gender')}\n"
                f"Age: {user_doc.get('age')}\n"
                f"Income: {user_doc.get('income_bracket')}\n"
                f"Land Size: {user_doc.get('land_size')} acres\n"
                f"Email: {user_doc.get('email') or 'Not subscribed'}\n\n"
                f"Is this correct?"
            )
            state["reply"] = summary
            state["onboarding_step"] = "confirmation"
            update_profile({"confirmation_step": "awaiting_confirmation", "onboarding_step": "confirmation"})
            state["confirmation_step"] = "awaiting_confirmation"
            state["chips"] = ["Yes Continue", "Edit Details", "Start Over"]
            return state
            
        next_field = next_step
        if next_field == "confirmation":
            # Just in case
            update_profile({"onboarding_step": "confirmation"})
            return handle_onboarding(state)
            
        state["reply"] = questions.get(next_field, f"Please provide your {next_field}.")
        state["onboarding_step"] = next_field
        state["chips"] = field_chips.get(next_field, []) + ["Start Over"]
        return state

    # Handle confirmation step
    if current_step == "confirmation":
        confirmation_step = user_doc.get("confirmation_step", "awaiting_confirmation")
        
        if confirmation_step == "awaiting_confirmation":
            if any(w in message.lower() for w in ["yes", "y", "yeah", "correct", "right", "yes continue"]):
                update_profile({"onboarding_step": "complete", "confirmation_step": "completed"})
                state["intent"] = "scheme_query"
                state["onboarding_step"] = "complete"
                return handle_scheme_query(state)
            elif any(w in message.lower() for w in ["no", "n", "edit", "change", "edit details"]):
                update_profile({"confirmation_step": "selecting_field"})
                state["reply"] = "Which field would you like to edit? (name, state, occupation, category, gender, age, income, land size, email)"
                state["confirmation_step"] = "selecting_field"
                state["chips"] = ["Name", "State", "Occupation", "Category", "Gender", "Age", "Income", "Land Size", "Email", "Start Over"]
                return state
            else:
                state["reply"] = "Please respond with 'Yes Continue' to confirm or 'Edit Details' to change your details."
                state["chips"] = ["Yes Continue", "Edit Details", "Start Over"]
                return state
                
        elif confirmation_step == "selecting_field":
            field_map = {
                "name": "name",
                "state": "state",
                "occupation": "occupation",
                "category": "caste_category",
                "caste": "caste_category",
                "gender": "gender",
                "age": "age",
                "income": "income_bracket",
                "land": "land_size",
                "land size": "land_size",
                "email": "email"
            }
            field_to_edit = field_map.get(message.lower().strip())
            if not field_to_edit:
                state["reply"] = "Please choose: name, state, occupation, category, gender, age, income, land size, or email"
                state["chips"] = ["Name", "State", "Occupation", "Category", "Gender", "Age", "Income", "Land Size", "Email", "Start Over"]
                return state
            update_profile({"confirmation_step": "editing_value", "editing_field": field_to_edit})
            state["reply"] = f"What is your new {field_to_edit.replace('_', ' ')}?"
            state["confirmation_step"] = "editing_value"
            state["editing_field"] = field_to_edit
            state["chips"] = ["Start Over"]
            return state
            
        elif confirmation_step == "editing_value":
            field_to_edit = user_doc.get("editing_field")
            if field_to_edit:
                normalized_value = extract_and_normalize_field(field_to_edit, message)
                updates = {field_to_edit: normalized_value, "confirmation_step": "awaiting_confirmation", "editing_field": None}
                if field_to_edit == "email":
                    if normalized_value.lower() in ["skip", "no", "n", "none"]:
                        updates["email"] = ""
                        updates["email_reminders"] = False
                    else:
                        updates["email"] = normalized_value
                        updates["email_reminders"] = True
                update_profile(updates)
                
                # Show summary again
                user_doc = sync_users_collection.find_one({"session_id": session_id}) or {}
                summary = (
                    f"Please confirm your updated details:\n\n"
                    f"Name: {user_doc.get('name')}\n"
                    f"Language: {user_doc.get('language_preference')}\n"
                    f"State: {user_doc.get('state')}\n"
                    f"Occupation: {user_doc.get('occupation')}\n"
                    f"Category: {user_doc.get('caste_category')}\n"
                    f"Gender: {user_doc.get('gender')}\n"
                    f"Age: {user_doc.get('age')}\n"
                    f"Income: {user_doc.get('income_bracket')}\n"
                    f"Land Size: {user_doc.get('land_size')} acres\n"
                    f"Email: {user_doc.get('email') or 'Not subscribed'}\n\n"
                    f"Is this correct?"
                )
                state["reply"] = summary
                state["confirmation_step"] = "awaiting_confirmation"
                state["chips"] = ["Yes Continue", "Edit Details", "Start Over"]
                return state

    state["reply"] = "Could you provide more details?"
    state["chips"] = ["Start Over"]
    return state

    # Fallback – should not reach here
    state["reply"] = "Could you provide more details?"
    return state

def handle_faq(state: Dict[str, Any]) -> Dict[str, Any]:
    """Answer generic questions via Groq without needing a profile."""
    user_doc = state.get("user_profile", {})
    language = user_doc.get("language_preference", "en")
    
    # Import language prompts
    from agent.languages import SYSTEM_PROMPTS
    system_prompt = SYSTEM_PROMPTS.get(language, SYSTEM_PROMPTS["en"])
    reply = safe_groq_chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": state["message"]},
        ],
        temperature=0.7,
    )
    state["reply"] = reply or "I’m here to help! Ask me about welfare schemes."
    return state

def handle_scheme_query(state: Dict[str, Any]) -> Dict[str, Any]:
    """Return matching schemes based on the stored user profile with Phase 8 3-tier retrieval and dynamic chips."""
    session_id = state["session_id"]
    user_message = state["message"].strip()
    user_doc = sync_users_collection.find_one({"session_id": session_id}) or {}
    
    # Helper to persist updates
    def update_profile(updates: Dict[str, Any]):
        sync_users_collection.update_one(
            {"session_id": session_id},
            {"$set": updates},
            upsert=True,
        )

    # 1. Check if user clicked/typed a sub-action ("Apply Now", "Check Eligibility", "Required Documents")
    selected_scheme_name = user_doc.get("selected_scheme")
    
    if selected_scheme_name:
        scheme_doc = sync_schemes_collection.find_one({"name": selected_scheme_name})
        
        # Sub-action: Apply Now
        if any(w in user_message.lower() for w in ["apply now", "apply"]):
            link = scheme_doc.get("apply_link", "the official portal") if scheme_doc else "the official portal"
            state["reply"] = f"To apply for **{selected_scheme_name}**, please visit the official website:\n\n{link}\n\nLet me know if you need help with documentation or eligibility criteria!"
            state["chips"] = ["Check Eligibility", "Required Documents", "Ask Something Else", "Start Over"]
            return state
            
        # Sub-action: Required Documents
        elif any(w in user_message.lower() for w in ["required documents", "documents", "document"]):
            docs = scheme_doc.get("required_documents", []) if scheme_doc else []
            docs_list = "\n".join([f"• {d}" for d in docs]) if docs else "No specific documents listed. Standard ID proof, income, and residence certificates are typically required."
            state["reply"] = f"The required documents for **{selected_scheme_name}** are:\n\n{docs_list}"
            state["chips"] = ["Apply Now", "Check Eligibility", "Ask Something Else", "Start Over"]
            return state
            
        # Sub-action: Check Eligibility
        elif any(w in user_message.lower() for w in ["check eligibility", "eligibility", "eligible"]):
            rules = scheme_doc.get("eligibility_rules", {}) if scheme_doc else {}
            rules_desc = []
            if "state" in rules: rules_desc.append(f"State: {rules['state']}")
            if "caste_category" in rules: rules_desc.append(f"Category: {rules['caste_category']}")
            if "occupation" in rules: rules_desc.append(f"Occupation: {rules['occupation']}")
            if "max_income" in rules: rules_desc.append(f"Max Annual Income: Rs. {rules['max_income']}")
            if "max_land_size" in rules: rules_desc.append(f"Max Land Holdings: {rules['max_land_size']} acres")
            if "min_age" in rules: rules_desc.append(f"Min Age: {rules['min_age']}")
            if "max_age" in rules: rules_desc.append(f"Max Age: {rules['max_age']}")
            if "gender" in rules: rules_desc.append(f"Gender: {rules['gender']}")
            
            desc_text = "\n".join([f"• {r}" for r in rules_desc]) if rules_desc else "Standard eligibility conditions apply. Please check official guidelines."
            state["reply"] = f"The eligibility criteria for **{selected_scheme_name}** are:\n\n{desc_text}"
            state["chips"] = ["Apply Now", "Required Documents", "Ask Something Else", "Start Over"]
            return state
            
        # Sub-action: Ask Something Else
        elif any(w in user_message.lower() for w in ["ask something else", "something else"]):
            update_profile({"selected_scheme": None})
            state["reply"] = "What else would you like to know? You can ask about other schemes or general questions."
            from agent.eligibility import match_schemes
            schemes = match_schemes(user_doc, sync_schemes_collection)
            scheme_names = [s.get("name") for s in schemes[:4]]
            state["chips"] = scheme_names + ["Start Over"]
            return state

    # 2. Check if user clicked/typed a scheme name specifically
    # Find if user typed a specific scheme name present in database
    all_schemes = list(sync_schemes_collection.find({}, {"name": 1}))
    matched_by_name = None
    for s in all_schemes:
        if s["name"].lower() in user_message.lower() or user_message.lower() in s["name"].lower():
            if len(user_message) >= 5: # prevent matching short strings
                matched_by_name = s["name"]
                break
                
    if matched_by_name:
        update_profile({"selected_scheme": matched_by_name})
        scheme_doc = sync_schemes_collection.find_one({"name": matched_by_name})
        desc = scheme_doc.get("description", "Government scheme")
        cat = scheme_doc.get("category", "Welfare")
        deadline = scheme_doc.get("deadline", "Ongoing")
        
        state["reply"] = f"Here are the details for **{matched_by_name}**:\n\n{desc}\n\n**Category**: {cat}\n**Deadline**: {deadline}"
        state["chips"] = ["Apply Now", "Check Eligibility", "Required Documents", "Ask Something Else", "Start Over"]
        return state

    # 3. Else, perform 3-tier retrieval if asking details or general knowledge
    # Check if user is asking detailed question about a specific scheme
    scheme_keywords = ["what", "how", "documents", "need", "require", "details", "benefits", "eligible", "pension", "scholarship"]
    asking_details = any(kw in user_message.lower() for kw in scheme_keywords)
    
    try:
        from agent.eligibility import match_schemes
        schemes = match_schemes(user_doc, sync_schemes_collection)
        
        # If asking details (or mentioning a scheme name), try 3-tier
        if asking_details or any(s.get("name").lower() in user_message.lower() for s in schemes):
            # Try to identify which scheme they are asking about
            scheme_name = schemes[0].get("name", "") if schemes else ""
            for s in schemes:
                if s.get("name").lower() in user_message.lower():
                    scheme_name = s.get("name")
                    break
                    
            if scheme_name:
                logger.info(f"3-tier retrieval for: {scheme_name}")
                
                # TIER 1: ChromaDB
                try:
                    from agent.chroma_retrieval import get_scheme_details_from_chroma
                    chroma_result = get_scheme_details_from_chroma(scheme_name)
                    if chroma_result and chroma_result.get("found"):
                        answer = safe_groq_chat([
                            {"role": "system", "content": f"You are a helpful assistant for Indian welfare schemes. Answer the user's question based ONLY on the following scheme data. If the answer is not in the data, say so.\n\nScheme Data:\n{chroma_result['text']}"},
                            {"role": "user", "content": state["message"]}
                        ])
                        state["reply"] = f"For **{scheme_name}**:\n\n{answer}"
                        update_profile({"selected_scheme": scheme_name})
                        state["chips"] = ["Apply Now", "Check Eligibility", "Required Documents", "Ask Something Else", "Start Over"]
                        return state
                except Exception as e:
                    logger.warning(f"ChromaDB retrieval failed: {e}")
                
                # TIER 2: Live Search
                try:
                    import asyncio
                    from live_fetcher.live_scheme_fetcher import fetch_scheme_details_live
                    from live_fetcher.groq_live_parser import answer_scheme_question_with_live_data
                    
                    live_data = asyncio.run(fetch_scheme_details_live(scheme_name))
                    if live_data:
                        answer = answer_scheme_question_with_live_data(groq_client, scheme_name, state["message"], live_data)
                        state["reply"] = f"For **{scheme_name}**:\n\n{answer}"
                        update_profile({"selected_scheme": scheme_name})
                        state["chips"] = ["Apply Now", "Check Eligibility", "Required Documents", "Ask Something Else", "Start Over"]
                        return state
                except Exception as e:
                    logger.warning(f"Live fetch failed: {e}")
                
                # TIER 3: Groq general knowledge
                answer = safe_groq_chat([
                    {"role": "system", "content": f"You are a helpful assistant for Indian welfare schemes. The user is asking about '{scheme_name}'. Provide helpful information based on your knowledge, but clearly state that this information may be outdated and they should verify from the official government website. Do not hallucinate specific details like income limits or deadlines."},
                    {"role": "user", "content": state["message"]}
                ])
                state["reply"] = f"For **{scheme_name}**:\n\n{answer}\n\n*Note: This information is based on general knowledge and may be outdated. Please verify from the official government website.*"
                update_profile({"selected_scheme": scheme_name})
                state["chips"] = ["Apply Now", "Check Eligibility", "Required Documents", "Ask Something Else", "Start Over"]
                return state
        
        # 4. Standard schemes list showing (if they just say yes or ask to find schemes)
        if schemes:
            scheme_list = "\n".join([
                f"• **{s['name']}** - {s['description']}\n  Apply: {s['apply_link']}"
                for s in schemes[:4]
            ])
            
            state["reply"] = f"Found {len(schemes)} matching schemes for your profile:\n\n{scheme_list}\n\nSelect a scheme from the chips below to see details, check eligibility, and apply!"
            state["chips"] = [s.get("name") for s in schemes[:4]] + ["Start Over"]
        else:
            state["reply"] = "No matching schemes found."
            state["chips"] = ["Start Over"]
            
    except Exception as e:
        logger.error(f"Scheme query error: {e}")
        state["reply"] = "I had trouble retrieving schemes. Please try again."
        state["chips"] = ["Start Over"]
        
    return state

def calculate_confidence(message: str, user_doc: dict) -> float:
    """Calculate confidence score for the response (0-100)."""
    confidence = 85.0  # Base confidence
    
    # Higher confidence for scheme-related questions
    scheme_keywords = ["scheme", "yojana", "benefit", "eligible", "pension", "scholarship", "kisan", "farmer", "student"]
    if any(kw in message.lower() for kw in scheme_keywords):
        confidence += 10
    
    # Lower confidence for very general or vague questions
    vague_keywords = ["something", "anything", "help", "what", "how"]
    if len(message.split()) < 3 or any(kw in message.lower() for kw in vague_keywords):
        confidence -= 15
    
    # Higher confidence if user has profile
    if user_doc and user_doc.get("name"):
        confidence += 5
    
    # Clamp between 0 and 100
    return max(0, min(100, confidence))
