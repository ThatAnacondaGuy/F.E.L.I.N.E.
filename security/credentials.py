"""Credential management using keyring."""

import keyring
import logging

logger = logging.getLogger(__name__)
SYSTEM_NAME = "MeowOS"

def store_credential(service: str, key: str, value: str) -> bool:
    """Store a credential securely."""
    try:
        keyring.set_password(f"{SYSTEM_NAME}_{service}", key, value)
        return True
    except Exception as e:
        logger.error(f"Failed to store credential for {service}/{key}: {e}")
        return False

def get_credential(service: str, key: str) -> str | None:
    """Retrieve a stored credential."""
    try:
        return keyring.get_password(f"{SYSTEM_NAME}_{service}", key)
    except Exception as e:
        logger.error(f"Failed to retrieve credential for {service}/{key}: {e}")
        return None

def delete_credential(service: str, key: str) -> bool:
    """Delete a stored credential."""
    try:
        keyring.delete_password(f"{SYSTEM_NAME}_{service}", key)
        return True
    except keyring.errors.PasswordDeleteError:
        return False
    except Exception as e:
        logger.error(f"Failed to delete credential for {service}/{key}: {e}")
        return False
