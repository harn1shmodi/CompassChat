import git
import tempfile
import shutil
import os
import subprocess
from pathlib import Path
from typing import Generator
import logging
import requests
import gc
from .repo_optimizer import repo_optimizer

logger = logging.getLogger(__name__)


class GitHubCloner:
    def __init__(self, max_repo_size_mb: int = 1000):  # Increased from 500MB to 1GB
        self.temp_dir = None
        self.max_repo_size_mb = max_repo_size_mb
        self._configure_git_for_memory_efficiency()
    
    def _configure_git_for_memory_efficiency(self):
        """Configure Git for memory-constrained environments like Digital Ocean"""
        try:
            # Configure memory limitations
            git_configs = {
                'pack.windowMemory': '100m',
                'pack.packSizeLimit': '100m', 
                'pack.threads': '1',
                'pack.deltaCacheSize': '25m',
                'core.packedGitWindowSize': '32m',
                'core.packedGitLimit': '128m',
                'core.bigFileThreshold': '50m',
                'http.postBuffer': '524288000',  # 500MB
                'http.lowSpeedLimit': '1000',    # 1KB/s minimum speed
                'http.lowSpeedTime': '600',      # 10 minute timeout
                'core.preloadIndex': 'true',
                'core.fscache': 'true',
                'gc.auto': '256'
            }
            
            for key, value in git_configs.items():
                try:
                    subprocess.run(['git', 'config', '--global', key, value], 
                                 capture_output=True, check=True, timeout=10)
                except subprocess.CalledProcessError as e:
                    logger.warning(f"Failed to set git config {key}: {e}")
                except subprocess.TimeoutExpired:
                    logger.warning(f"Timeout setting git config {key}")
                    
            logger.info("Git configured for memory efficiency")
            
        except Exception as e:
            logger.warning(f"Failed to configure git for memory efficiency: {e}")

    def _get_code_extensions(self):
        """Get comprehensive list of code file extensions"""
        return {
            # JavaScript/TypeScript ecosystem
            '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs',
            # Python ecosystem
            '.py', '.pyi', '.pyx', '.pxd',
            # Java/JVM languages
            '.java', '.scala', '.kt', '.kts', '.groovy',
            # C/C++ family
            '.c', '.cpp', '.cc', '.cxx', '.h', '.hpp', '.hxx',
            # Go, Rust, Swift
            '.go', '.rs', '.swift',
            # C#/.NET
            '.cs', '.vb', '.fs',
            # Ruby, PHP, Perl
            '.rb', '.php', '.pl', '.pm',
            # Shell scripts
            '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd',
            # Web technologies
            '.html', '.htm', '.css', '.scss', '.sass', '.less',
            '.vue', '.svelte', '.astro',
            # Mobile development
            '.m', '.mm', '.dart', '.kotlin',
            # Configuration as code
            '.yaml', '.yml', '.json', '.toml', '.ini', '.cfg',
            '.xml', '.gradle', '.cmake',
            # Documentation
            '.md', '.rst', '.txt', '.adoc',
            # SQL and data
            '.sql', '.graphql', '.proto',
            # Infrastructure as code
            '.tf', '.tfvars', '.hcl',  # Terraform
            '.pp', '.erb',              # Puppet
            '.j2', '.jinja', '.jinja2', # Ansible/Jinja
            # Notebooks
            '.ipynb', '.rmd',
            # Other languages
            '.r', '.R', '.jl', '.lua', '.nim', '.zig', '.v',
            '.ex', '.exs', '.erl', '.hrl',  # Elixir/Erlang
            '.clj', '.cljs', '.cljc',        # Clojure
            '.ml', '.mli',                   # OCaml
            '.hs', '.lhs',                   # Haskell
            '.elm', '.purs',                 # Elm/PureScript
        }

    def _get_exclude_directories(self):
        """Get directories to exclude during sparse checkout"""
        return [
            # Package managers and dependencies (largest space savers)
            'node_modules',
            'vendor',
            '.pnpm',
            'bower_components',
            'jspm_packages',
            'web_modules',
            # Build outputs and compiled files
            'dist',
            'build',
            'out',
            'output',
            'target',
            'bin',
            'obj',
            'lib',
            '_build',
            '.next',
            '.nuxt',
            '.output',
            '.svelte-kit',
            '.parcel-cache',
            # Python specific
            '__pycache__',
            '.pytest_cache',
            '.tox',
            'htmlcov',
            '.coverage',
            '*.egg-info',
            '.mypy_cache',
            '.ruff_cache',
            # IDE and editor directories
            '.idea',
            '.vscode',
            '.vs',
            # Documentation builds
            'docs/_build',
            'site',
            '_site',
            '.docusaurus',
            # Media and assets
            'assets/images',
            'assets/videos',
            'public/images',
            'static/img',
            'media',
            # Logs and temp files
            'logs',
            'tmp',
            'temp',
            # Test outputs
            'coverage',
            '.nyc_output',
            'test-results',
            # Environment and secrets
            '.env',
            '.venv',
            'venv',
            'env',
            'virtualenv',
            # Mobile/iOS specific
            'Pods',
            'DerivedData',
            # .NET specific
            'packages',
            'PublishProfiles',
            # Terraform
            '.terraform',
            # Docker
            '.docker',
        ]

    def _setup_sparse_checkout(self, repo_path: str):
        """Setup sparse checkout with exclusion patterns for optimal performance"""
        try:
            original_dir = os.getcwd()
            os.chdir(repo_path)
            
            # Initialize sparse-checkout in cone mode for performance
            subprocess.run(['git', 'sparse-checkout', 'init', '--cone', '--sparse-index'], 
                         check=True, capture_output=True, timeout=60)
            
            # Instead of restricting to specific directories, use a more inclusive approach
            # Start by including everything, then we'll rely on file-level filtering
            # This ensures we don't miss any important code regardless of directory structure
            
            # For cone mode, we need to specify directories to include, not exclude patterns
            # Since we want to be inclusive, let's disable sparse checkout and rely on file filtering
            subprocess.run(['git', 'sparse-checkout', 'disable'], 
                         check=True, capture_output=True, timeout=60)
            
            logger.info("Sparse checkout disabled - using file-level filtering for better inclusivity")
            return True
            
        except subprocess.TimeoutExpired as e:
            logger.warning(f"Sparse checkout setup timed out: {e}")
            return False
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to setup sparse checkout: {e}")
            return False
        except Exception as e:
            logger.warning(f"Error setting up sparse checkout: {e}")
            return False
        finally:
            try:
                os.chdir(original_dir)
            except:
                pass
    
    def clone_repo(self, repo_url: str) -> Generator[dict, None, None]:
        """Clone a GitHub repository with advanced optimizations for large repos"""
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
                # Provide size estimation to the user
                size_estimate = repo_optimizer.estimate_size_reduction(repo_size_mb)
                yield {
                    "status": "progress", 
                    "message": f"Repository size: {repo_size_mb}MB - proceeding with optimized clone. "
                              f"Estimated final size: {size_estimate['estimated_final_size_mb']}MB "
                              f"({size_estimate['reduction_percentage']}% reduction)"
                }
            
            # Create temporary directory
            self.temp_dir = tempfile.mkdtemp(prefix="compass_chat_")
            yield {"status": "progress", "message": "Created temporary directory"}
            
            # Try optimized clone strategies in order of preference
            clone_success = False
            
            # Strategy 1: Ultra-fast partial clone with sparse checkout (best for large repos)
            # Skip advanced filtering for now as it requires full clone first
            if repo_size_mb > 50:
                yield {"status": "progress", "message": "Attempting ultra-fast partial clone with filtering..."}
                clone_success = self._clone_with_sparse_checkout(repo_url)
                if clone_success:
                    yield {"status": "progress", "message": "Ultra-fast clone completed successfully"}
            
            # Strategy 2: Blobless clone (if Strategy 1 failed)
            if not clone_success:
                yield {"status": "progress", "message": "Attempting blobless clone..."}
                try:
                    repo = git.Repo.clone_from(
                        repo_url, 
                        self.temp_dir,
                        filter='blob:none',  # Download trees/commits, fetch blobs on-demand
                        single_branch=True   # Only default branch
                    )
                    clone_success = True
                    yield {"status": "progress", "message": "Blobless clone completed"}
                except Exception as filter_error:
                    logger.warning(f"Blobless clone failed: {filter_error}")
            
            # Strategy 3: Standard clone (fallback)
            if not clone_success:
                yield {"status": "progress", "message": "Using standard clone as fallback..."}
                try:
                    # Add timeout for standard clone as well
                    repo = git.Repo.clone_from(repo_url, self.temp_dir, single_branch=True)
                    clone_success = True
                    yield {"status": "progress", "message": "Standard clone completed"}
                except Exception as e:
                    logger.error(f"All clone strategies failed: {e}")
                    yield {"status": "error", "message": f"Failed to clone repository: {str(e)}"}
                    return
            
            # Get repository info
            if clone_success:
                try:
                    repo = git.Repo(self.temp_dir)
                    repo_info = self.get_repo_info(repo)
                    yield {"status": "info", "data": repo_info}
                except Exception as e:
                    logger.warning(f"Could not get repo info, using defaults: {e}")
                    repo_info = {"owner": "unknown", "name": "unknown", "url": repo_url, "default_branch": "main"}
                    yield {"status": "info", "data": repo_info}
            
            # Stream file processing with enhanced filtering
            yield {"status": "progress", "message": "Starting optimized file analysis..."}
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

    def _clone_with_sparse_checkout(self, repo_url: str) -> bool:
        """Perform ultra-fast partial clone with sparse checkout filtering"""
        try:
            # Step 1: Blobless clone without checkout
            logger.info("Performing blobless clone...")
            result = subprocess.run([
                'git', 'clone', 
                '--filter=blob:none',  # Only download commit history, not file contents
                '--no-checkout',       # Don't checkout files yet
                '--single-branch',     # Only default branch
                repo_url, 
                self.temp_dir
            ], check=True, capture_output=True, timeout=300)  # 5 minute timeout
            
            # Step 2: Setup sparse checkout
            logger.info("Setting up sparse checkout...")
            if not self._setup_sparse_checkout(self.temp_dir):
                return False
            
            # Step 3: Checkout the files (only what's in sparse-checkout)
            original_dir = os.getcwd()
            os.chdir(self.temp_dir)
            try:
                subprocess.run(['git', 'checkout', 'main'], 
                             check=True, capture_output=True, timeout=300)
            except subprocess.CalledProcessError:
                # Try master if main doesn't exist
                try:
                    subprocess.run(['git', 'checkout', 'master'], 
                                 check=True, capture_output=True, timeout=300)
                except subprocess.CalledProcessError as e:
                    logger.warning(f"Could not checkout main or master branch: {e}")
                    # Get default branch name and checkout
                    try:
                        result = subprocess.run(['git', 'symbolic-ref', 'refs/remotes/origin/HEAD'], 
                                              capture_output=True, text=True, check=True, timeout=60)
                        default_branch = result.stdout.strip().split('/')[-1]
                        subprocess.run(['git', 'checkout', default_branch], 
                                     check=True, capture_output=True, timeout=300)
                    except subprocess.CalledProcessError:
                        logger.warning("Could not determine default branch, proceeding anyway")
            finally:
                os.chdir(original_dir)
            
            logger.info("Ultra-fast clone with sparse checkout completed")
            return True
            
        except subprocess.TimeoutExpired as e:
            logger.warning(f"Sparse checkout clone timed out: {e}")
            return False
        except subprocess.CalledProcessError as e:
            logger.warning(f"Sparse checkout clone failed: {e}")
            return False
        except Exception as e:
            logger.warning(f"Error in sparse checkout clone: {e}")
            return False

    def _clone_with_advanced_filtering(self, repo_url: str) -> bool:
        """Perform clone with git-filter-repo for maximum size reduction"""
        try:
            # First, do a regular clone to a temporary location
            temp_clone_dir = f"{self.temp_dir}_temp"
            logger.info("Performing initial clone for advanced filtering...")
            
            subprocess.run([
                'git', 'clone', 
                '--single-branch',  # Only default branch
                repo_url, 
                temp_clone_dir
            ], check=True, capture_output=True)
            
            # Apply advanced filtering
            logger.info("Applying git-filter-repo advanced filtering...")
            success = repo_optimizer.filter_repository_advanced(temp_clone_dir, self.temp_dir)
            
            if success:
                # Clean up temporary clone
                if os.path.exists(temp_clone_dir):
                    shutil.rmtree(temp_clone_dir)
                
                # Create .gitattributes for better handling
                repo_optimizer.create_gitattributes_file(self.temp_dir)
                
                logger.info("Advanced filtering completed successfully")
                return True
            else:
                # Fallback: move temp clone to main location
                if os.path.exists(temp_clone_dir):
                    if os.path.exists(self.temp_dir):
                        shutil.rmtree(self.temp_dir)
                    shutil.move(temp_clone_dir, self.temp_dir)
                return False
                
        except subprocess.CalledProcessError as e:
            logger.warning(f"Advanced filtering clone failed: {e}")
            return False
        except Exception as e:
            logger.warning(f"Error in advanced filtering clone: {e}")
            return False
    
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
        """Get list of source code and documentation files with enhanced filtering"""
        source_extensions = self._get_code_extensions()
        
        # Essential files to always include
        force_include_files = {
            'README.md', 'LICENSE', 'package.json', 'requirements.txt', 'Gemfile',
            'go.mod', 'Cargo.toml', 'build.gradle', 'pom.xml', 'CMakeLists.txt',
            'Makefile', 'Dockerfile', 'docker-compose.yml', '.gitignore',
            'setup.py', 'pyproject.toml', 'tsconfig.json'
        }
        
        files = []
        repo_path = Path(repo_path)
        
        for file_path in repo_path.rglob("*"):
            if file_path.is_file() and not self.should_ignore_path(file_path, repo_path):
                # Check extension or exact filename match
                file_name = file_path.name
                file_extension = file_path.suffix.lower()
                
                # Include if it's a code file or essential file
                should_include = (
                    file_extension in source_extensions or 
                    file_name in source_extensions or
                    file_name in force_include_files
                )
                
                if should_include:
                    relative_path = file_path.relative_to(repo_path)
                    files.append({
                        "path": str(relative_path),
                        "absolute_path": str(file_path),
                        "size": file_path.stat().st_size,
                        "extension": file_extension or file_name
                    })
        
        return files
    
    def get_source_files_streaming(self, repo_path: str, batch_size: int = 50) -> Generator[dict, None, None]:
        """Stream source files in batches for memory efficiency with enhanced filtering"""
        source_extensions = self._get_code_extensions()
        
        # Essential files to always include (even if they match exclude patterns)
        force_include_files = {
            'README.md', 'LICENSE', 'package.json', 'requirements.txt', 'Gemfile',
            'go.mod', 'Cargo.toml', 'build.gradle', 'pom.xml', 'CMakeLists.txt',
            'Makefile', 'Dockerfile', 'docker-compose.yml', '.gitignore',
            'setup.py', 'pyproject.toml', 'tsconfig.json'
        }
        
        repo_path = Path(repo_path)
        batch = []
        total_processed = 0
        
        for file_path in repo_path.rglob("*"):
            if file_path.is_file() and not self.should_ignore_path_enhanced(file_path, repo_path):
                # Check extension or exact filename match
                file_name = file_path.name
                file_extension = file_path.suffix.lower()
                
                # Include if it's a code file or essential file
                should_include = (
                    file_extension in source_extensions or 
                    file_name in source_extensions or
                    file_name in force_include_files
                )
                
                if should_include:
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
        """Enhanced filtering for large repositories using inspiration file patterns"""
        try:
            # Size-based filtering - skip files > 10MB (increased from 5MB for better filtering)
            file_size = file_path.stat().st_size
            if file_size > 10 * 1024 * 1024:  # 10MB limit
                logger.debug(f"Skipping large file: {file_path} ({file_size / 1024 / 1024:.1f}MB)")
                return True
        except OSError:
            # File might be inaccessible, skip it
            return True
        
        # Use comprehensive exclude patterns from inspiration files
        exclude_directories = set(self._get_exclude_directories())
        
        # File extension filtering - skip large binary files
        exclude_patterns = {
            # Compressed and binary files
            '.zip', '.tar', '.gz', '.bz2', '.7z', '.rar',
            '.jar', '.war', '.ear', '.class',
            # Images (usually not needed for code analysis)
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.svg',
            '.webp', '.tiff', '.psd', '.ai', '.sketch',
            # Videos and audio
            '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm',
            '.mp3', '.wav', '.flac', '.aac', '.ogg',
            # Documents (usually not code)
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            # Databases
            '.db', '.sqlite', '.sqlite3', '.mdb',
            # Large data files
            '.csv', '.tsv', '.parquet', '.feather', '.h5', '.hdf5',
            # Compiled objects and libraries
            '.o', '.a', '.so', '.dll', '.dylib', '.exe',
            # Package files
            '.deb', '.rpm', '.dmg', '.pkg', '.msi',
            # Lock files (can be large)
            'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
            'Gemfile.lock', 'poetry.lock', 'Pipfile.lock',
            'composer.lock', 'Cargo.lock',
            # IDE files
            '.iml', '.ipr', '.iws',
            # OS generated files
            'Thumbs.db', 'desktop.ini', '.Spotlight-V100', '.Trashes',
            # Backup files
            '.bak', '.backup', '.old', '.orig', '.tmp', '.temp',
            # Cache files
            '.cache', '.cached',
            # Python bytecode
            '.pyc', '.pyo', '.pyd',
            # Log files
            '.log', '.logs'
        }
        
        file_extension = file_path.suffix.lower()
        file_name = file_path.name.lower()
        
        # Check file patterns
        if file_extension in exclude_patterns or file_name in exclude_patterns:
            logger.debug(f"Skipping file with filtered pattern: {file_path}")
            return True
        
        # Check if any part of the path matches ignore patterns
        try:
            relative_path = file_path.relative_to(repo_path)
            path_parts = relative_path.parts
            
            # Skip hidden files and directories (except specific exceptions)
            allowed_hidden = {'.github', '.gitignore', '.env.example', '.eslintrc', '.prettierrc'}
            if any(part.startswith('.') and part not in allowed_hidden for part in path_parts):
                return True
            
            # Skip directories matching exclude patterns
            if any(part in exclude_directories for part in path_parts):
                return True
            
            # Skip files with certain patterns in the name only if in test directories
            file_name_lower = file_path.name.lower()
            skip_patterns = ['test', 'tests', 'spec', 'specs', 'mock', 'mocks', 'fixture', 'fixtures']
            test_directories = ['test', 'tests', 'spec', 'specs', '__tests__', 'e2e']
            
            # Only skip test files if they're in dedicated test directories
            for pattern in skip_patterns:
                if pattern in file_name_lower and any(test_dir in path_parts for test_dir in test_directories):
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
