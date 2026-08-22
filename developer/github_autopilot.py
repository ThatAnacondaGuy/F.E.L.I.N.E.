"""GitHub auto-commit and assistant for Meow OS."""
import os
import subprocess
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class AutoCommitProposal(BaseModel):
    repo_path: str
    files_changed: List[str]
    diff_summary: str
    proposed_message: str
    status: str = "pending"

class GitHubAutopilot:
    """Manages automatic git commits and AI commit messages."""
    
    def __init__(self):
        self.on_commit_proposed = None
        
    def _run_git(self, repo_path: str, cmd: List[str]) -> tuple[bool, str]:
        """Run a git command in a specific repository."""
        try:
            result = subprocess.run(
                ['git', '-C', repo_path] + cmd,
                capture_output=True, text=True, check=True
            )
            return True, result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.error(f"Git error in {repo_path}: {e.stderr}")
            return False, e.stderr.strip() if e.stderr else ""
            
    def scan_projects(self, directories: List[str]) -> List[str]:
        """Scan directories for git repositories with uncommitted changes."""
        dirty_repos = []
        for d in directories:
            path = os.path.expanduser(d)
            if not os.path.exists(path):
                continue
                
            ok, output = self._run_git(path, ['status', '--porcelain'])
            if ok and output:
                dirty_repos.append(path)
                
        return dirty_repos
        
    def check_stale_repos(self, directories: List[str], max_days: int = 4) -> List[str]:
        """Check for repos that haven't been committed to recently."""
        stale_repos = []
        cutoff_date = datetime.now() - timedelta(days=max_days)
        
        for d in directories:
            path = os.path.expanduser(d)
            ok, output = self._run_git(path, ['log', '-1', '--format=%cI'])
            if ok and output:
                try:
                    last_commit = datetime.fromisoformat(output.replace('Z', '+00:00'))
                    if last_commit.replace(tzinfo=None) < cutoff_date:
                        stale_repos.append(path)
                except ValueError:
                    pass
        return stale_repos
        
    def generate_proposal(self, repo_path: str) -> Optional[AutoCommitProposal]:
        """Generate an AI commit proposal for a repo."""
        ok_stat, stat = self._run_git(repo_path, ['diff', '--stat'])
        ok_diff, diff = self._run_git(repo_path, ['diff'])
        
        if not ok_stat or not stat:
            # Maybe changes are staged but not committed
            ok_stat, stat = self._run_git(repo_path, ['diff', '--cached', '--stat'])
            ok_diff, diff = self._run_git(repo_path, ['diff', '--cached'])
            
            if not ok_stat or not stat:
                return None
                
        files_changed = [line.strip().split()[0] for line in stat.split('\n') if '|' in line]
        
        # Mock AI message generation
        mock_message = "feat: automated updates for project files\n\n- Proposed by GitHubAutopilot"
        
        proposal = AutoCommitProposal(
            repo_path=repo_path,
            files_changed=files_changed,
            diff_summary=stat,
            proposed_message=mock_message,
            status="pending"
        )
        
        if self.on_commit_proposed:
            self.on_commit_proposed(proposal)
            
        return proposal
        
    def stage_and_commit(self, repo_path: str, message: str) -> bool:
        """Stage all changes and commit with the given message."""
        ok_add, _ = self._run_git(repo_path, ['add', '.'])
        if not ok_add:
            return False
            
        ok_commit, _ = self._run_git(repo_path, ['commit', '-m', message])
        return ok_commit
        
    def push(self, repo_path: str) -> bool:
        """Push commits to the remote."""
        ok, _ = self._run_git(repo_path, ['push'])
        return ok
