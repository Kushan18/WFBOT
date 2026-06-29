import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()
MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI not set in .env")

client = MongoClient(MONGODB_URI)
db = client["welfarebot"]
schemes = db["schemes"]

scheme_docs = [
    {
        "name": "Telangana Post-Matric SC Scholarship",
        "description": "Covers tuition and maintenance for SC students in Telangana",
        "eligibility_rules": {"state": "Telangana", "caste_category": "SC", "occupation": "student", "max_income": 250000},
        "required_documents": ["Aadhaar card", "Caste certificate", "Income certificate", "Previous marksheet", "Bank passbook"],
        "apply_link": "https://telanganaepass.cgg.gov.in",
        "deadline": "2025-11-30",
        "category": "scholarship"
    },
    {
        "name": "PM KISAN Samman Nidhi",
        "description": "Direct income support of Rs 6000/year to small farmers",
        "eligibility_rules": {"state": "all", "occupation": "farmer", "max_income": 600000, "max_land_size": 5.0},
        "required_documents": ["Aadhaar card", "Land ownership documents", "Bank account details"],
        "apply_link": "https://pmkisan.gov.in",
        "deadline": "ongoing",
        "category": "agricultural"
    },
    {
        "name": "Rythu Bandhu Scheme",
        "description": "Telangana government input support scheme providing Rs 10,000/acre per year to farmers.",
        "eligibility_rules": {"state": "Telangana", "occupation": "farmer", "max_land_size": 25.0},
        "required_documents": ["Aadhaar card", "Pattadar Passbook (land ownership)", "Bank account details"],
        "apply_link": "http://rythubandhu.telangana.gov.in",
        "deadline": "ongoing",
        "category": "agricultural"
    },
    {
        "name": "National Means-cum-Merit Scholarship",
        "description": "Rs 12000/year for meritorious students from weaker sections",
        "eligibility_rules": {"state": "all", "occupation": "student", "max_income": 150000, "min_age": 14, "max_age": 18},
        "required_documents": ["Aadhaar card", "Income certificate", "Previous class marksheet", "School certificate"],
        "apply_link": "https://scholarships.gov.in",
        "deadline": "2025-10-31",
        "category": "scholarship"
    },
    {
        "name": "PM Matru Vandana Yojana",
        "description": "Cash incentive of Rs 5000 for first child's birth to pregnant women",
        "eligibility_rules": {"state": "all", "gender": "Female"},
        "required_documents": ["Aadhaar card", "Bank account details", "MCP card", "Husband Aadhaar"],
        "apply_link": "https://pmmvy.wcd.gov.in",
        "deadline": "ongoing",
        "category": "welfare"
    },
    {
        "name": "Dr. Ambedkar Post-Matric Scholarship for SC Students",
        "description": "Central scholarship covering fees for SC students",
        "eligibility_rules": {"state": "all", "caste_category": "SC", "occupation": "student", "max_income": 250000},
        "required_documents": ["Aadhaar card", "Caste certificate", "Income certificate", "Marksheet", "Fee receipt"],
        "apply_link": "https://scholarships.gov.in",
        "deadline": "2025-12-31",
        "category": "scholarship"
    },
    {
        "name": "OBC Post-Matric Scholarship",
        "description": "Scholarship for OBC students pursuing post-matric education",
        "eligibility_rules": {
            "state": "all",
            "caste_category": "OBC",
            "occupation": "student",
            "max_income": 300000
        },
        "required_documents": ["Aadhaar card", "Caste certificate", "Income certificate", "Marksheet"],
        "apply_link": "https://scholarships.gov.in",
        "deadline": "2025-12-31",
        "category": "scholarship"
    },
    {
        "name": "PM Vishwakarma Yojana",
        "description": "Support for traditional artisans and craftspeople with training and credit",
        "eligibility_rules": {
            "state": "all",
            "occupation": "other"
        },
        "required_documents": ["Aadhaar card", "Bank account details"],
        "apply_link": "https://pmvishwakarma.gov.in",
        "deadline": "ongoing",
        "category": "livelihood"
    },
    {
        "name": "Telangana Kalyana Lakshmi",
        "description": "Financial assistance of Rs 1,00,116 for marriage of girls from OBC/SC/ST families in Telangana",
        "eligibility_rules": {
            "state": "Telangana",
            "gender": "Female"
        },
        "required_documents": ["Aadhaar card", "Caste certificate", "Marriage certificate", "Bank passbook"],
        "apply_link": "https://telanganaepass.cgg.gov.in",
        "deadline": "ongoing",
        "category": "welfare"
    },
    {
        "name": "Central Sector Scholarship for College Students",
        "description": "Rs 10,000-20,000 per year for meritorious students from families with income below 4.5 lakhs",
        "eligibility_rules": {
            "state": "all",
            "occupation": "student",
            "max_income": 450000
        },
        "required_documents": ["Aadhaar card", "Income certificate", "Marksheet", "Bank passbook"],
        "apply_link": "https://scholarships.gov.in",
        "deadline": "2025-11-30",
        "category": "scholarship"
    },
    {
        "name": "Pradhan Mantri Kaushal Vikas Yojana",
        "description": "Free skill training and certification for youth to improve employability",
        "eligibility_rules": {
            "state": "all",
            "max_income": 500000
        },
        "required_documents": ["Aadhaar card", "Bank account details"],
        "apply_link": "https://pmkvyofficial.org",
        "deadline": "ongoing",
        "category": "skill development"
    }
]

inserted = 0
updated = 0
for doc in scheme_docs:
    if schemes.find_one({"name": doc["name"]}):
        schemes.update_one({"name": doc["name"]}, {"$set": doc})
        updated += 1
    else:
        schemes.insert_one(doc)
        inserted += 1

print(f"Seeded {inserted} schemes, updated {updated} schemes successfully")

