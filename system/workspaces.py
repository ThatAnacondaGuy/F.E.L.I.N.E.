"""Contextual workspace launcher for Meow OS."""
import os
try:
    import tomllib
except ImportError:
    import tomli as tomllib
import logging
from pathlib import Path
from typing import Any

from .applescript import launch_app, open_urls_in_tabs
from .focus_mode import FocusMode, FocusIntensity
from .spotify import SpotifyController

logger = logging.getLogger(__name__)

class WorkspaceManager:
    """Manages workspaces for different contexts (study, dev, research)."""
    
    def __init__(self, config_path: str = "configs/workspaces.toml"):
        self.config_path = Path(config_path)
        self.focus_mode = FocusMode()
        self.spotify = SpotifyController()
        self.active_workspace: str | None = None
        self.workspaces: dict[str, Any] = self._load_config()
        
    def _load_config(self) -> dict[str, Any]:
        """Load workspaces from TOML config."""
        if not self.config_path.exists():
            logger.warning(f"Config {self.config_path} not found")
            return {}
        try:
            with open(self.config_path, "rb") as f:
                data = tomllib.load(f)
                return data.get("workspace", {})
        except Exception as e:
            logger.error(f"Failed to load workspaces config: {e}")
            return {}
            
    def list_workspaces(self) -> list[str]:
        """List available workspaces."""
        return list(self.workspaces.keys())
        
    def launch_workspace(self, name: str) -> bool:
        """Launch a specific workspace."""
        if name not in self.workspaces:
            logger.error(f"Workspace {name} not found")
            return False
            
        if self.active_workspace:
            self.teardown_workspace(self.active_workspace)
            
        logger.info(f"Launching workspace: {name}")
        config = self.workspaces[name]
        
        # Open apps & VS Code workspace
        apps = config.get("apps", [])
        for app in apps:
            launch_app(app)
            
        vscode_ws = config.get("vscode_workspace")
        if vscode_ws and "Visual Studio Code" in apps:
            expanded_path = os.path.expanduser(vscode_ws)
            os.system(f'code "{expanded_path}"')
            
        # Open browser tabs
        tabs = config.get("browser_tabs", [])
        if tabs:
            open_urls_in_tabs(tabs, browser="Safari")
            
        # Activate focus mode
        intensity_str = config.get("focus_intensity", "light").upper()
        intensity = getattr(FocusIntensity, intensity_str, FocusIntensity.LIGHT)
        self.focus_mode.activate(intensity=intensity, duration_minutes=120)
        
        # Start Spotify playlist
        playlist = config.get("playlist")
        if playlist:
            self.spotify.play_playlist(playlist)
            
        self.active_workspace = name
        return True
        
    def teardown_workspace(self, name: str) -> bool:
        """Teardown a workspace and return to normal."""
        logger.info(f"Tearing down workspace: {name}")
        self.focus_mode.deactivate()
        self.spotify.pause()
        self.active_workspace = None
        return True

    def get_active_workspace(self) -> str | None:
        """Return the currently active workspace name."""
        return self.active_workspace
