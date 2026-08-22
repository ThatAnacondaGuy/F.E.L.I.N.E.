"""Spotify AppleScript controller for Meow OS."""
import logging
from typing import Optional
from .applescript import run_applescript

logger = logging.getLogger(__name__)

class SpotifyController:
    """Controls Spotify playback via AppleScript without API keys."""
    
    def __init__(self):
        self._last_position: Optional[float] = None
        
    def _run_spotify_script(self, command: str) -> tuple[bool, str]:
        """Helper to run Spotify specific AppleScript."""
        script = f'''
        if application "Spotify" is running then
            tell application "Spotify"
                {command}
            end tell
        else
            return "not running"
        end if
        '''
        return run_applescript(script)
        
    def play(self) -> bool:
        ok, _ = self._run_spotify_script('play')
        return ok
        
    def pause(self) -> bool:
        ok, _ = self._run_spotify_script('pause')
        return ok
        
    def toggle(self) -> bool:
        ok, _ = self._run_spotify_script('playpause')
        return ok
        
    def next_track(self) -> bool:
        ok, _ = self._run_spotify_script('next track')
        return ok
        
    def previous_track(self) -> bool:
        ok, _ = self._run_spotify_script('previous track')
        return ok
        
    def play_playlist(self, uri: str) -> bool:
        """Play a specific Spotify URI (playlist, album, track)."""
        ok, _ = self._run_spotify_script(f'play track "{uri}"')
        return ok
        
    def get_current_track(self) -> dict[str, str]:
        """Get info about the currently playing track."""
        script = '''
        set track_name to name of current track
        set track_artist to artist of current track
        set track_album to album of current track
        return track_name & "|||" & track_artist & "|||" & track_album
        '''
        ok, output = self._run_spotify_script(script)
        if ok and output != "not running" and "|||" in output:
            parts = output.split("|||")
            if len(parts) >= 3:
                return {
                    "title": parts[0].strip(),
                    "artist": parts[1].strip(),
                    "album": parts[2].strip()
                }
        return {}
        
    def is_playing(self) -> bool:
        ok, output = self._run_spotify_script('return player state as string')
        return ok and "playing" in output.lower()
        
    def set_volume(self, level: int) -> bool:
        """Set Spotify specific volume (0-100)."""
        level = max(0, min(100, level))
        ok, _ = self._run_spotify_script(f'set sound volume to {level}')
        return ok
        
    def pause_for_lecture(self) -> bool:
        """Pause playback and remember position for later."""
        if self.is_playing():
            ok, pos = self._run_spotify_script('return player position')
            if ok:
                try:
                    self._last_position = float(pos)
                except ValueError:
                    self._last_position = None
            self.pause()
            return True
        return False
        
    def resume_after_lecture(self) -> bool:
        """Resume playback where it was left off."""
        self.play()
        if self._last_position is not None:
            self._run_spotify_script(f'set player position to {self._last_position}')
            self._last_position = None
        return True
        
    def start_focus_playlist(self, uri: str) -> bool:
        """Switch to focus playlist and lower volume."""
        self.set_volume(30)
        return self.play_playlist(uri)
