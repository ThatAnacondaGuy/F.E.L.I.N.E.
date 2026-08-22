"""Authority level and permission system."""

from database.models import AuthorityLevel

# Maps action categories to required authority levels
ACTION_AUTHORITY_MAP = {
    "read_data": AuthorityLevel.AUTOMATIC,
    "write_data": AuthorityLevel.AUTOMATIC,
    "send_email": AuthorityLevel.CONFIRM,
    "delete_data": AuthorityLevel.EXPLICIT,
    "modify_schedule": AuthorityLevel.CONFIRM,
    "financial_transaction": AuthorityLevel.EXPLICIT
}

def check_permission(action_category: str, agent: str) -> AuthorityLevel:
    """
    Check the required permission level for an action category.
    Returns the required AuthorityLevel.
    """
    # In a full system, we might also check agent-specific overrides.
    # For now, return the baseline requirement.
    return ACTION_AUTHORITY_MAP.get(action_category, AuthorityLevel.EXPLICIT)
