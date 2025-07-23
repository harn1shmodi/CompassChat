from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, JSON, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Session
from sqlalchemy import create_engine
from datetime import datetime, timedelta
import hashlib
import secrets
import os
import logging

logger = logging.getLogger(__name__)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=True)  # Made nullable for OAuth users
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # OAuth fields
    oauth_provider = Column(String(50), nullable=True)  # 'google', 'github', etc.
    oauth_provider_id = Column(String(100), nullable=True)  # Provider's user ID
    display_name = Column(String(100), nullable=True)  # Full name from OAuth
    avatar_url = Column(String(500), nullable=True)  # Profile picture URL
    
    # Relationships
    sessions = relationship("UserSession", back_populates="user")
    repository_analyses = relationship("UserRepositoryAnalysis", back_populates="user")

class UserSession(Base):
    __tablename__ = "user_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_token = Column(String(255), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    user = relationship("User", back_populates="sessions")

class RepositoryCache(Base):
    __tablename__ = "repository_cache"
    
    id = Column(Integer, primary_key=True, index=True)
    repo_url = Column(String(500), unique=True, index=True, nullable=False)
    repo_name = Column(String(200), nullable=False)  # "owner/name" format
    last_commit_hash = Column(String(40), nullable=True)  # Git commit hash for cache invalidation
    analysis_completed_at = Column(DateTime, nullable=False)
    total_files = Column(Integer, default=0)
    total_chunks = Column(Integer, default=0)
    total_functions = Column(Integer, default=0)
    total_classes = Column(Integer, default=0)
    repo_metadata = Column(JSON, nullable=True)  # Store additional repository metadata
    is_public = Column(Boolean, default=True)  # Whether this repo can be shared across users
    
    # Relationships
    user_analyses = relationship("UserRepositoryAnalysis", back_populates="repository_cache")

class UserRepositoryAnalysis(Base):
    __tablename__ = "user_repository_analyses"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    repository_cache_id = Column(Integer, ForeignKey("repository_cache.id"), nullable=False)
    access_granted_at = Column(DateTime, default=datetime.utcnow)
    last_accessed_at = Column(DateTime, default=datetime.utcnow)
    chat_history_count = Column(Integer, default=0)
    
    # Relationships
    user = relationship("User", back_populates="repository_analyses")
    repository_cache = relationship("RepositoryCache", back_populates="user_analyses")

