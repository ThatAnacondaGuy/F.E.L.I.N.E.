"""Error analysis engine for Meow OS."""
import hashlib
import logging
from enum import Enum, auto

logger = logging.getLogger(__name__)

class ErrorType(Enum):
    PYTHON = auto()
    CUDA = auto()
    BUILD = auto()
    NPM = auto()
    UNKNOWN = auto()

class ErrorAnalyzer:
    """Engine to classify and generate AI prompts for terminal errors."""
    
    def __init__(self):
        self.cache: dict[str, str] = {}
        
    def classify_error(self, text: str) -> ErrorType:
        """Determine the type of error from the text."""
        text = text.lower()
        if 'traceback' in text or 'python' in text:
            return ErrorType.PYTHON
        elif 'cuda' in text or 'nvcc' in text:
            return ErrorType.CUDA
        elif 'err!' in text or 'npm' in text:
            return ErrorType.NPM
        elif 'make: ***' in text or 'fatal error:' in text:
            return ErrorType.BUILD
        return ErrorType.UNKNOWN
        
    def extract_context(self, text: str, error_line: int) -> str:
        """Extract 50 surrounding lines for context."""
        lines = text.splitlines()
        start = max(0, error_line - 25)
        end = min(len(lines), error_line + 25)
        return "\n".join(lines[start:end])
        
    def generate_prompt(self, error: str, error_type: str, context: str) -> str:
        """Generate specialized system prompts based on error type."""
        system_prompt = "You are an AI coding assistant."
        
        if error_type == ErrorType.CUDA.name:
            system_prompt = "You are a senior CUDA/GPU programming expert. Aniket is learning CUDA for his NVIDIA career goal."
        elif error_type == ErrorType.PYTHON.name:
            system_prompt = "You are a senior Python developer. Explain the error simply and provide the fix."
            
        prompt = f"{system_prompt}\n\nAnalyze the following error and provide a fix:\nERROR:\n{error}\n\nCONTEXT:\n{context}\n"
        return prompt
        
    def format_solution(self, raw_response: str) -> str:
        """Clean and format the AI solution to markdown."""
        return f"### Error Solution\n\n{raw_response.strip()}"
