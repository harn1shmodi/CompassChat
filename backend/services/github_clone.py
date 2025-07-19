import git
import tempfile
import shutil
import os
from pathlib import Path
from typing import Generator
import logging
import requests
import gc

logger = logging.getLogger(__name__)


class GitHubCloner:
    def __init__(self, max_repo_size_mb: int = 300):
        self.temp_dir = None
        self.max_repo_size_mb = max_repo_size_mb
    
    def clone_repo(self, repo_url: str) -> Generator[dict, None, None]:
        """Clone a GitHub repository with size pre-check and streaming processing"""
        try:
            # Validate GitHub URL
            if not self.is_valid_github_url(repo_url):
                yield {"status": "error", "message": "Invalid GitHub URL"}
                return
            
            # Pre-check repository size
            yield {"status": "progress", "message": "Checking repository size..."}
            repo_size_mb = self.get_repo_size_github_api(repo_url)
            
            if repo_size_mb > self.max_repo_size_mb:
                yield {
                    "status": "error", 
                    "message": f"Repository too large: {repo_size_mb}MB (max: {self.max_repo_size_mb}MB). "
                               f"Consider filtering large files or contact support for enterprise repos."
                }
                return
            elif repo_size_mb > 0:
                yield {"status": "progress", "message": f"Repository size: {repo_size_mb}MB - proceeding with optimized clone"}
            
            # Create temporary directory
            self.temp_dir = tempfile.mkdtemp(prefix="compass_chat_")
            yield {"status": "progress", "message": "Created temporary directory"}
            
            # Clone repository with optimization for large repos
            yield {"status": "progress", "message": "Cloning repository with optimizations..."}
            try:
                # Try blobless clone first (faster for large repos)
                repo = git.Repo.clone_from(
                    repo_url, 
                    self.temp_dir,
                    filter='blob:none',  # Download trees/commits, fetch blobs on-demand
                    single_branch=True   # Only default branch
                )
                yield {"status": "progress", "message": "Optimized clone completed"}
            except Exception as filter_error:
                logger.warning(f"Blobless clone failed, using standard clone: {filter_error}")
                # Fallback to standard clone
                repo = git.Repo.clone_from(repo_url, self.temp_dir)
                yield {"status": "progress", "message": "Standard clone completed"}
            
            # Get repository info
            repo_info = self.get_repo_info(repo)
            yield {"status": "info", "data": repo_info}
            
            # Stream file processing instead of loading all at once
            yield {"status": "progress", "message": "Starting streaming file analysis..."}
            total_files = 0
            all_files = []
            
            for file_batch in self.get_source_files_streaming(self.temp_dir):
                batch_size = len(file_batch["files"])
                total_files += batch_size
                all_files.extend(file_batch["files"])
                
                yield {
                    "status": "files_batch", 
                    "data": {
                        "batch": file_batch["files"],
                        "total_processed": total_files,
                        "temp_dir": self.temp_dir
                    }
                }
                
                # Memory cleanup every 100 files
                if total_files % 100 == 0:
                    gc.collect()
            
            # Final summary
            yield {
                "status": "files", 
                "data": {
                    "files": all_files, 
                    "temp_dir": self.temp_dir,
                    "total_files": total_files,
                    "repo_size_mb": repo_size_mb
                }
            }
            
            yield {"status": "cloning_complete", "message": f"Repository analysis complete - {total_files} files processed"}
            
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
    
    def get_repo_size_github_api(self, repo_url: str) -> int:
        """Get repository size in MB using GitHub API"""
        try:
            # Extract owner/repo from URL
            if repo_url.startswith("https://github.com/"):
                parts = repo_url.replace("https://github.com/", "").replace(".git", "").split("/")
            elif repo_url.startswith("git@github.com:"):
                parts = repo_url.replace("git@github.com:", "").replace(".git", "").split("/")
            elif repo_url.startswith("github.com/"):
                parts = repo_url.replace("github.com/", "").replace(".git", "").split("/")
            else:
                logger.warning(f"Cannot extract repo info from URL: {repo_url}")
                return 0
            
            if len(parts) < 2:
                logger.warning(f"Invalid GitHub URL format: {repo_url}")
                return 0
                
            owner, repo = parts[0], parts[1]
            
            # Call GitHub API
            api_url = f"https://api.github.com/repos/{owner}/{repo}"
            response = requests.get(api_url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                size_kb = data.get('size', 0)
                size_mb = size_kb // 1024  # Convert to MB
                logger.info(f"Repository {owner}/{repo} size: {size_mb}MB")
                return size_mb
            elif response.status_code == 404:
                logger.warning(f"Repository not found or private: {owner}/{repo}")
                return 0
            else:
                logger.warning(f"GitHub API error {response.status_code} for {owner}/{repo}")
                return 0
                
        except requests.RequestException as e:
            logger.warning(f"Failed to check repository size via API: {e}")
            return 0
        except Exception as e:
            logger.warning(f"Error checking repository size: {e}")
            return 0
    
    def get_source_files(self, repo_path: str) -> list:
        """Get list of source code and documentation files"""
        source_extensions = {
            # Source code files
            '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h', '.hpp',
            '.cs', '.go', '.rs', '.php', '.rb', '.swift', '.kt', '.scala', '.sh',
            # Documentation files
            '.md', '.json', '.txt', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
            # Configuration and build files
            'Dockerfile', 'docker-compose.yml', 'package.json', 'requirements.txt',
            'composer.json', 'pom.xml', 'build.gradle', 'Cargo.toml', 'go.mod'
        }
        
        files = []
        repo_path = Path(repo_path)
        
        for file_path in repo_path.rglob("*"):
            if file_path.is_file() and not self.should_ignore_path(file_path, repo_path):
                # Check extension or exact filename match
                file_name = file_path.name
                file_extension = file_path.suffix.lower()
                
                if file_extension in source_extensions or file_name in source_extensions:
                    relative_path = file_path.relative_to(repo_path)
                    files.append({
                        "path": str(relative_path),
                        "absolute_path": str(file_path),
                        "size": file_path.stat().st_size,
                        "extension": file_extension or file_name
                    })
        
        return files
    
    def get_source_files_streaming(self, repo_path: str, batch_size: int = 50) -> Generator[dict, None, None]:
        """Stream source files in batches for memory efficiency"""
        source_extensions = {
            # Source code files
            '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h', '.hpp',
            '.cs', '.go', '.rs', '.php', '.rb', '.swift', '.kt', '.scala', '.sh',
            # Documentation files
            '.md', '.json', '.txt', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
            # Configuration and build files
            'Dockerfile', 'docker-compose.yml', 'package.json', 'requirements.txt',
            'composer.json', 'pom.xml', 'build.gradle', 'Cargo.toml', 'go.mod'
        }
        
        repo_path = Path(repo_path)
        batch = []
        total_processed = 0
        
        for file_path in repo_path.rglob("*"):
            if file_path.is_file() and not self.should_ignore_path_enhanced(file_path, repo_path):
                # Check extension or exact filename match
                file_name = file_path.name
                file_extension = file_path.suffix.lower()
                
                if file_extension in source_extensions or file_name in source_extensions:
                    try:
                        relative_path = file_path.relative_to(repo_path)
                        file_info = {
                            "path": str(relative_path),
                            "absolute_path": str(file_path),
                            "size": file_path.stat().st_size,
                            "extension": file_extension or file_name
                        }
                        batch.append(file_info)
                        
                        # Yield batch when it reaches the specified size
                        if len(batch) >= batch_size:
                            total_processed += len(batch)
                            yield {"files": batch, "total_processed": total_processed}
                            batch = []
                            
                    except (OSError, ValueError) as e:
                        logger.warning(f"Error processing file {file_path}: {e}")
                        continue
        
        # Yield remaining files in the last batch
        if batch:
            total_processed += len(batch)
            yield {"files": batch, "total_processed": total_processed}
    
    def should_ignore_path(self, file_path: Path, repo_path: Path) -> bool:
        """Check if a file path should be ignored (legacy method)"""
        return self.should_ignore_path_enhanced(file_path, repo_path)
    
    def should_ignore_path_enhanced(self, file_path: Path, repo_path: Path) -> bool:
        """Enhanced filtering for large repositories"""
        try:
            # Size-based filtering - skip files > 5MB
            file_size = file_path.stat().st_size
            if file_size > 5 * 1024 * 1024:  # 5MB limit
                logger.debug(f"Skipping large file: {file_path} ({file_size / 1024 / 1024:.1f}MB)")
                return True
        except OSError:
            # File might be inaccessible, skip it
            return True
        
        # Enhanced ignore patterns for large repos
        ignore_patterns = {
            # Standard patterns
            'node_modules', '.git', '__pycache__', '.pytest_cache', 'venv', 'env',
            '.venv', 'build', 'dist', '.next', '.nuxt', 'target', 'bin', 'obj',
            # Additional patterns for large repos
            'vendor', 'packages', 'deps', 'lib', 'libs', 'external',
            'third-party', 'third_party', 'assets', 'static', 'media',
            'images', 'img', 'fonts', 'videos', 'audio', 'docs/_build',
            'site-packages', 'bower_components', 'jspm_packages',
            '.tox', '.coverage', '.nyc_output', 'coverage', 'htmlcov',
            '.gradle', '.mvn', '.idea', '.vscode', '.vs', '.settings',
            'cmake-build-*', 'out', 'Debug', 'Release', 'x64', 'x86'
        }
        
        # File extension filtering - skip large binary files
        large_file_extensions = {
            # Archives and packages
            '.zip', '.tar', '.gz', '.rar', '.7z', '.bz2', '.xz',
            # Executables and binaries
            '.exe', '.msi', '.dmg', '.pkg', '.deb', '.rpm', '.snap', '.appimage',
            '.bin', '.dll', '.so', '.dylib', '.a', '.lib', '.pdb',
            # Media files
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.ico', '.webp',
            '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv',
            '.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac',
            # Document formats (often large)
            '.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx',
            # Development artifacts
            '.jar', '.war', '.ear', '.class', '.pyc', '.pyo', '.egg',
            '.whl', '.gem', '.nupkg', '.vsix',
            # Database files
            '.db', '.sqlite', '.sqlite3', '.mdb', '.accdb',
            # Log files
            '.log', '.logs'
        }
        
        file_extension = file_path.suffix.lower()
        if file_extension in large_file_extensions:
            logger.debug(f"Skipping file with filtered extension: {file_path}")
            return True
        
        # Check if any part of the path matches ignore patterns
        try:
            relative_path = file_path.relative_to(repo_path)
            path_parts = relative_path.parts
            
            # Skip hidden files and directories (except specific exceptions)
            if any(part.startswith('.') and part not in {'.github', '.gitignore', '.env.example'} for part in path_parts):
                return True
            
            # Skip directories matching ignore patterns
            if any(part in ignore_patterns for part in path_parts):
                return True
            
            # Skip files with certain patterns in the name
            file_name_lower = file_path.name.lower()
            skip_patterns = ['test', 'tests', 'spec', 'specs', 'mock', 'mocks', 'fixture', 'fixtures']
            
            # Only skip test files if they're in dedicated test directories
            for pattern in skip_patterns:
                if pattern in file_name_lower and any(test_dir in path_parts for test_dir in ['test', 'tests', 'spec', 'specs', '__tests__']):
                    return True
            
            return False
            
        except ValueError:
            # File is not under repo root
            return True
    
    def cleanup(self):
        """Clean up temporary directory"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            self.temp_dir = None
