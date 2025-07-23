from fastapi import APIRouter, HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from core.database import db_manager, User
from services.oauth_service import oauth_service
from typing import Optional
import logging
import urllib.parse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer()

class UserRegistration(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    created_at: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    oauth_provider: Optional[str] = None

class LoginResponse(BaseModel):
    user: UserResponse
    session_token: str
    message: str

class OAuthCallbackRequest(BaseModel):
    provider: str
    code: str
    state: Optional[str] = None

class GitCompassTokenRequest(BaseModel):
    token: str

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    """Dependency to get current user from session token"""
    try:
        session_token = credentials.credentials
        user = db_manager.get_user_from_session(session_token)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return user
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )

@router.post("/register", response_model=LoginResponse)
async def register_user(user_data: UserRegistration):
    """Register a new user"""
    try:
        # Validate input
        if len(user_data.password) < 6:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 6 characters long"
            )
        
        if len(user_data.username) < 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username must be at least 3 characters long"
            )
        
        # Create user
        user = db_manager.create_user(
            username=user_data.username,
            email=user_data.email,
            password=user_data.password
        )
        
        # Create session
        session_token = db_manager.create_session(user.id)
        
        return LoginResponse(
            user=UserResponse(
                id=user.id,
                username=user.username,
                email=user.email,
                created_at=user.created_at.isoformat(),
                display_name=user.display_name,
                avatar_url=user.avatar_url,
                oauth_provider=user.oauth_provider
            ),
            session_token=session_token,
            message="User registered successfully"
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )

@router.post("/login", response_model=LoginResponse)
async def login_user(login_data: UserLogin):
    """Login user and create session"""
    try:
        # Authenticate user
        user = db_manager.authenticate_user(login_data.username, login_data.password)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )
        
        # Create session
        session_token = db_manager.create_session(user.id)
        
        return LoginResponse(
            user=UserResponse(
                id=user.id,
                username=user.username,
                email=user.email,
                created_at=user.created_at.isoformat(),
                display_name=user.display_name,
                avatar_url=user.avatar_url,
                oauth_provider=user.oauth_provider
            ),
            session_token=session_token,
            message="Login successful"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information"""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        created_at=current_user.created_at.isoformat(),
        display_name=current_user.display_name,
        avatar_url=current_user.avatar_url,
        oauth_provider=current_user.oauth_provider
    )

@router.post("/refresh", response_model=LoginResponse)
async def refresh_session(current_user: User = Depends(get_current_user)):
    """Refresh user session token"""
    try:
        # Create new session
        session_token = db_manager.create_session(current_user.id)
        
        return LoginResponse(
            user=UserResponse(
                id=current_user.id,
                username=current_user.username,
                email=current_user.email,
                created_at=current_user.created_at.isoformat(),
                display_name=current_user.display_name,
                avatar_url=current_user.avatar_url,
                oauth_provider=current_user.oauth_provider
            ),
            session_token=session_token,
            message="Session refreshed successfully"
        )
        
    except Exception as e:
        logger.error(f"Session refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session refresh failed"
        )

@router.post("/logout")
async def logout_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Logout user (deactivate session)"""
    try:
        session_token = credentials.credentials
        db_manager.deactivate_session(session_token)
        return {"message": "Logout successful"}
        
    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )

@router.get("/repositories")
async def get_user_repositories(current_user: User = Depends(get_current_user)):
    """Get repositories that the user has access to"""
    try:
        repositories = db_manager.get_user_repositories(current_user.id)
        return {
            "repositories": repositories,
            "total": len(repositories)
        }
        
    except Exception as e:
        logger.error(f"Error fetching user repositories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch repositories"
        )

# OAuth Endpoints

@router.get("/oauth/config")
async def get_oauth_config():
    """Get available OAuth providers configuration"""
    from core.config import settings
    
    return {
        "google_available": bool(settings.google_client_id and settings.google_client_secret),
        "github_available": bool(settings.github_client_id and settings.github_client_secret),
        "gitcompass_available": True  # Always available for GitCompass integration
    }

