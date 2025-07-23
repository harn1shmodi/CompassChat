# GitCompass Integration Guide: JWT Token Authentication

## How It's Implemented in CompassChat

CompassChat is already set up to accept JWT tokens from GitCompass in two ways:

### 🔄 **Flow Overview**
1. User is logged into GitCompass
2. User clicks "Chat with Code" button in GitCompass
3. GitCompass generates JWT token with user info
4. GitCompass redirects to: `https://chat.gitcompass.com?token=JWT_TOKEN_HERE`
5. CompassChat validates token and logs user in instantly

### ✅ **What's Already Built in CompassChat**

1. **JWT Token Validation** (`/api/auth/gitcompass/validate`)
2. **URL Parameter Handling** (Frontend automatically detects `?token=` in URL)
3. **User Account Creation/Linking** (Creates CompassChat account from JWT data)
4. **Session Management** (Issues CompassChat session after JWT validation)

## 🛠️ **What You Need to Add to GitCompass**

### Method 1: Shared JWT Secret (Recommended)

**Step 1: Set Same JWT Secret in Both Apps**
```bash
# In both GitCompass and CompassChat .env files:
JWT_SECRET_KEY=your_shared_secret_key_change_in_production
```

**Step 2: Add JWT Generation to GitCompass**

```javascript
// Add this to your GitCompass backend (Node.js/Express example)
const jwt = require('jsonwebtoken');

function generateCompassChatToken(user) {
  const payload = {
    user_id: user.id,
    username: user.username || user.login,
    email: user.email,
    name: user.name || user.display_name,
    avatar_url: user.avatar_url,
    exp: Math.floor(Date.now() / 1000) + (30 * 60), // 30 minutes
    iat: Math.floor(Date.now() / 1000),
    iss: 'gitcompass'
  };
  
  return jwt.sign(payload, process.env.JWT_SECRET_KEY, { algorithm: 'HS256' });
}

// API endpoint for generating tokens
app.post('/api/compasschat/token', authenticateUser, (req, res) => {
  try {
    const token = generateCompassChatToken(req.user);
    res.json({ token });
  } catch (error) {
    res.status(500).json({ error: 'Failed to generate token' });
  }
});
```

**Step 3: Add Frontend Integration to GitCompass**

