import React, { useState, useEffect } from 'react';
import './Auth.css';

interface User {
  id: number;
  username: string;
  email: string;
  display_name?: string;
  avatar_url?: string;
  oauth_provider?: string;
}

interface AuthProps {
  onLogin: (user: User, token: string) => void;
}

export const Auth: React.FC<AuthProps> = ({ onLogin }) => {
  const [isLogin, setIsLogin] = useState(true);
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: ''
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [oauthLoading, setOauthLoading] = useState(false);
  const [oauthAvailable, setOauthAvailable] = useState({
    google: false,
    github: false
  });

  // Check which OAuth providers are available
  useEffect(() => {
    fetch('/api/auth/oauth/config')
      .then(response => response.json())
      .then(data => {
        setOauthAvailable({
          google: data.google_available || false,
          github: data.github_available || false
        });
      })
      .catch(() => {
        // If endpoint doesn't exist, assume no OAuth available
        setOauthAvailable({ google: false, github: false });
      });
  }, []);

  // Check for OAuth callback token in URL params
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('token');
    const provider = urlParams.get('provider');
    
    if (token && provider) {
      // Clear URL params
      window.history.replaceState({}, document.title, window.location.pathname);
      
      // Validate the session token by getting user info
      fetch('/api/auth/me', {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      .then(response => response.json())
      .then(data => {
        if (data.id) {
          onLogin(data, token);
        } else {
          setError('Authentication failed. Please try again.');
        }
      })
      .catch(() => {
        setError('Authentication failed. Please try again.');
      });
    }
  }, [onLogin]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const endpoint = isLogin ? '/api/auth/login' : '/api/auth/register';
      const body = isLogin 
        ? { username: formData.username, password: formData.password }
        : formData;

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      });

      const data = await response.json();

      if (response.ok) {
        onLogin(data.user, data.session_token);
      } else {
        setError(data.detail || 'Authentication failed');
      }
    } catch (err) {
      setError('Network error. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleOAuthLogin = async (provider: 'google' | 'github') => {
    setOauthLoading(true);
    setError('');

    try {
      const response = await fetch(`/api/auth/oauth/${provider}`);
      const data = await response.json();

      if (response.ok && data.auth_url) {
        // Redirect to OAuth provider
        window.location.href = data.auth_url;
      } else {
        setError(`Failed to initiate ${provider} authentication`);
        setOauthLoading(false);
      }
    } catch (err) {
      setError('Network error. Please try again.');
      setOauthLoading(false);
    }
  };

  const handleGitCompassLogin = () => {
    // Redirect to GitCompass for authentication
    const gitcompassUrl = 'https://gitcompass.com';
    const redirectUrl = encodeURIComponent(window.location.origin);
    window.location.href = `${gitcompassUrl}/auth/compasschat?redirect=${redirectUrl}`;
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    });
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="auth-header">
          <h1>CompassChat</h1>
          <p>Chat with your code using AI</p>
        </div>

        <div className="auth-tabs">
          <button 
            className={isLogin ? 'tab active' : 'tab'}
            onClick={() => setIsLogin(true)}
          >
            Login
          </button>
          <button 
            className={!isLogin ? 'tab active' : 'tab'}
            onClick={() => setIsLogin(false)}
          >
            Register
          </button>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          {error && <div className="error-message">{error}</div>}
          
          <div className="form-group">
            <label>Username</label>
            <input
              type="text"
              name="username"
              value={formData.username}
              onChange={handleInputChange}
              required
              placeholder="Enter your username"
              className="form-input"
            />
          </div>

          {!isLogin && (
            <div className="form-group">
              <label>Email</label>
              <input
                type="email"
                name="email"
                value={formData.email}
                onChange={handleInputChange}
                required
                placeholder="Enter your email"
                className="form-input"
              />
            </div>
          )}

          <div className="form-group">
            <label>Password</label>
            <input
              type="password"
              name="password"
              value={formData.password}
              onChange={handleInputChange}
              required
              placeholder="Enter your password"
              minLength={6}
              className="form-input"
            />
          </div>

          <button 
            type="submit" 
            className="submit-button"
            disabled={loading}
          >
            {loading ? 'Please wait...' : (isLogin ? 'Login' : 'Register')}
          </button>
        </form>

        {(oauthAvailable.google || oauthAvailable.github) && (
          <>
            <div className="oauth-divider">
              <span>or</span>
            </div>

            <div className="oauth-buttons">
              <button 
                className="oauth-button gitcompass-button"
                onClick={handleGitCompassLogin}
                disabled={oauthLoading}
              >
                <span>Continue with GitCompass</span>
              </button>
              
              {oauthAvailable.google && (
                <button 
                  className="oauth-button google-button"
                  onClick={() => handleOAuthLogin('google')}
                  disabled={oauthLoading}
                >
                  <span>Continue with Google</span>
                </button>
              )}
              
              {oauthAvailable.github && (
                <button 
                  className="oauth-button github-button"
                  onClick={() => handleOAuthLogin('github')}
                  disabled={oauthLoading}
                >
                  <span>Continue with GitHub</span>
                </button>
              )}
            </div>
          </>
        )}

        <div className="auth-footer">
          <p>
            {isLogin ? "Don't have an account? " : "Already have an account? "}
            <button 
              className="link-button"
              onClick={() => setIsLogin(!isLogin)}
            >
              {isLogin ? 'Register' : 'Login'}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
};
