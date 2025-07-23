# Quick Implementation Guide for GitCompass

## 🎯 **What You Need to Add to GitCompass**

The JWT integration requires **minimal changes** to your GitCompass codebase:

### ✅ **1. Environment Configuration**
Add to your GitCompass `.env` file:
```bash
JWT_SECRET_KEY=your_shared_secret_key_change_in_production
```
*Use the same secret in both GitCompass and CompassChat*

### ✅ **2. Backend Implementation**

Choose your framework:

#### **Node.js/Express**
```javascript
// Install: npm install jsonwebtoken
const jwt = require('jsonwebtoken');

// Add this endpoint
app.post('/api/compasschat/token', authenticateUser, (req, res) => {
  const token = jwt.sign({
    user_id: req.user.id,
    username: req.user.username,
    email: req.user.email,
    name: req.user.name,
    avatar_url: req.user.avatar_url,
    exp: Math.floor(Date.now() / 1000) + (30 * 60),
    iat: Math.floor(Date.now() / 1000),
    iss: 'gitcompass'
  }, process.env.JWT_SECRET_KEY, { algorithm: 'HS256' });
  
  res.json({ token });
});
```

#### **Python/Django**
```python
# Install: pip install PyJWT
import jwt
from datetime import datetime, timedelta
from django.http import JsonResponse

def compasschat_token(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    payload = {
        'user_id': request.user.id,
        'username': request.user.username,
        'email': request.user.email,
        'name': request.user.get_full_name(),
        'avatar_url': request.user.profile.avatar_url if hasattr(request.user, 'profile') else '',
        'exp': datetime.utcnow() + timedelta(minutes=30),
        'iat': datetime.utcnow(),
        'iss': 'gitcompass'
    }
    
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm='HS256')
    return JsonResponse({'token': token})
```

#### **PHP/Laravel**
```php
// Install: composer require firebase/php-jwt
use Firebase\JWT\JWT;
use Firebase\JWT\Key;

Route::post('/api/compasschat/token', function (Request $request) {
    $user = Auth::user();
    if (!$user) {
        return response()->json(['error' => 'Unauthorized'], 401);
    }
    
    $payload = [
        'user_id' => $user->id,
        'username' => $user->username,
        'email' => $user->email,
        'name' => $user->name,
        'avatar_url' => $user->avatar_url ?? '',
        'exp' => time() + (30 * 60),
        'iat' => time(),
        'iss' => 'gitcompass'
    ];
    
    $token = JWT::encode($payload, env('JWT_SECRET_KEY'), 'HS256');
    return response()->json(['token' => $token]);
});
```

#### **Ruby/Rails**
```ruby
# Add to Gemfile: gem 'jwt'
def compasschat_token
  return render json: { error: 'Unauthorized' }, status: 401 unless current_user
  
  payload = {
    user_id: current_user.id,
    username: current_user.username,
    email: current_user.email,
    name: current_user.name,
    avatar_url: current_user.avatar_url || '',
    exp: 30.minutes.from_now.to_i,
    iat: Time.now.to_i,
    iss: 'gitcompass'
  }
  
  token = JWT.encode(payload, ENV['JWT_SECRET_KEY'], 'HS256')
  render json: { token: token }
end
```

### ✅ **3. Frontend Implementation**

Add "Chat with Code" buttons anywhere in your GitCompass UI:

#### **React/Vue/Modern JS**
```javascript
// Component for any page
function ChatWithCodeButton({ repository = null }) {
  const openCompassChat = async () => {
    try {
      const response = await fetch('/api/compasschat/token', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
          'Content-Type': 'application/json'
        }
      });
      
      const { token } = await response.json();
      
      const params = new URLSearchParams({ token });
      if (repository) {
        params.append('repo', repository.clone_url);
      }
      
      window.open(`https://chat.gitcompass.com?${params}`, '_blank');
    } catch (error) {
      console.error('Failed to open CompassChat:', error);
    }
  };

  return (
    <button onClick={openCompassChat} className="btn btn-primary">
      💬 Chat with Code
    </button>
  );
}
```

#### **Plain HTML/JavaScript**
```html
<!-- Add anywhere in your HTML -->
<button onclick="openCompassChat()" class="btn btn-primary">
  💬 Chat with Code
</button>

<script>
async function openCompassChat(repoUrl = null) {
  try {
    const response = await fetch('/api/compasschat/token', {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer ' + getAuthToken(), // Your auth method
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
  }
}
</script>
```

#### **jQuery**
```javascript
$('.chat-with-code-btn').click(function() {
  const repoUrl = $(this).data('repo-url');
  
  $.post('/api/compasschat/token', {
    _token: $('meta[name="csrf-token"]').attr('content') // CSRF if needed
  })
  .done(function(data) {
    let url = `https://chat.gitcompass.com?token=${data.token}`;
    if (repoUrl) {
      url += `&repo=${encodeURIComponent(repoUrl)}`;
    }
    window.open(url, '_blank');
  })
  .fail(function() {
    alert('Failed to open CompassChat');
  });
});
```

### ✅ **4. Where to Add Buttons**

Add "Chat with Code" buttons in these GitCompass locations:

1. **Repository pages** - Next to Star/Fork buttons
2. **Repository lists** - In action menus
3. **Main navigation** - Global "AI Chat" link
4. **Dashboard** - Quick access widget
5. **Project pages** - Context-specific chat

### ✅ **5. Testing**

Test the integration:
```bash
# 1. Test token generation
curl -X POST https://gitcompass.com/api/compasschat/token \
  -H "Authorization: Bearer YOUR_AUTH_TOKEN"

# 2. Test CompassChat with token
# Visit: https://chat.gitcompass.com?token=GENERATED_TOKEN

# 3. Verify user is logged in automatically
```

## 🚀 **Implementation Levels**

### **Minimal (5 minutes)**
Just add the backend endpoint and one button:
```javascript
// One line in your GitCompass
<button onclick="window.open('https://chat.gitcompass.com?token=' + await getCompassChatToken())">
  💬 Chat
</button>
```

### **Standard (30 minutes)**
- Backend endpoint
- Buttons on repository pages
- Error handling

### **Full Integration (2 hours)**
- Backend endpoint
- Multiple UI integration points
- Repository context passing
- User experience polish

## 🎯 **Result**

Users click "Chat with Code" in GitCompass → Instantly logged into CompassChat!

**No re-authentication, no OAuth setup needed** - just JWT token exchange! 🎉
