# FastAPI Integration Guide for GitCompass

## 🚀 Quick Setup

### 1. Install Dependencies
```bash
pip install PyJWT==2.8.0 python-multipart
```

### 2. Environment Variables
Add to your GitCompass `.env`:
```bash
# CRITICAL: Use the same secret as CompassChat!
JWT_SECRET_KEY=your_shared_secret_key_change_in_production
```

### 3. Add Endpoints to Your GitCompass FastAPI App

Copy the code from `gitcompass_fastapi_endpoints.py` and adapt these parts:

#### Replace `get_current_user` function:
```python
# Replace this with your existing authentication
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    # Your existing user authentication logic
    # Should return user object with: id, username, email, name, avatar_url
    pass
```

#### For session-based auth, modify the `/auth/compasschat` endpoint:
```python
@app.get("/auth/compasschat")
async def compasschat_auth(request: Request, redirect: Optional[str] = None):
    # Replace this part with your session checking logic:
    user_id = request.session.get("user_id")  # Your session structure
    if not user_id:
        login_url = f"/login?redirect={request.url}"
        return RedirectResponse(url=login_url, status_code=302)
    
    user = await get_user_by_id(user_id)  # Your user lookup
    # ... rest stays the same
```

## 🎯 Frontend Integration

### Add to your GitCompass frontend templates/components:

#### 1. Chat with Code Button (Any Page)
```javascript
// Add this JavaScript function
async function openCompassChat(repoUrl = null) {
  try {
    const response = await fetch('/api/compasschat/token', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${getAuthToken()}`, // Your auth method
        'Content-Type': 'application/json'
      }
    });
    
    const { token } = await response.json();
    
    let url = `https://chat.gitcompass.com?token=${token}`;
    if (repoUrl) {
      url += `&repo=${encodeURIComponent(repoUrl)}`;
    }
    
    window.open(url, '_blank');
  } catch (error) {
    console.error('Failed to open CompassChat:', error);
    alert('Failed to open CompassChat. Please try again.');
  }
}

// Add this helper function for your auth token
function getAuthToken() {
  // Replace with your auth token retrieval method
  return localStorage.getItem('auth_token') || sessionStorage.getItem('token');
}
```

#### 2. Repository Page Buttons
```html
<!-- Add to repository page template -->
<div class="repository-actions">
  <button class="btn btn-star">⭐ Star</button>
  <button class="btn btn-fork">🍴 Fork</button>
  <button class="btn btn-primary" onclick="openCompassChat('{{ repository.clone_url }}')">
    💬 Chat with Code
  </button>
</div>
```

#### 3. Repository List Integration
```html
<!-- Add to repository list items -->
<div class="repo-item">
  <h3>{{ repo.name }}</h3>
  <p>{{ repo.description }}</p>
  <div class="repo-actions">
    <a href="/{{ repo.full_name }}">View</a>
    <button onclick="openCompassChat('{{ repo.clone_url }}')">💬 Chat</button>
  </div>
</div>
```

#### 4. Navigation Menu
```html
<!-- Add to main navigation -->
<nav>
  <a href="/repositories">Repositories</a>
  <a href="/projects">Projects</a>
  <a href="/settings">Settings</a>
  <button onclick="openCompassChat()" class="nav-btn">💬 AI Chat</button>
</nav>
```

#### 5. Dashboard Widget
```html
<!-- Add to dashboard -->
<div class="dashboard-widget">
  <h3>AI Code Assistant</h3>
  <p>Chat with your repositories using AI</p>
  <button onclick="openCompassChat()" class="btn btn-primary">
    Launch CompassChat
  </button>
</div>
```

## 🔧 Testing

### 1. Test Token Generation
```bash
curl -X POST "https://gitcompass.com/api/compasschat/token" \
  -H "Authorization: Bearer YOUR_GITCOMPASS_TOKEN" \
  -H "Content-Type: application/json"
```

Expected response:
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### 2. Test Auth Redirect
Visit in browser:
```
https://gitcompass.com/auth/compasschat?redirect=https://chat.gitcompass.com
```

Should redirect to CompassChat with token parameter.

### 3. Test Complete Flow
1. Click "Continue with GitCompass" on CompassChat
2. Should redirect to GitCompass auth endpoint
3. Should redirect back to CompassChat with token
4. Should automatically log into CompassChat

## 🛠️ Customization

### For Different User Models
```python
# Adapt the JWT payload to your user model
payload = {
    "user_id": current_user.id,
    "username": current_user.username or current_user.login,
    "email": current_user.email,
    "name": current_user.display_name or current_user.full_name,
    "avatar_url": current_user.profile_picture or current_user.avatar,
    # Add any other fields CompassChat needs
    "exp": datetime.utcnow() + timedelta(minutes=30),
    "iat": datetime.utcnow(),
    "iss": "gitcompass"
}
```

### For Different Auth Systems
```python
# Cookie-based auth
@app.get("/auth/compasschat")
async def compasschat_auth(request: Request, redirect: Optional[str] = None):
    user_token = request.cookies.get("auth_token")
    if not user_token:
        return RedirectResponse(url="/login", status_code=302)
    
    user = validate_token_and_get_user(user_token)
    # ... generate JWT and redirect

# Header-based auth
@app.get("/auth/compasschat")
async def compasschat_auth(request: Request, redirect: Optional[str] = None):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    
    token = auth_header.split(" ")[1]
    user = validate_token_and_get_user(token)
    # ... generate JWT and redirect
```

## 🎉 Result

After adding these endpoints:

✅ **JWT Token Generation**: `/api/compasschat/token` endpoint for programmatic access  
✅ **Auth Redirect Handler**: `/auth/compasschat` endpoint for "Continue with GitCompass" button  
✅ **Frontend Integration**: JavaScript functions and buttons ready to use  
✅ **Seamless Flow**: Users go from GitCompass → CompassChat without re-authentication  

**Total time to implement: ~30 minutes** ⚡
