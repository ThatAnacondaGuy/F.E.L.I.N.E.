"""System control modules for Meow OS."""
from .applescript import *
from .focus_mode import *
from .workspaces import *
from .spotify import *

__all__ = [
    'run_applescript', 'quit_app', 'launch_app', 'is_app_running', 'get_frontmost_app',
    'set_volume', 'get_volume', 'mute_volume', 'unmute_volume',
    'enable_dnd', 'disable_dnd', 'open_url', 'open_urls_in_tabs',
    'display_notification', 'set_dock_autohide',
    'FocusMode', 'FocusIntensity',
    'WorkspaceManager',
    'SpotifyController',
]
