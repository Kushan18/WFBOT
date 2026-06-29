from typing import List, Dict, Any
from pymongo.collection import Collection

def match_schemes(user_profile: Dict[str, Any], schemes_collection: Collection) -> List[Dict[str, Any]]:
    """
    Takes user profile and returns matching schemes from MongoDB.
    Returns list of scheme documents that match ALL eligibility rules.
    """
    user = user_profile
    
    # Start with base query - match state or all or no state restriction
    base_query = {
        "$or": [
            {"eligibility_rules.state": user.get("state")},
            {"eligibility_rules.state": "all"},
            {"eligibility_rules.state": {"$exists": False}}
        ]
    }
    
    # Build additional filters
    additional_filters = []

    # Add caste filter if user has it
    if user.get("caste_category"):
        additional_filters.append({
            "$or": [
                {"eligibility_rules.caste_category": user.get("caste_category")},
                {"eligibility_rules.caste_category": "all"},
                {"eligibility_rules.caste_category": {"$exists": False}}
            ]
        })

    # Add occupation filter if user has it
    if user.get("occupation"):
        additional_filters.append({
            "$or": [
                {"eligibility_rules.occupation": user.get("occupation")},
                {"eligibility_rules.occupation": "all"},
                {"eligibility_rules.occupation": "any"},
                {"eligibility_rules.occupation": {"$exists": False}}
            ]
        })

    # Add land size filter if user has it
    if user.get("land_size") is not None:
        try:
            user_land = float(user.get("land_size"))
            additional_filters.append({
                "$or": [
                    {"eligibility_rules.max_land_size": {"$gte": user_land}},
                    {"eligibility_rules.max_land_size": {"$exists": False}}
                ]
            })
        except (ValueError, TypeError):
            pass

    # Add income filter if user has it
    if user.get("income_bracket"):
        try:
            user_income = int(user.get("income_bracket"))
            additional_filters.append({
                "$or": [
                    {"eligibility_rules.max_income": {"$gte": user_income}},
                    {"eligibility_rules.max_income": {"$exists": False}}
                ]
            })
        except (ValueError, TypeError):
            pass

    # Add age filter if user has it
    if user.get("age"):
        try:
            user_age = int(user.get("age"))
            # Min age condition
            additional_filters.append({
                "$or": [
                    {"eligibility_rules.min_age": {"$lte": user_age}},
                    {"eligibility_rules.min_age": {"$exists": False}}
                ]
            })
            # Max age condition
            additional_filters.append({
                "$or": [
                    {"eligibility_rules.max_age": {"$gte": user_age}},
                    {"eligibility_rules.max_age": {"$exists": False}}
                ]
            })
        except (ValueError, TypeError):
            pass

    # Combine all filters with AND
    if additional_filters:
        final_query = {"$and": [base_query] + additional_filters}
    else:
        final_query = base_query

    matching = list(schemes_collection.find(final_query).limit(10))
    return matching
