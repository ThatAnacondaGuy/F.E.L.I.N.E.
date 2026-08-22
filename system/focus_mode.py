"""Hostile Focus Mode enforcer for Meow OS."""
import time
import logging
import subprocess
from enum import Enum
from pydantic import BaseModel

from .applescript import quit_app, set_dock_autohide, enable_dnd, disable_dnd, run_applescript

logger = logging.getLogger(__name__)

class FocusIntensity(str, Enum):
    LIGHT = 'light'
    MEDIUM = 'medium'
    HOSTILE = 'hostile'

class FocusState(BaseModel):
    is_active: bool = False
    activated_at: float | None = None
    intensity: FocusIntensity | None = None
    duration_minutes: int | None = None

class FocusMode:
    """Manages system focus state and distraction blocking."""
    
    DISTRACTING_APPS = ['Discord', 'WhatsApp', 'Telegram', 'Slack', 'Messages', 'Twitter', 'TweetDeck']
    BLOCKED_DOMAINS = ['reddit.com', 'twitter.com', 'x.com', 'instagram.com', 'facebook.com', 'tiktok.com', 'youtube.com']
    
    def __init__(self):
        self.state = FocusState()
    
    def activate(self, intensity: FocusIntensity = FocusIntensity.LIGHT, duration_minutes: int = 60) -> bool:
        """Activate focus mode with specified intensity."""
        if self.state.is_active:
            self.deactivate()
            
        logger.info(f"Activating {intensity.value.upper()} focus mode for {duration_minutes} minutes")
        
        # Level 1: LIGHT (Close apps)
        for app in self.DISTRACTING_APPS:
            quit_app(app)
            
        # Level 2: MEDIUM (Apps + Block sites via Safari tabs)
        if intensity in (FocusIntensity.MEDIUM, FocusIntensity.HOSTILE):
            self._close_distracting_tabs()
            # To block via hosts, user needs to run a sudo helper script
            # Example: sudo python3 scripts/block_hosts.py
            
        # Level 3: HOSTILE (Apps + Sites + Hide Dock + DND)
        if intensity == FocusIntensity.HOSTILE:
            set_dock_autohide(True)
            enable_dnd()
            
        self.state = FocusState(
            is_active=True,
            activated_at=time.time(),
            intensity=intensity,
            duration_minutes=duration_minutes
        )
        self._log_audit("activate", intensity.value)
        return True
        
    def deactivate(self) -> bool:
        """Deactivate focus mode."""
        if not self.state.is_active:
            return False
            
        logger.info(f"Deactivating {self.state.intensity.value.upper()} focus mode")
        
        if self.state.intensity == FocusIntensity.HOSTILE:
            set_dock_autohide(False)
            disable_dnd()
            
        self.state = FocusState()
        self._log_audit("deactivate", "none")
        return True
        
    def check_timer(self) -> None:
        """Check if focus mode should be auto-deactivated based on timer."""
        if not self.state.is_active or not self.state.activated_at or not self.state.duration_minutes:
            return
            
        elapsed = (time.time() - self.state.activated_at) / 60.0
        if elapsed >= self.state.duration_minutes:
            logger.info("Focus mode timer expired")
            self.deactivate()
            
    def _close_distracting_tabs(self) -> None:
        """Close Safari tabs containing distracting URLs using AppleScript."""
        for domain in self.BLOCKED_DOMAINS:
            script = f'''
            tell application "Safari"
                repeat with w in windows
                    repeat with t in tabs of w
                        if URL of t contains "{domain}" then
                            close t
                        end if
                    end repeat
                end repeat
            end tell
            '''
            run_applescript(script)
            
    def _log_audit(self, action: str, intensity: str) -> None:
        """Log focus mode changes."""
        logger.info(f"AUDIT: FocusMode {action} at intensity {intensity}")

    def get_remaining_minutes(self) -> int:
        """Get remaining minutes of the current focus session."""
        if not self.state.is_active or not self.state.activated_at or not self.state.duration_minutes:
            return 0
        elapsed = (time.time() - self.state.activated_at) / 60.0
        rem = self.state.duration_minutes - elapsed
        return int(max(0, rem))
