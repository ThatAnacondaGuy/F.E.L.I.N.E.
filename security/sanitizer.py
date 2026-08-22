"""Log and output sanitizer to prevent leaking secrets."""

import re

# Common patterns for secrets and PII
PATTERNS = [
    # Email addresses
    (re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'), '[REDACTED_EMAIL]'),
    # Bearer tokens
    (re.compile(r'Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*'), 'Bearer [REDACTED_TOKEN]'),
    # API Keys (generic 32+ hex/alphanumeric)
    (re.compile(r'(?i)(api[_-]?key|secret|token)[\s:=]+[\'"]?([a-zA-Z0-9\-\._~]{32,})[\'"]?'), r'\1=[REDACTED_KEY]'),
]

def sanitize(text: str) -> str:
    """Sanitize text by redacting sensitive information."""
    if not isinstance(text, str):
        return text
        
    sanitized = text
    for pattern, replacement in PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
        
    return sanitized
