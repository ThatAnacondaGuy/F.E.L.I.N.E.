"""Terminal error monitoring and watchdog for Meow OS."""
import time
import re
import logging
from pathlib import Path
from collections import deque
from threading import Thread, Event
from typing import Callable, Optional
from .error_analyzer import ErrorAnalyzer

logger = logging.getLogger(__name__)

class WatchdogThread(Thread):
    def __init__(self, target: Callable, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.target_func = target
        self._stop_event = Event()
        self.daemon = True
        
    def stop(self):
        self._stop_event.set()
        
    def stopped(self) -> bool:
        return self._stop_event.is_set()
        
    def run(self):
        self.target_func(self)

class TerminalWatchdog:
    """Monitors log files for terminal errors and triggers analysis."""
    
    ERROR_PATTERNS = [
        re.compile(r'Traceback \(most recent call last\)'),
        re.compile(r'cudaError'),
        re.compile(r'CUDA_ERROR'),
        re.compile(r'nvcc fatal'),
        re.compile(r'CUDA out of memory'),
        re.compile(r'error:'),
        re.compile(r'fatal error:'),
        re.compile(r'make: \*\*\*'),
        re.compile(r'ERR!'),
        re.compile(r'Error:'),
        re.compile(r'error\[E'),
    ]
    
    def __init__(self):
        self.analyzer = ErrorAnalyzer()
        self.on_solution_found: Optional[Callable[[str], None]] = None
        self._last_analysis_time = 0.0
        self.rate_limit_seconds = 30.0
        self.context_buffer: deque[str] = deque(maxlen=100)
        
    def check_line_for_errors(self, line: str) -> bool:
        """Check if a line matches any known error patterns."""
        for pattern in self.ERROR_PATTERNS:
            if pattern.search(line):
                return True
        return False
        
    def process_error(self, error_line: str, context_lines: list[str]) -> None:
        """Process a detected error with rate limiting."""
        now = time.time()
        if now - self._last_analysis_time < self.rate_limit_seconds:
            logger.info("Rate limit hit, skipping error analysis")
            return
            
        self._last_analysis_time = now
        context = "\n".join(context_lines)
        
        logger.info(f"Analyzing error: {error_line.strip()}")
        error_type = self.analyzer.classify_error(error_line)
        prompt = self.analyzer.generate_prompt(error_line, error_type.name, context)
        
        # Send to backend (mocked for now)
        solution = self.analyzer.format_solution("MOCK SOLUTION: " + prompt[:50] + "...")
        
        if self.on_solution_found:
            self.on_solution_found(solution)
            
    def watch_file(self, filepath: str | Path) -> Optional[WatchdogThread]:
        """Monitor a file for errors."""
        path = Path(filepath)
        if not path.exists():
            logger.error(f"File {path} does not exist.")
            return None
            
        def _tail(thread: WatchdogThread):
            with open(path, 'r') as f:
                f.seek(0, 2)
                while not thread.stopped():
                    line = f.readline()
                    if not line:
                        time.sleep(0.1)
                        continue
                        
                    self.context_buffer.append(line)
                    if self.check_line_for_errors(line):
                        context = list(self.context_buffer)
                        self.process_error(line, context)
                        
        thread = WatchdogThread(target=_tail)
        thread.start()
        return thread
        
    def watch_directory(self, dirpath: str | Path):
        """Monitor all log files in a directory."""
        logger.info(f"Directory watch mode initialized for {dirpath}.")
        # To be fully implemented in phase 2.
