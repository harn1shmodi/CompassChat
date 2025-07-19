import git
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pathlib import Path
import logging
import re

logger = logging.getLogger(__name__)


class GitAnalysisService:
    """Service for analyzing Git commits and changes"""
    
    def __init__(self):
        self.repo = None
        self.repo_path = None
    
    def analyze_repository(self, repo_path: str) -> Dict[str, Any]:
        """Analyze a Git repository and return comprehensive information"""
        try:
            self.repo_path = Path(repo_path)
            self.repo = git.Repo(repo_path)
            
            return {
                "repository_info": self._get_repository_info(),
                "branch_info": self._get_branch_info(),
                "commit_stats": self._get_commit_stats(),
                "tags": self._get_tags(),
                "contributors": self._get_contributors()
            }
        except Exception as e:
            logger.error(f"Error analyzing repository: {e}")
            return {}
    
    def get_commits_since(self, 
                         repo_path: str, 
                         since_commit: Optional[str] = None, 
                         since_date: Optional[datetime] = None,
                         branch: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get commits since a specific commit or date"""
        try:
            self.repo_path = Path(repo_path)
            self.repo = git.Repo(repo_path)
            
            # Auto-detect the main branch if not specified
            if not branch:
                # Check for common main branch names
                for branch_name in ['main', 'master', 'develop']:
                    try:
                        if branch_name in [b.name for b in self.repo.branches]:
                            branch = branch_name
                            break
                    except:
                        continue
                
                # Fallback to first available branch or HEAD
                if not branch:
                    branches = list(self.repo.branches)
                    if branches:
                        branch = branches[0].name
                    else:
                        branch = "HEAD"
            
            # Determine the range for commits
            if since_commit:
                # Get commits since a specific commit
                commit_range = f"{since_commit}..{branch}"
            elif since_date:
                # Get commits since a specific date
                commit_range = f"--since={since_date.isoformat()}"
            else:
                # Get last 50 commits as fallback
                commit_range = f"-50"
            
            commits = []
            
            # Get commits using git log
            if since_commit:
                log_commits = list(self.repo.iter_commits(commit_range))
            else:
                log_commits = list(self.repo.iter_commits(branch, max_count=50))
                if since_date:
                    # Ensure timezone compatibility
                    if since_date.tzinfo is None:
                        since_date = since_date.replace(tzinfo=timezone.utc)
                    log_commits = [c for c in log_commits if c.committed_datetime >= since_date]
            
            for commit in log_commits:
                commit_info = self._analyze_commit(commit)
                commits.append(commit_info)
            
            return commits
        except Exception as e:
            logger.error(f"Error getting commits: {e}")
            return []
    
    def _analyze_commit(self, commit: git.Commit) -> Dict[str, Any]:
        """Analyze a single commit and extract relevant information"""
        try:
            # Get commit files and changes
            files_changed = self._get_commit_files(commit)
            
            # Categorize the commit
            commit_type = self._categorize_commit(commit.message, files_changed)
            
            # Extract breaking changes
            breaking_changes = self._extract_breaking_changes(commit.message, files_changed)
            
            return {
                "sha": commit.hexsha,
                "short_sha": commit.hexsha[:7],
                "message": commit.message.strip(),
                "summary": commit.summary,
                "author": {
                    "name": commit.author.name,
                    "email": commit.author.email
                },
                "date": commit.committed_datetime.isoformat(),
                "files_changed": files_changed,
                "stats": {
                    "insertions": commit.stats.total["insertions"],
                    "deletions": commit.stats.total["deletions"],
                    "files": commit.stats.total["files"]
                },
                "type": commit_type,
                "breaking_changes": breaking_changes,
                "scope": self._extract_scope(commit.message),
                "description": self._extract_description(commit.message)
            }
        except Exception as e:
            logger.error(f"Error analyzing commit {commit.hexsha}: {e}")
            return {
                "sha": commit.hexsha,
                "short_sha": commit.hexsha[:7],
                "message": commit.message.strip(),
                "error": str(e)
            }
    
    def _get_commit_files(self, commit: git.Commit) -> List[Dict[str, Any]]:
        """Get files changed in a commit"""
        try:
            if not commit.parents:
                # Initial commit
                return []
            
            # Compare with first parent
            diff = commit.parents[0].diff(commit)
            files = []
            
            for diff_item in diff:
                file_info = {
                    "path": diff_item.a_path or diff_item.b_path,
                    "change_type": diff_item.change_type,
                    "insertions": 0,
                    "deletions": 0
                }
                
                # Get line changes if available
                if hasattr(diff_item, 'diff'):
                    try:
                        diff_text = diff_item.diff.decode('utf-8', errors='ignore')
                        file_info["insertions"] = diff_text.count('\n+')
                        file_info["deletions"] = diff_text.count('\n-')
                    except:
                        pass
                
                files.append(file_info)
            
            return files
        except Exception as e:
            logger.error(f"Error getting commit files: {e}")
            return []
    
    def _categorize_commit(self, message: str, files_changed: List[Dict]) -> str:
        """Categorize commit type based on message and files changed"""
        message_lower = message.lower()
        
        # Check for conventional commit patterns
        conventional_patterns = {
            'feat': ['feat:', 'feature:'],
            'fix': ['fix:', 'bug:', 'bugfix:'],
            'docs': ['docs:', 'doc:', 'documentation:'],
            'style': ['style:', 'format:', 'formatting:'],
            'refactor': ['refactor:', 'refactoring:'],
            'test': ['test:', 'tests:', 'testing:'],
            'chore': ['chore:', 'maintenance:', 'cleanup:'],
            'ci': ['ci:', 'build:', 'deploy:'],
            'perf': ['perf:', 'performance:', 'optimize:']
        }
        
        for commit_type, patterns in conventional_patterns.items():
            if any(pattern in message_lower for pattern in patterns):
                return commit_type
        
        # Fallback categorization based on content
        if any(keyword in message_lower for keyword in ['add', 'new', 'create', 'implement']):
            return 'feat'
        elif any(keyword in message_lower for keyword in ['fix', 'bug', 'issue', 'error']):
            return 'fix'
        elif any(keyword in message_lower for keyword in ['update', 'change', 'modify']):
            return 'update'
        elif any(keyword in message_lower for keyword in ['remove', 'delete', 'deprecate']):
            return 'remove'
        elif any(keyword in message_lower for keyword in ['test', 'spec']):
            return 'test'
        elif any(keyword in message_lower for keyword in ['doc', 'readme', 'comment']):
            return 'docs'
        else:
            return 'other'
    
    def _extract_breaking_changes(self, message: str, files_changed: List[Dict]) -> List[str]:
        """Extract breaking changes from commit message and file changes"""
        breaking_changes = []
        
        # Check for breaking change indicators in message
        message_lower = message.lower()
        breaking_keywords = [
            'breaking change', 'breaking:', 'break:', 'bc:', 'major:',
            'incompatible', 'removes', 'deprecates', 'migration required'
        ]
        
        if any(keyword in message_lower for keyword in breaking_keywords):
            breaking_changes.append("Breaking change indicated in commit message")
        
        # Check for potential breaking changes in files
        api_files = [f for f in files_changed if 'api' in f['path'].lower() or 'interface' in f['path'].lower()]
        if api_files:
            breaking_changes.append("API or interface files modified")
        
        # Check for version bumps that might indicate breaking changes
        version_files = [f for f in files_changed if any(name in f['path'].lower() for name in ['package.json', 'setup.py', 'cargo.toml', 'pom.xml'])]
        if version_files:
            breaking_changes.append("Version files modified - check for major version bump")
        
        return breaking_changes
    
    def _extract_scope(self, message: str) -> Optional[str]:
        """Extract scope from conventional commit message"""
        # Match pattern like "feat(scope): description"
        match = re.search(r'^\w+\(([^)]+)\):', message)
        return match.group(1) if match else None
    
    def _extract_description(self, message: str) -> str:
        """Extract description from commit message"""
        # Remove conventional commit prefix if present
        clean_message = re.sub(r'^\w+(\([^)]+\))?:\s*', '', message)
        
        # Get first line as description
        description = clean_message.split('\n')[0].strip()
        
        return description
    
    def _get_repository_info(self) -> Dict[str, Any]:
        """Get basic repository information"""
        try:
            return {
                "name": self.repo_path.name,
                "path": str(self.repo_path),
                "is_bare": self.repo.bare,
                "head_commit": self.repo.head.commit.hexsha,
                "active_branch": self.repo.active_branch.name if self.repo.active_branch else None,
                "remote_url": self.repo.remotes.origin.url if self.repo.remotes else None
            }
        except Exception as e:
            logger.error(f"Error getting repository info: {e}")
            return {}
    
    def _get_branch_info(self) -> List[Dict[str, Any]]:
        """Get information about repository branches"""
        try:
            branches = []
            for branch in self.repo.branches:
                branches.append({
                    "name": branch.name,
                    "commit": branch.commit.hexsha,
                    "is_active": branch == self.repo.active_branch
                })
            return branches
        except Exception as e:
            logger.error(f"Error getting branch info: {e}")
            return []
    
    def _get_commit_stats(self) -> Dict[str, Any]:
        """Get commit statistics"""
        try:
            commits = list(self.repo.iter_commits(max_count=1000))
            return {
                "total_commits": len(commits),
                "latest_commit": commits[0].hexsha if commits else None,
                "oldest_commit": commits[-1].hexsha if commits else None
            }
        except Exception as e:
            logger.error(f"Error getting commit stats: {e}")
            return {}
    
    def _get_tags(self) -> List[Dict[str, Any]]:
        """Get repository tags"""
        try:
            tags = []
            for tag in self.repo.tags:
                tags.append({
                    "name": tag.name,
                    "commit": tag.commit.hexsha,
                    "date": tag.commit.committed_datetime.isoformat()
                })
            return sorted(tags, key=lambda x: x['date'], reverse=True)
        except Exception as e:
            logger.error(f"Error getting tags: {e}")
            return []
    
    def _get_contributors(self) -> List[Dict[str, Any]]:
        """Get repository contributors"""
        try:
            contributors = {}
            for commit in self.repo.iter_commits(max_count=1000):
                email = commit.author.email
                if email not in contributors:
                    contributors[email] = {
                        "name": commit.author.name,
                        "email": email,
                        "commits": 0,
                        "first_commit": commit.committed_datetime.isoformat(),
                        "last_commit": commit.committed_datetime.isoformat()
                    }
                
                contributors[email]["commits"] += 1
                
                # Update first/last commit dates
                commit_date = commit.committed_datetime.isoformat()
                if commit_date < contributors[email]["first_commit"]:
                    contributors[email]["first_commit"] = commit_date
                if commit_date > contributors[email]["last_commit"]:
                    contributors[email]["last_commit"] = commit_date
            
            return sorted(contributors.values(), key=lambda x: x['commits'], reverse=True)
        except Exception as e:
            logger.error(f"Error getting contributors: {e}")
            return []

    def get_latest_tag(self, repo_path: str) -> Optional[str]:
        """Get the latest tag in the repository"""
        try:
            self.repo_path = Path(repo_path)
            self.repo = git.Repo(repo_path)
            
            tags = self._get_tags()
            return tags[0]['name'] if tags else None
        except Exception as e:
            logger.error(f"Error getting latest tag: {e}")
            return None

    def get_previous_tag(self, repo_path: str) -> Optional[str]:
        """Get the previous tag before the latest"""
        try:
            self.repo_path = Path(repo_path)
            self.repo = git.Repo(repo_path)
            
            tags = self._get_tags()
            return tags[1]['name'] if len(tags) > 1 else None
        except Exception as e:
            logger.error(f"Error getting previous tag: {e}")
            return None

    def get_all_tags(self, repo_path: str) -> List[Dict[str, Any]]:
        """Get all tags in the repository"""
        try:
            self.repo_path = Path(repo_path)
            self.repo = git.Repo(repo_path)
            
            return self._get_tags()
        except Exception as e:
            logger.error(f"Error getting all tags: {e}")
            return []

    def get_current_branch(self, repo_path: str) -> Optional[str]:
        """Get the current branch name"""
        try:
            self.repo_path = Path(repo_path)
            self.repo = git.Repo(repo_path)
            
            return self.repo.active_branch.name if self.repo.active_branch else None
        except Exception as e:
            logger.error(f"Error getting current branch: {e}")
            return None

    def get_main_branch(self, repo_path: str) -> str:
        """Get the main branch name (main or master)"""
        try:
            self.repo_path = Path(repo_path)
            self.repo = git.Repo(repo_path)
            
            # Check for common main branch names
            for branch_name in ['main', 'master', 'develop']:
                try:
                    if branch_name in [b.name for b in self.repo.branches]:
                        return branch_name
                except:
                    continue
            
            # Fallback to first branch
            branches = list(self.repo.branches)
            return branches[0].name if branches else 'main'
        except Exception as e:
            logger.error(f"Error getting main branch: {e}")
            return 'main'

    def get_commits_in_range(self, repo_path: str, comparison_range: str) -> List[Dict[str, Any]]:
        """Get commits in a specific range (e.g., 'v1.0.0..HEAD' or 'main..feature-branch')"""
        try:
            self.repo_path = Path(repo_path)
            self.repo = git.Repo(repo_path)
            
            commits = []
            
            # Validate the range before using it
            if '..' in comparison_range:
                # Range comparison (from..to)
                from_ref, to_ref = comparison_range.split('..', 1)
                
                # Validate references exist
                if not self._validate_reference_exists(from_ref):
                    logger.warning(f"Reference '{from_ref}' does not exist, falling back to recent commits")
                    return self.get_commits_since(repo_path, since_commit=None)
                
                if to_ref != 'HEAD' and not self._validate_reference_exists(to_ref):
                    logger.warning(f"Reference '{to_ref}' does not exist, using HEAD instead")
                    comparison_range = f"{from_ref}..HEAD"
                
                log_commits = list(self.repo.iter_commits(comparison_range))
            else:
                # Single reference - get commits since that reference
                if not self._validate_reference_exists(comparison_range):
                    logger.warning(f"Reference '{comparison_range}' does not exist, falling back to recent commits")
                    return self.get_commits_since(repo_path, since_commit=None)
                
                log_commits = list(self.repo.iter_commits(f"{comparison_range}..HEAD"))
            
            for commit in log_commits:
                commit_info = self._analyze_commit(commit)
                commits.append(commit_info)
            
            return commits
        except Exception as e:
            logger.error(f"Error getting commits in range {comparison_range}: {e}")
            # Fallback to recent commits
            return self.get_commits_since(repo_path, since_commit=None)

    def detect_comparison_range(self, repo_path: str) -> Dict[str, Any]:
        """Auto-detect the best comparison range for changelog generation"""
        try:
            self.repo_path = Path(repo_path)
            self.repo = git.Repo(repo_path)
            
            latest_tag = self.get_latest_tag(repo_path)
            previous_tag = self.get_previous_tag(repo_path)
            current_branch = self.get_current_branch(repo_path)
            main_branch = self.get_main_branch(repo_path)
            
            # Determine the best default comparison
            if latest_tag:
                # Most common: since last tag
                recommended_range = f"{latest_tag}..HEAD"
                recommended_type = "since_tag"
            elif current_branch and current_branch != main_branch:
                # On a feature branch - compare to main
                recommended_range = f"{main_branch}..{current_branch}"
                recommended_type = "branch_comparison"
            else:
                # Fallback to last 20 commits
                recommended_range = "HEAD~20..HEAD"
                recommended_type = "commit_count"
            
            return {
                "recommended_range": recommended_range,
                "recommended_type": recommended_type,
                "available_options": {
                    "since_latest_tag": f"{latest_tag}..HEAD" if latest_tag else None,
                    "between_tags": f"{previous_tag}..{latest_tag}" if previous_tag and latest_tag else None,
                    "current_branch_to_main": f"{main_branch}..{current_branch}" if current_branch != main_branch else None,
                    "main_to_current_branch": f"{current_branch}..{main_branch}" if current_branch != main_branch else None,
                    "last_20_commits": "HEAD~20..HEAD",
                    "last_50_commits": "HEAD~50..HEAD"
                },
                "repository_info": {
                    "latest_tag": latest_tag,
                    "previous_tag": previous_tag,
                    "current_branch": current_branch,
                    "main_branch": main_branch,
                    "total_tags": len(self._get_tags()),
                    "total_branches": len(list(self.repo.branches))
                }
            }
        except Exception as e:
            logger.error(f"Error detecting comparison range: {e}")
            return {
                "recommended_range": "HEAD~20..HEAD",
                "recommended_type": "commit_count",
                "available_options": {},
                "repository_info": {}
            }
    
    def get_commits_between_tags(self, repo_path: str, from_tag: str, to_tag: str = None) -> List[Dict[str, Any]]:
        """Get commits between two tags"""
        try:
            self.repo_path = Path(repo_path)
            self.repo = git.Repo(repo_path)
            
            # Validate that the tag exists
            if not self._validate_tag_exists(from_tag):
                logger.warning(f"Tag '{from_tag}' does not exist, trying with 'v' prefix")
                if not from_tag.startswith('v'):
                    from_tag = f"v{from_tag}"
                    if not self._validate_tag_exists(from_tag):
                        logger.error(f"Tag '{from_tag}' does not exist, falling back to commit count")
                        return self.get_commits_since(repo_path, since_commit=None)
            
            if to_tag:
                if not self._validate_tag_exists(to_tag):
                    logger.warning(f"Tag '{to_tag}' does not exist, using HEAD instead")
                    to_tag = "HEAD"
                commit_range = f"{from_tag}..{to_tag}"
            else:
                commit_range = f"{from_tag}..HEAD"
            
            commits = []
            for commit in self.repo.iter_commits(commit_range):
                commit_info = self._analyze_commit(commit)
                commits.append(commit_info)
            
            return commits
        except Exception as e:
            logger.error(f"Error getting commits between tags: {e}")
            # Fallback to recent commits if tag-based comparison fails
            return self.get_commits_since(repo_path, since_commit=None)
    
    def _validate_tag_exists(self, tag: str) -> bool:
        """Validate that a tag exists in the repository"""
        try:
            if not self.repo:
                return False
            
            # Check if tag exists in repository
            for repo_tag in self.repo.tags:
                if repo_tag.name == tag:
                    return True
            
            return False
        except Exception as e:
            logger.error(f"Error validating tag {tag}: {e}")
            return False
    
    def _validate_reference_exists(self, ref: str) -> bool:
        """Validate that a reference (tag, branch, or commit) exists in the repository"""
        try:
            if not self.repo:
                return False
            
            # Special case for HEAD
            if ref == 'HEAD':
                return True
            
            # Check if it's a tag
            if self._validate_tag_exists(ref):
                return True
            
            # Check if it's a branch
            try:
                for branch in self.repo.branches:
                    if branch.name == ref:
                        return True
            except:
                pass
            
            # Check if it's a commit hash
            try:
                self.repo.commit(ref)
                return True
            except:
                pass
            
            return False
        except Exception as e:
            logger.error(f"Error validating reference {ref}: {e}")
            return False