# Database utility functions
class DatabaseManager:
    def __init__(self, database_url: str = None):
        if not database_url:
            # Import here to avoid circular imports
            from core.config import settings
            database_url = settings.database_url
        
        logger.info(f"Initializing database with URL type: {'PostgreSQL' if database_url.startswith('postgresql://') else 'SQLite'}")
        
        # Handle missing psycopg2 gracefully
        if database_url.startswith("postgresql://"):
            try:
                import psycopg2
                logger.info("psycopg2 module available")
            except ImportError:
                logger.error("psycopg2 not installed but PostgreSQL URL provided. Falling back to SQLite.")
                database_url = "sqlite:///./compasschat.db"
        
        # Enhanced connection handling for Supabase
        connect_args = {}
        if database_url.startswith("postgresql://"):
            connect_args = {
                "sslmode": "require",
                "connect_timeout": 30,
                # Force IPv4 to avoid IPv6 routing issues
                "options": "-c default_transaction_isolation=read_committed"
            }
            logger.info("Attempting PostgreSQL connection with SSL required")
        
        try:
            # Try connecting with pool settings for better reliability
            if database_url.startswith("postgresql://"):
                self.engine = create_engine(
                    database_url, 
                    connect_args=connect_args,
                    pool_pre_ping=True,
                    pool_recycle=300,
                    echo=False  # Set to True for SQL debugging
                )
            else:
                self.engine = create_engine(database_url)
            
            # Create tables and test connection
            Base.metadata.create_all(bind=self.engine)
            
            # Simple connection test without raw SQL
            with self.engine.connect() as conn:
                pass  # Just test that we can connect
            
            logger.info(f"✅ Database connected successfully to: {database_url.split('@')[0] if '@' in database_url else 'SQLite'}@***")
            
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            # Enhanced fallback to SQLite if PostgreSQL fails
            if database_url.startswith("postgresql://"):
                logger.warning("🔄 PostgreSQL connection failed, falling back to SQLite database")
                logger.warning("⚠️  Note: Data will not persist between deployments with SQLite")
                try:
                    self.engine = create_engine("sqlite:///./compasschat.db")
                    Base.metadata.create_all(bind=self.engine)
                    logger.info("✅ SQLite fallback successful")
                except Exception as sqlite_error:
                    logger.error(f"❌ SQLite fallback also failed: {sqlite_error}")
                    raise
            else:
                raise
    
    def get_session(self) -> Session:
        from sqlalchemy.orm import sessionmaker
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        return SessionLocal()
    
    def create_user(self, username: str, email: str, password: str) -> User:
        """Create a new user with hashed password"""
        session = self.get_session()
        try:
            # Check if user already exists
            existing_user = session.query(User).filter(
                (User.username == username) | (User.email == email)
            ).first()
            
            if existing_user:
                raise ValueError("User with this username or email already exists")
            
            # Hash password
            hashed_password = hashlib.sha256(password.encode()).hexdigest()
            
            # Create user
            user = User(
                username=username,
                email=email,
                hashed_password=hashed_password
            )
            
            session.add(user)
            session.commit()
            session.refresh(user)
            return user
        finally:
            session.close()
    
    def authenticate_user(self, username: str, password: str) -> User:
        """Authenticate user and return user object if valid"""
        session = self.get_session()
        try:
            hashed_password = hashlib.sha256(password.encode()).hexdigest()
            user = session.query(User).filter(
                User.username == username,
                User.hashed_password == hashed_password,
                User.is_active == True
            ).first()
            return user
        finally:
            session.close()
    
    def create_session(self, user_id: int) -> str:
        """Create a new session for user and return session token"""
        session = self.get_session()
        try:
            # Generate session token
            session_token = secrets.token_urlsafe(32)
            expires_at = datetime.utcnow() + timedelta(days=30)  # 30 day expiry
            
            # Mark old sessions for deactivation after grace period (prevents race conditions)
            # Instead of immediate deactivation, set expiry to 30 seconds from now
            grace_period_expiry = datetime.utcnow() + timedelta(seconds=30)
            session.query(UserSession).filter(
                UserSession.user_id == user_id,
                UserSession.is_active == True
            ).update({"expires_at": grace_period_expiry})
            
            # Create new session
            user_session = UserSession(
                user_id=user_id,
                session_token=session_token,
                expires_at=expires_at
            )
            
            session.add(user_session)
            session.commit()
            return session_token
        finally:
            session.close()
    
    def get_user_from_session(self, session_token: str) -> User:
        """Get user from valid session token"""
        session = self.get_session()
        try:
            user_session = session.query(UserSession).filter(
                UserSession.session_token == session_token,
                UserSession.is_active == True,
                UserSession.expires_at > datetime.utcnow()
            ).first()
            
            if user_session:
                # Auto-extend session if within 7 days of expiry (use total_seconds for precision)
                time_until_expiry = (user_session.expires_at - datetime.utcnow()).total_seconds()
                days_until_expiry = time_until_expiry / 86400  # 24 * 60 * 60 seconds per day
                
                if days_until_expiry <= 7:
                    user_session.expires_at = datetime.utcnow() + timedelta(days=30)
                    session.commit()
                    logger.info(f"Auto-extended session for user {user_session.user.username}, {days_until_expiry:.2f} days remaining")
                
                return user_session.user
            return None
        finally:
            session.close()
    
    def cleanup_expired_sessions(self):
        """Clean up truly expired sessions (called periodically)"""
        session = self.get_session()
        try:
            expired_count = session.query(UserSession).filter(
                UserSession.expires_at < datetime.utcnow()
            ).delete()
            session.commit()
            if expired_count > 0:
                logger.info(f"Cleaned up {expired_count} expired sessions")
        finally:
            session.close()
    
    def deactivate_session(self, session_token: str):
        """Deactivate a specific session"""
        session = self.get_session()
        try:
            user_session = session.query(UserSession).filter(
                UserSession.session_token == session_token,
                UserSession.is_active == True
            ).first()
            
            if user_session:
                user_session.is_active = False
                session.commit()
        finally:
            session.close()
    
    def get_or_create_repository_cache(self, repo_url: str, repo_name: str, 
                                     commit_hash: str = None, is_public: bool = True) -> RepositoryCache:
        """Get existing repository cache or create new one"""
        session = self.get_session()
        try:
            repo_cache = session.query(RepositoryCache).filter(
                RepositoryCache.repo_url == repo_url
            ).first()
            
            if repo_cache:
                # Check if cache is still valid (commit hash matches)
                if commit_hash and repo_cache.last_commit_hash != commit_hash:
                    # Cache is outdated, update it
                    repo_cache.last_commit_hash = commit_hash
                    repo_cache.analysis_completed_at = datetime.utcnow()
                    session.commit()
                return repo_cache
            else:
                # Create new cache entry
                repo_cache = RepositoryCache(
                    repo_url=repo_url,
                    repo_name=repo_name,
                    last_commit_hash=commit_hash,
                    analysis_completed_at=datetime.utcnow(),
                    is_public=is_public
                )
                session.add(repo_cache)
                session.commit()
                session.refresh(repo_cache)
                return repo_cache
        finally:
            session.close()
    
    def grant_user_access_to_repository(self, user_id: int, repository_cache_id: int):
        """Grant user access to a repository analysis"""
        session = self.get_session()
        try:
            # Check if access already exists
            existing_access = session.query(UserRepositoryAnalysis).filter(
                UserRepositoryAnalysis.user_id == user_id,
                UserRepositoryAnalysis.repository_cache_id == repository_cache_id
            ).first()
            
            if existing_access:
                # Update last accessed time
                existing_access.last_accessed_at = datetime.utcnow()
                session.commit()
                return existing_access
            else:
                # Create new access
                user_analysis = UserRepositoryAnalysis(
                    user_id=user_id,
                    repository_cache_id=repository_cache_id
                )
                session.add(user_analysis)
                session.commit()
                session.refresh(user_analysis)
                return user_analysis
        finally:
            session.close()
    
    def get_user_repositories(self, user_id: int):
        """Get all repositories that user has access to"""
        session = self.get_session()
        try:
            user_repos = session.query(UserRepositoryAnalysis).filter(
                UserRepositoryAnalysis.user_id == user_id
            ).order_by(UserRepositoryAnalysis.last_accessed_at.desc()).all()
            
            return [
                {
                    "id": ur.repository_cache.id,
                    "repo_name": ur.repository_cache.repo_name,
                    "repo_url": ur.repository_cache.repo_url,
                    "last_analyzed": ur.repository_cache.analysis_completed_at,
                    "last_accessed": ur.last_accessed_at,
                    "total_files": ur.repository_cache.total_files,
                    "total_chunks": ur.repository_cache.total_chunks,
                    "chat_count": ur.chat_history_count
                }
                for ur in user_repos
            ]
        finally:
            session.close()
    
    def create_oauth_user(self, username: str, email: str, provider: str, 
                         provider_id: str, display_name: str = None, 
                         avatar_url: str = None) -> User:
        """Create a new OAuth user"""
        session = self.get_session()
        try:
            # Check if user already exists
            existing_user = session.query(User).filter(
                (User.username == username) | (User.email == email)
            ).first()
            
            if existing_user:
                raise ValueError("User with this username or email already exists")
            
            # Create OAuth user (no password)
            user = User(
                username=username,
                email=email,
                oauth_provider=provider,
                oauth_provider_id=provider_id,
                display_name=display_name,
                avatar_url=avatar_url,
                hashed_password=None  # OAuth users don't need passwords
            )
            
            session.add(user)
            session.commit()
            session.refresh(user)
            return user
        finally:
            session.close()
    
    def get_user_by_email(self, email: str) -> User:
        """Get user by email address"""
        session = self.get_session()
        try:
            user = session.query(User).filter(
                User.email == email,
                User.is_active == True
            ).first()
            return user
        finally:
            session.close()
    
    def update_user_oauth_info(self, user_id: int, provider: str = None, 
                              provider_id: str = None, avatar_url: str = None,
                              display_name: str = None):
        """Update user's OAuth information"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if user:
                if provider:
                    user.oauth_provider = provider
                if provider_id:
                    user.oauth_provider_id = provider_id
                if avatar_url:
                    user.avatar_url = avatar_url
                if display_name:
                    user.display_name = display_name
                session.commit()
        finally:
            session.close()

# Global database manager instance
db_manager = DatabaseManager()
