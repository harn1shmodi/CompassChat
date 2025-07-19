from typing import Optional, Dict, Any, List
from core.database import db_manager, RepositoryCache, User
from services.graph_service import GraphService
import logging
import hashlib
import json

logger = logging.getLogger(__name__)

class CacheService:
    """Service for managing repository analysis caching"""
    
    def __init__(self):
        self.graph_service = GraphService()
    
    def get_cache_key(self, repo_url: str, commit_hash: str = None) -> str:
        """Generate cache key for repository"""
        cache_data = f"{repo_url}:{commit_hash or 'latest'}"
        return hashlib.md5(cache_data.encode()).hexdigest()
    
    def is_repository_cached(self, repo_url: str, commit_hash: str = None) -> bool:
        """Check if repository analysis is cached and valid"""
        try:
            print(f"Checking cache for repository: {repo_url} (commit: {commit_hash})")
            repo_cache = db_manager.get_or_create_repository_cache(
                repo_url=repo_url,
                repo_name=self._extract_repo_name(repo_url),
                commit_hash=commit_hash,
                is_public=True
            )
            print(f"Cache entry: {repo_cache}")
            
            # Check if analysis exists in Neo4j
            if self.graph_service.repository_exists(repo_cache.repo_name):
                # Verify cache is not stale
                if commit_hash and repo_cache.last_commit_hash == commit_hash:
                    return True
                elif not commit_hash:  # No commit hash provided, assume valid
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking repository cache: {e}")
            return False
    
    def get_cached_repository_stats(self, repo_url: str) -> Optional[Dict[str, Any]]:
        """Get cached repository statistics"""
        try:
            repo_cache = db_manager.get_or_create_repository_cache(
                repo_url=repo_url,
                repo_name=self._extract_repo_name(repo_url)
            )
            
            return {
                "total_files": repo_cache.total_files,
                "total_chunks": repo_cache.total_chunks,
                "total_functions": repo_cache.total_functions,
                "total_classes": repo_cache.total_classes,
                "last_analyzed": repo_cache.analysis_completed_at.isoformat(),
                "metadata": repo_cache.repo_metadata or {}
            }
            
        except Exception as e:
            logger.error(f"Error getting cached repository stats: {e}")
            return None
    
    def update_repository_cache(self, repo_url: str, repo_name: str, 
                              commit_hash: str = None, stats: Dict[str, Any] = None):
        """Update repository cache with analysis results"""
        try:
            repo_cache = db_manager.get_or_create_repository_cache(
                repo_url=repo_url,
                repo_name=repo_name,
                commit_hash=commit_hash,
                is_public=True
            )
            
            if stats:
                repo_cache.total_files = stats.get("files", 0)  # Fixed key mapping
                repo_cache.total_chunks = stats.get("chunks", 0)  # Fixed key mapping
                repo_cache.total_functions = stats.get("functions", 0)  # Fixed key mapping
                repo_cache.total_classes = stats.get("classes", 0)  # Fixed key mapping
                repo_cache.repo_metadata = stats.get("metadata", {})
            
            # Update in database
            session = db_manager.get_session()
            try:
                session.merge(repo_cache)
                session.commit()
                logger.info(f"Updated cache for repository: {repo_name}")
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"Error updating repository cache: {e}")
    
    def grant_user_access(self, user: User, repo_url: str) -> bool:
        """Grant user access to a cached repository"""
        try:
            repo_cache = db_manager.get_or_create_repository_cache(
                repo_url=repo_url,
                repo_name=self._extract_repo_name(repo_url)
            )
            
            db_manager.grant_user_access_to_repository(user.id, repo_cache.id)
            logger.info(f"Granted user {user.username} access to repository: {repo_cache.repo_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error granting user access: {e}")
            return False
    
    def invalidate_repository_cache(self, repo_url: str):
        """Invalidate repository cache (for when repo is updated)"""
        try:
            # Clear from Neo4j
            repo_name = self._extract_repo_name(repo_url)
            self.graph_service.clear_repository(repo_name)
            
            # Update database cache status
            session = db_manager.get_session()
            try:
                repo_cache = session.query(RepositoryCache).filter(
                    RepositoryCache.repo_url == repo_url
                ).first()
                
                if repo_cache:
                    # Reset stats to indicate re-analysis needed
                    repo_cache.total_files = 0
                    repo_cache.total_chunks = 0
                    repo_cache.total_functions = 0
                    repo_cache.total_classes = 0
                    repo_cache.last_commit_hash = None
                    session.commit()
                    
                logger.info(f"Invalidated cache for repository: {repo_name}")
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"Error invalidating repository cache: {e}")
    
    def get_popular_repositories(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most popular repositories (most accessed)"""
        try:
            session = db_manager.get_session()
            try:
                # Query repositories with user access count
                popular_repos = session.query(RepositoryCache).join(
                    RepositoryCache.user_analyses
                ).filter(
                    RepositoryCache.is_public == True,
                    RepositoryCache.total_chunks > 0  # Only fully analyzed repos
                ).order_by(
                    RepositoryCache.analysis_completed_at.desc()
                ).limit(limit).all()
                
                return [
                    {
                        "repo_name": repo.repo_name,
                        "repo_url": repo.repo_url,
                        "last_analyzed": repo.analysis_completed_at.isoformat(),
                        "total_files": repo.total_files,
                        "total_chunks": repo.total_chunks,
                        "user_count": len(repo.user_analyses)
                    }
                    for repo in popular_repos
                ]
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"Error getting popular repositories: {e}")
            return []
    
    def get_user_repositories(self, user: User) -> List[Dict[str, Any]]:
        """Get repositories accessible to a specific user"""
        try:
            session = db_manager.get_session()
            try:
                # Query repositories the user has access to
                user_repos = session.query(RepositoryCache).join(
                    RepositoryCache.user_analyses
                ).filter(
                    RepositoryCache.user_analyses.any(user_id=user.id)
                ).order_by(
                    RepositoryCache.analysis_completed_at.desc()
                ).all()
                
                logger.info(f"Found {len(user_repos)} repositories for user {user.username}")
                for repo in user_repos:
                    logger.info(f"  - {repo.repo_name}: {repo.total_files} files, {repo.total_chunks} chunks")
                
                # If no user-specific repositories found, return empty list
                # This enforces user isolation - new users won't see existing repositories
                if not user_repos:
                    logger.info(f"No repositories found for user {user.username}")
                    return []
                
                return [
                    {
                        "id": str(repo.id),
                        "name": repo.repo_name,
                        "url": repo.repo_url,
                        "last_analyzed": repo.analysis_completed_at.isoformat() if repo.analysis_completed_at else "",
                        "total_files": repo.total_files,
                        "total_chunks": repo.total_chunks,
                        "total_functions": repo.total_functions,
                        "total_classes": repo.total_classes,
                        "status": "complete" if repo.total_chunks > 0 else "incomplete"
                    }
                    for repo in user_repos
                ]
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"Error getting user repositories: {e}")
            return []
    
    def _extract_repo_name(self, repo_url: str) -> str:
        """Extract repository name from URL (owner/name format)"""
        try:
            # Handle GitHub URLs
            if "github.com" in repo_url:
                parts = repo_url.rstrip("/").split("/")
                if len(parts) >= 2:
                    return f"{parts[-2]}/{parts[-1].replace('.git', '')}"
            
            # Fallback: use last two parts of URL
            parts = repo_url.rstrip("/").replace(".git", "").split("/")
            if len(parts) >= 2:
                return f"{parts[-2]}/{parts[-1]}"
            
            return repo_url  # Fallback to full URL
            
        except Exception as e:
            logger.error(f"Error extracting repo name from URL {repo_url}: {e}")
            return repo_url

# Global cache service instance
cache_service = CacheService()
