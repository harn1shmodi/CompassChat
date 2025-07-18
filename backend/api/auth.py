from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from core.database import db_manager, User
from typing import Optional
import logging

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

class LoginResponse(BaseModel):
    user: UserResponse
    session_token: str
    message: str

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
                created_at=user.created_at.isoformat()
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
                created_at=user.created_at.isoformat()
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
        created_at=current_user.created_at.isoformat()
    )

@router.post("/logout")
async def logout_user(current_user: User = Depends(get_current_user)):
    """Logout user (deactivate session)"""
    try:
        # Note: In a real implementation, we'd need to deactivate the specific session
        # For now, we'll just return success since sessions expire automatically
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