```javascript
// Add "Chat with Code" button to your GitCompass frontend
function ChatWithCodeButton({ repository, user }) {
  const handleChatWithCode = async () => {
    try {
      // Get JWT token from your GitCompass backend
      const response = await fetch('/api/compasschat/token', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${user.accessToken}`,
          'Content-Type': 'application/json'
        }
      });
      
      const { token } = await response.json();
      
      // Redirect to CompassChat with token and optional repo
      const params = new URLSearchParams({
        token: token,
        ...(repository && { repo: repository.clone_url })
      });
      
      const compasschatUrl = `https://chat.gitcompass.com?${params.toString()}`;
      window.open(compasschatUrl, '_blank');
      
    } catch (error) {
      console.error('Failed to launch CompassChat:', error);
    }
  };

  return (
    <button 
      onClick={handleChatWithCode}
      className="btn btn-primary"
    >
      💬 Chat with Code
    </button>
  );
}
```

### Method 2: Token Validation API (Alternative)

If you prefer not to share JWT secrets, GitCompass can issue its own tokens and CompassChat will validate them via API:

**Step 1: Add Token Validation Endpoint to GitCompass**
```javascript
// Add to your GitCompass backend
app.post('/api/auth/validate', (req, res) => {
  try {
    const token = req.headers.authorization?.replace('Bearer ', '');
    const user = validateTokenAndGetUser(token); // Your existing validation
    
    if (user) {
      res.json({
        user_id: user.id,
        username: user.username,
        email: user.email,
        name: user.name,
        avatar_url: user.avatar_url
      });
    } else {
      res.status(401).json({ error: 'Invalid token' });
    }
  } catch (error) {
    res.status(401).json({ error: 'Token validation failed' });
  }
});
```

**Step 2: Configure CompassChat to Use GitCompass API**
```bash
# In CompassChat .env (remove JWT_SECRET_KEY to use API validation)
GITCOMPASS_BASE_URL=https://gitcompass.com
```

## 🎨 **Frontend Integration Examples**

### Repository Page Integration
```javascript
// Add to repository pages in GitCompass
function RepositoryActions({ repository, user }) {
  return (
    <div className="repository-actions">
      <button>⭐ Star</button>
      <button>🍴 Fork</button>
      <ChatWithCodeButton repository={repository} user={user} />
    </div>
  );
}
```

### Navigation Menu Integration
```javascript
// Add to main navigation in GitCompass
function NavigationMenu({ user }) {
  const handleOpenCompassChat = async () => {
    const response = await fetch('/api/compasschat/token', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${user.accessToken}` }
    });
    const { token } = await response.json();
    window.open(`https://chat.gitcompass.com?token=${token}`, '_blank');
  };

  return (
    <nav>
      <a href="/repositories">Repositories</a>
      <a href="/projects">Projects</a>
      <button onClick={handleOpenCompassChat}>💬 AI Chat</button>
    </nav>
  );
}
```

### Dashboard Widget
```javascript
// Add CompassChat widget to GitCompass dashboard
function CompassChatWidget({ user }) {
  return (
    <div className="dashboard-widget">
      <h3>AI Code Assistant</h3>
      <p>Chat with your repositories using AI</p>
      <ChatWithCodeButton user={user} />
    </div>
  );
}
```

## 🚀 **PHP/WordPress Integration**

If GitCompass is PHP-based:

```php
<?php
// Add JWT generation to your GitCompass PHP backend
require_once 'vendor/autoload.php';
use Firebase\JWT\JWT;
use Firebase\JWT\Key;

function generateCompassChatToken($user) {
    $payload = [
        'user_id' => $user['id'],
        'username' => $user['username'],
        'email' => $user['email'],
        'name' => $user['name'],
        'avatar_url' => $user['avatar_url'],
        'exp' => time() + (30 * 60), // 30 minutes
        'iat' => time(),
        'iss' => 'gitcompass'
    ];
    
    return JWT::encode($payload, $_ENV['JWT_SECRET_KEY'], 'HS256');
}

// API endpoint
add_action('wp_ajax_compasschat_token', function() {
    $user = wp_get_current_user();
    if (!$user->ID) {
        wp_die('Unauthorized', 401);
    }
    
    $token = generateCompassChatToken([
        'id' => $user->ID,
        'username' => $user->user_login,
        'email' => $user->user_email,
        'name' => $user->display_name,
        'avatar_url' => get_avatar_url($user->ID)
    ]);
    
    wp_send_json(['token' => $token]);
});
?>
```

## 🔒 **Security Considerations**

### JWT Secret Management
```bash
# Use strong, shared secret (same in both apps)
JWT_SECRET_KEY=$(openssl rand -base64 32)
```

### CORS Configuration
```bash
# In CompassChat, allow GitCompass origin
CORS_ORIGINS=["https://gitcompass.com", "https://chat.gitcompass.com"]
```

### Token Expiry
- Short-lived tokens (30 minutes recommended)
- CompassChat creates its own long-lived sessions after JWT validation

## 📋 **Implementation Checklist**

### GitCompass Changes:
- [ ] Add JWT library dependency
- [ ] Create token generation function
- [ ] Add `/api/compasschat/token` endpoint
- [ ] Add "Chat with Code" buttons to UI
- [ ] Set JWT_SECRET_KEY environment variable

### CompassChat Configuration:
- [ ] Set same JWT_SECRET_KEY
- [ ] Update CORS_ORIGINS to include GitCompass domain
- [ ] Deploy with JWT validation enabled

### Testing:
- [ ] Test token generation in GitCompass
- [ ] Test token validation in CompassChat
- [ ] Test complete user flow
- [ ] Verify session creation

## 🎯 **Minimal Implementation**

For quickest integration, just add this to any GitCompass page:

```html
<!-- Add anywhere in GitCompass -->
<script>
async function openCompassChat(repoUrl = null) {
  try {
    const response = await fetch('/api/compasschat/token', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + localStorage.getItem('userToken') }
    });
    const { token } = await response.json();
    
    const url = `https://chat.gitcompass.com?token=${token}` + 
                (repoUrl ? `&repo=${encodeURIComponent(repoUrl)}` : '');
    window.open(url, '_blank');
  } catch (error) {
    console.error('Failed to open CompassChat:', error);
  }
}
</script>

<button onclick="openCompassChat()">💬 Open CompassChat</button>
```

The integration is **seamless** - users go from GitCompass to CompassChat without any re-authentication! 🎉