@router.get("/oauth/{provider}")
async def oauth_login(provider: str, request: Request):
    """Initiate OAuth login with provider (google/github)"""
    try:
        from core.config import settings
        
        if provider not in ["google", "github"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported OAuth provider"
            )
        
        # Build redirect URI
        base_url = str(request.base_url).rstrip('/')
        redirect_uri = f"{base_url}/api/auth/oauth/{provider}/callback"
        
        if provider == "google":
            client_id = settings.google_client_id
            scope = "openid email profile"
            auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id={client_id}&redirect_uri={urllib.parse.quote(redirect_uri)}&scope={urllib.parse.quote(scope)}"
        
        elif provider == "github":
            client_id = settings.github_client_id
            scope = "user:email"
            auth_url = f"https://github.com/login/oauth/authorize?client_id={client_id}&redirect_uri={urllib.parse.quote(redirect_uri)}&scope={urllib.parse.quote(scope)}"
        
        return {"auth_url": auth_url}
        
    except Exception as e:
        logger.error(f"OAuth initiation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate OAuth"
        )

@router.get("/oauth/{provider}/callback")
async def oauth_callback(provider: str, code: str, request: Request):
    """Handle OAuth callback"""
    try:
        # Build redirect URI (must match the one used in auth initiation)
        base_url = str(request.base_url).rstrip('/')
        redirect_uri = f"{base_url}/api/auth/oauth/{provider}/callback"
        
        # Exchange code for user data
        oauth_data = await oauth_service.exchange_oauth_code(provider, code, redirect_uri)
        
        if not oauth_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to exchange OAuth code"
            )
        
        # Get or create user
        user = await oauth_service.get_or_create_oauth_user(oauth_data)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user account"
            )
        
        # Create session
        session_token = db_manager.create_session(user.id)
        
        # Redirect to frontend with token
        frontend_url = "https://chat.gitcompass.com" if "gitcompass.com" in str(request.base_url) else "http://localhost:5173"
        
        return RedirectResponse(
            url=f"{frontend_url}?token={session_token}&provider={provider}",
            status_code=302
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth authentication failed"
        )

@router.post("/oauth/callback", response_model=LoginResponse)
async def oauth_callback_post(callback_data: OAuthCallbackRequest, request: Request):
    """Handle OAuth callback via POST (for frontend integration)"""
    try:
        # Build redirect URI
        base_url = str(request.base_url).rstrip('/')
        redirect_uri = f"{base_url}/api/auth/oauth/{callback_data.provider}/callback"
        
        # Exchange code for user data
        oauth_data = await oauth_service.exchange_oauth_code(
            callback_data.provider, 
            callback_data.code, 
            redirect_uri
        )
        
        if not oauth_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to exchange OAuth code"
            )
        
        # Get or create user
        user = await oauth_service.get_or_create_oauth_user(oauth_data)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user account"
            )
        
        # Create session
        session_token = db_manager.create_session(user.id)
        
        return LoginResponse(
            user=UserResponse(
                id=user.id,
                username=user.username,
                email=user.email,
                created_at=user.created_at.isoformat(),
                display_name=user.display_name,
                avatar_url=user.avatar_url,
                oauth_provider=user.oauth_provider
            ),
            session_token=session_token,
            message=f"Successfully authenticated with {callback_data.provider}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth authentication failed"
        )

@router.post("/gitcompass/validate", response_model=LoginResponse)
async def validate_gitcompass_token(token_request: GitCompassTokenRequest):
    """Validate token from GitCompass main product"""
    try:
        # Validate token with GitCompass or decode JWT
        token_data = await oauth_service.validate_gitcompass_token(token_request.token)
        
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired GitCompass token"
            )
        
        # Extract user data from token
        email = token_data.get("email")
        username = token_data.get("username") or token_data.get("login") or email.split("@")[0]
        
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token missing required user information"
            )
        
        # Get or create user
        user = db_manager.get_user_by_email(email)
        
        if not user:
            # Create new user from GitCompass token
            user = db_manager.create_oauth_user(
                username=username,
                email=email,
                provider="gitcompass",
                provider_id=str(token_data.get("user_id", "")),
                display_name=token_data.get("name"),
                avatar_url=token_data.get("avatar_url")
            )
        
        # Create CompassChat session
        session_token = db_manager.create_session(user.id)
        
        return LoginResponse(
            user=UserResponse(
                id=user.id,
                username=user.username,
                email=user.email,
                created_at=user.created_at.isoformat(),
                display_name=user.display_name,
                avatar_url=user.avatar_url,
                oauth_provider=user.oauth_provider
            ),
            session_token=session_token,
            message="Successfully authenticated from GitCompass"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GitCompass token validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token validation failed"
        )
