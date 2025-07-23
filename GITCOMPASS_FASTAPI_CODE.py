# FastAPI Code for GitCompass Integration

## Add these endpoints to your GitCompass FastAPI backend:

```python
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from datetime import datetime, timedelta
import os
from typing import Optional

app = FastAPI()
security = HTTPBearer()

# Configuration - add to your .env
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your_shared_secret_key_change_in_production")
JWT_ALGORITHM = "HS256"

# Your existing user authentication dependency
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Your existing user authentication logic"""
    # Replace this with your actual user authentication
    # This should return your User object
    pass

# 1. JWT Token Generation Endpoint
@app.post("/api/compasschat/token")
async def generate_compasschat_token(current_user = Depends(get_current_user)):
    """Generate JWT token for CompassChat authentication"""
    try:
        # Generate JWT payload
        payload = {
            "user_id": current_user.id,
            "username": current_user.username,
            "email": current_user.email,
            "name": getattr(current_user, 'name', '') or getattr(current_user, 'display_name', ''),
            "avatar_url": getattr(current_user, 'avatar_url', ''),
            "exp": datetime.utcnow() + timedelta(minutes=30),  # 30 minutes
            "iat": datetime.utcnow(),
            "iss": "gitcompass"
        }
        
        # Generate JWT token
        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        
        return {"token": token}
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate CompassChat token"
        )

# 2. CompassChat Authentication Redirect Endpoint
@app.get("/auth/compasschat")
async def compasschat_auth(request: Request, redirect: Optional[str] = None):
    """Handle 'Continue with GitCompass' button from CompassChat"""
    try:
        # Check if user is authenticated
        # You'll need to adapt this to your authentication method
        
        # Option A: If you have session-based auth
        user_id = request.session.get("user_id")  # Adapt to your session structure
        if not user_id:
            # Redirect to login with return URL
            login_url = f"/login?redirect={request.url}"
            return RedirectResponse(url=login_url, status_code=302)
        
        # Get user (adapt to your user model)
        user = await get_user_by_id(user_id)  # Your user lookup function
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        # Generate JWT token
        payload = {
            "user_id": user.id,
            "username": user.username,
            "email": user.email,
            "name": getattr(user, 'name', '') or getattr(user, 'display_name', ''),
            "avatar_url": getattr(user, 'avatar_url', ''),
            "exp": datetime.utcnow() + timedelta(minutes=30),
            "iat": datetime.utcnow(),
            "iss": "gitcompass"
        }
        
        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        
        # Default redirect URL
        redirect_url = redirect or "https://chat.gitcompass.com"
        
        # Redirect back to CompassChat with token
        return RedirectResponse(
            url=f"{redirect_url}?token={token}",
            status_code=302
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Authentication failed: {str(e)}"
        )

# Alternative version if you use JWT-based authentication in GitCompass
@app.get("/auth/compasschat")
async def compasschat_auth_jwt_version(request: Request, redirect: Optional[str] = None, current_user = Depends(get_current_user)):
    """Handle 'Continue with GitCompass' button - JWT auth version"""
    try:
        # User is already authenticated via get_current_user dependency
        
        # Generate JWT token for CompassChat
        payload = {
            "user_id": current_user.id,
            "username": current_user.username,
            "email": current_user.email,
            "name": getattr(current_user, 'name', '') or getattr(current_user, 'display_name', ''),
            "avatar_url": getattr(current_user, 'avatar_url', ''),
            "exp": datetime.utcnow() + timedelta(minutes=30),
            "iat": datetime.utcnow(),
            "iss": "gitcompass"
        }
        
        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        
        # Default redirect URL
        redirect_url = redirect or "https://chat.gitcompass.com"
        
        # Redirect back to CompassChat with token
        return RedirectResponse(
            url=f"{redirect_url}?token={token}",
            status_code=302
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Authentication failed: {str(e)}"
        )

# Helper function - adapt to your user model
async def get_user_by_id(user_id: int):
    """Get user by ID - replace with your actual user lookup"""
    # Example - adapt to your database/ORM
    # return db.query(User).filter(User.id == user_id).first()
    pass

# Frontend JavaScript to use these endpoints
"""
// Add this to your GitCompass frontend

// 1. For programmatic token generation
async function getCompassChatToken() {
  try {
    const response = await fetch('/api/compasschat/token', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('auth_token')}`, // Your auth method
        'Content-Type': 'application/json'
      }
    });
    
    const data = await response.json();
    return data.token;
  } catch (error) {
    console.error('Failed to get CompassChat token:', error);
    return null;
  }
}

// 2. For "Chat with Code" buttons
async function openCompassChat(repoUrl = null) {
  try {
    const token = await getCompassChatToken();
    if (!token) return;
    
    let url = `https://chat.gitcompass.com?token=${token}`;
    if (repoUrl) {
      url += `&repo=${encodeURIComponent(repoUrl)}`;
    }
    
    window.open(url, '_blank');
  } catch (error) {
    console.error('Failed to open CompassChat:', error);
  }
}

// 3. Add buttons anywhere in your GitCompass UI
// <button onclick="openCompassChat()">💬 Chat with Code</button>
// <button onclick="openCompassChat('https://github.com/user/repo.git')">💬 Chat with This Repo</button>
"""
```

## Installation Requirements

Add these to your GitCompass requirements.txt:
```bash
PyJWT==2.8.0
python-multipart
```

## Environment Variables

Add to your GitCompass .env file:
```bash
# Same secret as CompassChat - VERY IMPORTANT!
JWT_SECRET_KEY=your_shared_secret_key_change_in_production
```

## Usage Examples

### Repository Page Integration
```python
# Add to your repository page template/endpoint
@app.get("/repository/{repo_id}")
async def repository_page(repo_id: int, current_user = Depends(get_current_user)):
    repo = await get_repository(repo_id)
    
    # Include CompassChat integration in your template context
    return {
        "repository": repo,
        "compasschat_available": True,
        "repo_clone_url": repo.clone_url
    }
```

### Dashboard Widget
```python
@app.get("/dashboard")
async def dashboard(current_user = Depends(get_current_user)):
    return {
        "user": current_user,
        "recent_repos": await get_user_recent_repos(current_user.id),
        "compasschat_token_endpoint": "/api/compasschat/token"
    }
```

## Testing

Test the endpoints:
```bash
# 1. Test token generation
curl -X POST "https://gitcompass.com/api/compasschat/token" \
  -H "Authorization: Bearer YOUR_GITCOMPASS_TOKEN"

# 2. Test auth redirect
# Visit: https://gitcompass.com/auth/compasschat?redirect=https://chat.gitcompass.com
```
