/**
 * GitCompass Integration Example
 * 
 * This is example code showing how to integrate CompassChat
 * authentication with your main GitCompass product.
 */

// Example: Add this to your main GitCompass frontend

// 1. Environment Configuration
const COMPASSCHAT_URL = process.env.REACT_APP_COMPASSCHAT_URL || 'https://chat.gitcompass.com';
const JWT_SECRET = process.env.JWT_SECRET_KEY; // Same secret as CompassChat backend

// 2. JWT Token Generation (Backend)
// Add this to your GitCompass backend/API
/**
 * Generate JWT token for CompassChat authentication
 */
function generateCompassChatToken(user) {
  const jwt = require('jsonwebtoken');
  
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
  
  return jwt.sign(payload, JWT_SECRET, { algorithm: 'HS256' });
}

// 3. Frontend Integration Examples

// Example 1: Add "Chat with Code" button to repository page
function ChatWithCodeButton({ repository, user }) {
  const handleChatWithCode = async () => {
    try {
      // Get JWT token from your backend
      const response = await fetch('/api/compasschat/token', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${user.accessToken}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ repository_url: repository.clone_url })
      });
      
      const { token } = await response.json();
      
      // Redirect to CompassChat with token
      const compasschatUrl = `${COMPASSCHAT_URL}?token=${token}&repo=${encodeURIComponent(repository.clone_url)}`;
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

// Example 2: Repository page integration
function RepositoryActions({ repository, user }) {
  return (
    <div className="repository-actions">
      {/* Your existing buttons */}
      <button>⭐ Star</button>
      <button>🍴 Fork</button>
      
      {/* New CompassChat integration */}
      <ChatWithCodeButton repository={repository} user={user} />
    </div>
  );
}

// Example 3: Navigation menu integration
function NavigationMenu({ user }) {
  const handleOpenCompassChat = async () => {
    try {
      const response = await fetch('/api/compasschat/token', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${user.accessToken}`,
          'Content-Type': 'application/json'
        }
      });
      
      const { token } = await response.json();
      const compasschatUrl = `${COMPASSCHAT_URL}?token=${token}`;
      
      window.open(compasschatUrl, '_blank');
    } catch (error) {
      console.error('Failed to open CompassChat:', error);
    }
  };

  return (
    <nav>
      <a href="/repositories">Repositories</a>
      <a href="/projects">Projects</a>
      <a href="/settings">Settings</a>
      
      {/* CompassChat quick access */}
      <button onClick={handleOpenCompassChat} className="nav-link">
        💬 AI Chat
      </button>
    </nav>
  );
}

// 4. Backend API Endpoint Example (Express.js)
/**
 * Add this endpoint to your GitCompass backend
 */
app.post('/api/compasschat/token', authenticateUser, async (req, res) => {
  try {
    const user = req.user; // From your authentication middleware
    const { repository_url } = req.body;
    
    // Generate JWT token for CompassChat
    const token = generateCompassChatToken(user);
    
    // Optionally, log the CompassChat access
    await logCompassChatAccess(user.id, repository_url);
    
    res.json({ token });
  } catch (error) {
    console.error('CompassChat token generation failed:', error);
    res.status(500).json({ error: 'Failed to generate CompassChat token' });
  }
});

// 5. WordPress/PHP Integration Example
/**
 * For WordPress or PHP-based GitCompass
 */
function generate_compasschat_token($user, $repository_url = null) {
    require_once 'vendor/autoload.php';
    
    $payload = [
        'user_id' => $user->ID,
        'username' => $user->user_login,
        'email' => $user->user_email,
        'name' => $user->display_name,
        'avatar_url' => get_avatar_url($user->ID),
        'exp' => time() + (30 * 60), // 30 minutes
        'iat' => time(),
        'iss' => 'gitcompass'
    ];
    
    return \Firebase\JWT\JWT::encode($payload, JWT_SECRET, 'HS256');
}

// Example WordPress shortcode
function compasschat_button_shortcode($atts) {
    if (!is_user_logged_in()) {
        return '<p>Please log in to use CompassChat</p>';
    }
    
    $user = wp_get_current_user();
    $token = generate_compasschat_token($user);
    $compasschat_url = COMPASSCHAT_URL . '?token=' . $token;
    
    return '<a href="' . $compasschat_url . '" target="_blank" class="btn btn-primary">💬 Chat with Code</a>';
}
add_shortcode('compasschat_button', 'compasschat_button_shortcode');

// 6. Security Best Practices

/**
 * Token validation middleware for your backend
 */
function validateCompassChatToken(req, res, next) {
  const token = req.headers.authorization?.replace('Bearer ', '');
  
  if (!token) {
    return res.status(401).json({ error: 'No token provided' });
  }
  
  try {
    const payload = jwt.verify(token, JWT_SECRET);
    req.compasschat_user = payload;
    next();
  } catch (error) {
    return res.status(401).json({ error: 'Invalid token' });
  }
}

// 7. Advanced Integration: Auto-analyze repositories

/**
 * Automatically trigger repository analysis when user accesses CompassChat
 */
async function autoAnalyzeRepository(user, repositoryUrl) {
  try {
    const response = await fetch(`${COMPASSCHAT_URL}/api/repos/analyze`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${user.compasschat_token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        repository_url: repositoryUrl,
        auto_analyze: true
      })
    });
    
    if (response.ok) {
      console.log('Repository analysis initiated');
    }
  } catch (error) {
    console.error('Auto-analysis failed:', error);
  }
}

export {
  generateCompassChatToken,
  ChatWithCodeButton,
  RepositoryActions,
  NavigationMenu,
  validateCompassChatToken,
  autoAnalyzeRepository
};
