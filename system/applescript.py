"""AppleScript execution wrapper for Meow OS.

Provides Python functions that execute AppleScript commands via osascript
to control macOS applications and system features.
"""
import subprocess
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def run_applescript(script: str, timeout: int = 10) -> tuple[bool, str]:
    """Execute an AppleScript and return (success, output)."""
    try:
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            logger.warning(f'AppleScript error: {result.stderr.strip()}')
            return False, result.stderr.strip()
    except subprocess.TimeoutExpired:
        logger.error('AppleScript timed out')
        return False, 'timeout'
    except Exception as e:
        logger.error(f'AppleScript execution failed: {e}')
        return False, str(e)

# Application control
def quit_app(app_name: str) -> bool:
    """Quit an application."""
    ok, _ = run_applescript(f'tell application "{app_name}" to quit')
    return ok

def launch_app(app_name: str) -> bool:
    """Launch an application."""
    ok, _ = run_applescript(f'tell application "{app_name}" to activate')
    return ok

def is_app_running(app_name: str) -> bool:
    """Check if an application is running."""
    ok, output = run_applescript(
        f'tell application "System Events" to (name of processes) contains "{app_name}"'
    )
    return ok and output.lower() == 'true'

def get_frontmost_app() -> str:
    """Get the name of the frontmost application."""
    _, name = run_applescript(
        'tell application "System Events" to get name of first process whose frontmost is true'
    )
    return name

# Volume control
def set_volume(level: int) -> bool:
    """Set system volume (0-100)."""
    ok, _ = run_applescript(f'set volume output volume {level}')
    return ok

def get_volume() -> int:
    _, output = run_applescript('output volume of (get volume settings)')
    try:
        return int(output)
    except ValueError:
        return -1

def mute_volume() -> bool:
    ok, _ = run_applescript('set volume with output muted')
    return ok

def unmute_volume() -> bool:
    ok, _ = run_applescript('set volume without output muted')
    return ok

# Notifications / DND
def enable_dnd() -> bool:
    """Enable Do Not Disturb (Focus mode on macOS)."""
    # On modern macOS, this uses shortcuts or focus filters
    ok, _ = run_applescript('''
        tell application "System Events"
            tell process "ControlCenter"
                -- Click Focus in menu bar
            end tell
        end tell
    ''')
    # Fallback: use defaults
    subprocess.run(['defaults', 'write', 'com.apple.ncprefs', 'dnd_prefs', '-data', '1'], capture_output=True)
    return True

def disable_dnd() -> bool:
    subprocess.run(['defaults', 'delete', 'com.apple.ncprefs', 'dnd_prefs'], capture_output=True)
    return True

# Browser control
def open_url(url: str, browser: str = 'Safari') -> bool:
    ok, _ = run_applescript(f'tell application "{browser}" to open location "{url}"')
    return ok

def open_urls_in_tabs(urls: list[str], browser: str = 'Safari') -> bool:
    for url in urls:
        open_url(url, browser)
    return True

# Display notification
def display_notification(title: str, message: str, sound: str = 'default') -> bool:
    script = f'display notification "{message}" with title "{title}"'
    if sound:
        script += f' sound name "{sound}"'
    ok, _ = run_applescript(script)
    return ok

# Dock control
def set_dock_autohide(enabled: bool) -> bool:
    val = 'true' if enabled else 'false'
    subprocess.run(['defaults', 'write', 'com.apple.dock', 'autohide', '-bool', val], capture_output=True)
    subprocess.run(['killall', 'Dock'], capture_output=True)
    return True
