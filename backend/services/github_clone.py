import git
import tempfile
import shutil
import os
from pathlib import Path
from typing import Generator
import logging

logger = logging.getLogger(__name__)


class GitHubCloner:
    def __init__(self):
        self.temp_dir = None
    
    def clone_repo(self, repo_url: str) -> Generator[dict, None, None]:
        """Clone a GitHub repository and yield progress updates"""
        try:
            # Validate GitHub URL
            if not self.is_valid_github_url(repo_url):
                yield {"status": "error", "message": "Invalid GitHub URL"}
                return
            
            # Create temporary directory
            self.temp_dir = tempfile.mkdtemp(prefix="compass_chat_")
            yield {"status": "progress", "message": "Created temporary directory"}
            
            # Clone repository
            yield {"status": "progress", "message": "Cloning repository..."}
            repo = git.Repo.clone_from(repo_url, self.temp_dir)
            
            yield {"status": "progress", "message": "Repository cloned successfully"}
            
            # Get repository info
            repo_info = self.get_repo_info(repo)
            yield {"status": "info", "data": repo_info}
            
            # Get file structure
            files = self.get_source_files(self.temp_dir)
            yield {"status": "files", "data": {"files": files, "temp_dir": self.temp_dir}}
            
            yield {"status": "complete", "message": "Repository analysis ready"}
            
        except Exception as e:
            logger.error(f"Error cloning repository: {e}")
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
            yield {"status": "error", "message": f"Failed to clone repository: {str(e)}"}
    
    def is_valid_github_url(self, url: str) -> bool:
        """Validate if the URL is a valid GitHub repository URL"""
        return (
            url.startswith("https://github.com/") or 
            url.startswith("git@github.com:") or
            url.startswith("github.com/")
        )
    
    def get_repo_info(self, repo: git.Repo) -> dict:
        """Extract repository information"""
        try:
            remote_url = repo.remotes.origin.url
            # Extract owner and repo name from URL
            if remote_url.startswith("https://github.com/"):
                parts = remote_url.replace("https://github.com/", "").replace(".git", "").split("/")
            elif remote_url.startswith("git@github.com:"):
                parts = remote_url.replace("git@github.com:", "").replace(".git", "").split("/")
            else:
                parts = ["unknown", "unknown"]
            
            return {
                "owner": parts[0] if len(parts) > 0 else "unknown",
                "name": parts[1] if len(parts) > 1 else "unknown",
                "url": remote_url,
                "default_branch": repo.active_branch.name if repo.active_branch else "main"
            }
        except Exception as e:
            logger.warning(f"Could not extract repo info: {e}")
            return {
                "owner": "unknown",
                "name": "unknown", 
                "url": "unknown",
                "default_branch": "main"
            }
    
    def get_source_files(self, repo_path: str) -> list:
        """Get list of source code files"""
        source_extensions = {
            '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h', '.hpp',
            '.cs', '.go', '.rs', '.php', '.rb', '.swift', '.kt', '.scala', '.sh'
        }
        
        files = []
        repo_path = Path(repo_path)
        
        for file_path in repo_path.rglob("*"):
            if (file_path.is_file() and 
                file_path.suffix.lower() in source_extensions and
                not self.should_ignore_path(file_path, repo_path)):
                
                relative_path = file_path.relative_to(repo_path)
                files.append({
                    "path": str(relative_path),
                    "absolute_path": str(file_path),
                    "size": file_path.stat().st_size,
                    "extension": file_path.suffix.lower()
                })
        
        return files
    
    def should_ignore_path(self, file_path: Path, repo_path: Path) -> bool:
        """Check if a file path should be ignored"""
        ignore_patterns = {
            'node_modules', '.git', '__pycache__', '.pytest_cache', 'venv', 'env',
            '.venv', 'build', 'dist', '.next', '.nuxt', 'target', 'bin', 'obj'
        }
        
        # Check if any part of the path matches ignore patterns
        relative_path = file_path.relative_to(repo_path)
        path_parts = relative_path.parts
        
        return any(part.startswith('.') and part != '..' for part in path_parts) or \
               any(part in ignore_patterns for part in path_parts)
    
    def cleanup(self):
        """Clean up temporary directory"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            self.temp_dir = None
