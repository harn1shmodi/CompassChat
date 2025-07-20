"""
Advanced repository optimization utilities for CompassChat
Implements git-filter-repo and other advanced filtering techniques
"""

import subprocess
import shutil
import os
from pathlib import Path
from typing import List, Set, Dict, Any
import logging
import tempfile

logger = logging.getLogger(__name__)


class RepositoryOptimizer:
    """Advanced repository optimization using git-filter-repo and other techniques"""
    
    def __init__(self):
        self.code_extensions = self._get_code_extensions()
        self.exclude_directories = self._get_exclude_directories()
        self.force_include_files = self._get_force_include_files()
    
    def _get_code_extensions(self) -> Set[str]:
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
    
    def _get_exclude_directories(self) -> Set[str]:
        """Get directories to exclude"""
        return {
            'node_modules', 'vendor', '.pnpm', 'bower_components', 'jspm_packages',
            'web_modules', 'dist', 'build', 'out', 'output', 'target', 'bin', 'obj',
            'lib', '_build', '.next', '.nuxt', '.output', '.svelte-kit', '.parcel-cache',
            '__pycache__', '.pytest_cache', '.tox', 'htmlcov', '.coverage',
            '*.egg-info', '.mypy_cache', '.ruff_cache', '.idea', '.vscode', '.vs',
            'docs/_build', 'site', '_site', '.docusaurus', 'assets/images',
            'assets/videos', 'public/images', 'static/img', 'media', 'logs', 'tmp',
            'temp', 'coverage', '.nyc_output', 'test-results', '.env', '.venv',
            'venv', 'env', 'virtualenv', 'Pods', 'DerivedData', 'packages',
            'PublishProfiles', '.terraform', '.docker'
        }
    
    def _get_force_include_files(self) -> Set[str]:
        """Get essential files to always include"""
        return {
            'README.md', 'LICENSE', 'package.json', 'requirements.txt', 'Gemfile',
            'go.mod', 'Cargo.toml', 'build.gradle', 'pom.xml', 'CMakeLists.txt',
            'Makefile', 'Dockerfile', 'docker-compose.yml', '.gitignore',
            'setup.py', 'pyproject.toml', 'tsconfig.json', '.eslintrc.js',
            '.eslintrc.json', '.prettierrc', '.prettierrc.json'
        }
    
    def install_git_filter_repo(self) -> bool:
        """Install git-filter-repo if not available"""
        try:
            # Check if already installed
            subprocess.run(['git-filter-repo', '--version'], 
                         capture_output=True, check=True)
            logger.info("git-filter-repo is already installed")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        
        try:
            # Try to install via pip
            subprocess.run(['pip', 'install', 'git-filter-repo'], 
                         check=True, capture_output=True)
            logger.info("git-filter-repo installed successfully")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install git-filter-repo: {e}")
            return False
    
    def filter_repository_advanced(self, repo_path: str, target_path: str = None) -> bool:
        """
        Apply advanced filtering using git-filter-repo to keep only code files
        WARNING: This rewrites Git history
        """
        if not self.install_git_filter_repo():
            logger.warning("git-filter-repo not available, skipping advanced filtering")
            return False
        
        try:
            original_dir = os.getcwd()
            repo_path = Path(repo_path).resolve()
            
            if target_path:
                target_path = Path(target_path).resolve()
                # Copy repo to target location first
                shutil.copytree(repo_path, target_path)
                os.chdir(target_path)
            else:
                os.chdir(repo_path)
            
            logger.info("Applying advanced git-filter-repo filtering...")
            
            # Build filter arguments for code files
            filter_args = ['git-filter-repo']
            
            # Include code file extensions
            for ext in self.code_extensions:
                filter_args.extend(['--path-glob', f'*{ext}'])
            
            # Include essential files
            for filename in self.force_include_files:
                filter_args.extend(['--path', filename])
            
            # Include common source directories
            common_dirs = [
                'src/', 'source/', 'lib/', 'app/', 'apps/', 'packages/',
                'core/', 'components/', 'modules/', 'services/', 'api/',
                'server/', 'client/', 'frontend/', 'backend/', 'cmd/',
                'internal/', 'pkg/', 'scripts/', 'tools/', 'utils/',
                'helpers/', 'config/', '.github/'
            ]
            
            for dir_path in common_dirs:
                filter_args.extend(['--path', dir_path])
            
            # Exclude large directories
            for exclude_dir in self.exclude_directories:
                filter_args.extend(['--path-glob', f'!{exclude_dir}/'])
            
            # Exclude binary files
            binary_patterns = [
                '!*.jpg', '!*.jpeg', '!*.png', '!*.gif', '!*.mp4', '!*.zip',
                '!*.pdf', '!*.exe', '!*.dll', '!*.so', '!*.dylib', '!*.jar',
                '!*.war', '!*.class', '!*.pyc', '!*.db', '!*.sqlite'
            ]
            
            for pattern in binary_patterns:
                filter_args.extend(['--path-glob', pattern])
            
            # Strip large blobs
            filter_args.extend(['--strip-blobs-bigger-than', '10M'])
            
            # Force processing
            filter_args.append('--force')
            
            # Execute git-filter-repo
            result = subprocess.run(filter_args, capture_output=True, text=True, check=True)
            
            logger.info("Advanced filtering completed successfully")
            logger.debug(f"git-filter-repo output: {result.stdout}")
            
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"git-filter-repo failed: {e}")
            logger.error(f"Error output: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Error in advanced filtering: {e}")
            return False
        finally:
            try:
                os.chdir(original_dir)
            except:
                pass
    
    def estimate_size_reduction(self, total_repo_size_mb: float) -> Dict[str, Any]:
        """Estimate size reduction based on typical repository composition"""
        # Based on analysis of common repositories:
        # - node_modules alone often accounts for 40-60% of repo size
        # - Build outputs add another 10-20%
        # - Media files can be 10-30%
        # - Actual code is typically only 10-30% of total size
        
        estimated_code_percentage = 0.20  # Conservative estimate
        estimated_final_size_mb = total_repo_size_mb * estimated_code_percentage
        
        return {
            'original_size_mb': total_repo_size_mb,
            'estimated_final_size_mb': round(estimated_final_size_mb, 2),
            'reduction_percentage': round((1 - estimated_code_percentage) * 100, 1),
            'size_saved_mb': round(total_repo_size_mb * (1 - estimated_code_percentage), 2)
        }
    
    def create_gitattributes_file(self, repo_path: str):
        """Create .gitattributes file for handling large files"""
        gitattributes_path = Path(repo_path) / '.gitattributes'
        
        try:
            with open(gitattributes_path, 'w') as f:
                f.write("# Auto-generated .gitattributes for CompassChat optimization\n\n")
                
                # Mark large files as binary to prevent diff generation
                binary_patterns = [
                    '*.zip', '*.tar', '*.gz', '*.jpg', '*.jpeg', '*.png', '*.gif',
                    '*.mp4', '*.avi', '*.mov', '*.pdf', '*.exe', '*.dll', '*.so',
                    '*.dylib', '*.jar', '*.war', '*.class', '*.db', '*.sqlite'
                ]
                
                for pattern in binary_patterns:
                    f.write(f"{pattern} binary\n")
                
                f.write("\n# Ensure text files are properly handled\n")
                
                # Ensure text files are properly handled
                for ext in self.code_extensions:
                    f.write(f"*{ext} text\n")
            
            logger.info(f"Created .gitattributes file at {gitattributes_path}")
            
        except Exception as e:
            logger.error(f"Failed to create .gitattributes file: {e}")
    
    def get_rsync_exclude_args(self) -> List[str]:
        """Generate rsync exclude arguments for copying repos"""
        excludes = []
        for dir_pattern in self.exclude_directories:
            excludes.extend(['--exclude', dir_pattern])
        
        # Add file patterns
        exclude_patterns = [
            '*.zip', '*.tar', '*.gz', '*.jpg', '*.jpeg', '*.png', '*.gif',
            '*.mp4', '*.pdf', '*.exe', '*.dll', '*.jar', '*.class', '*.pyc'
        ]
        
        for pattern in exclude_patterns:
            excludes.extend(['--exclude', pattern])
        
        return excludes
    
    def should_include_file(self, file_path: Path) -> bool:
        """Check if a file should be included based on optimization rules"""
        try:
            # Check if in excluded directory
            for part in file_path.parts:
                if part in self.exclude_directories:
                    return False
            
            # Check if it's a force-include file
            if file_path.name in self.force_include_files:
                return True
            
            # Check extension
            return file_path.suffix.lower() in self.code_extensions
            
        except Exception:
            return False
    
    def filter_directory_simple(self, source_dir: str, target_dir: str):
        """Simple directory filtering without Git history rewriting"""
        source = Path(source_dir)
        target = Path(target_dir)
        
        try:
            target.mkdir(parents=True, exist_ok=True)
            
            for file_path in source.rglob('*'):
                if file_path.is_file() and self.should_include_file(file_path):
                    try:
                        relative_path = file_path.relative_to(source)
                        target_path = target / relative_path
                        
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(file_path, target_path)
                        
                    except Exception as e:
                        logger.warning(f"Failed to copy file {file_path}: {e}")
            
            logger.info(f"Simple filtering completed: {source_dir} -> {target_dir}")
            
        except Exception as e:
            logger.error(f"Error in simple directory filtering: {e}")
            raise


# Global instance
repo_optimizer = RepositoryOptimizer()
