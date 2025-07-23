# OAuth Integration Setup for CompassChat

This guide explains how to integrate CompassChat with your main GitCompass product using OAuth authentication.

## Overview

CompassChat now supports three authentication methods:

1. **GitCompass Integration** - Users authenticate through your main GitCompass product
2. **Google OAuth** - Direct Google authentication  
3. **GitHub OAuth** - Direct GitHub authentication
4. **Traditional Login** - Username/password (fallback)

## Implementation Options

### Option 1: GitCompass JWT Token Validation (Recommended)

This is the most seamless approach where users authenticate on GitCompass and get redirected to CompassChat with a valid JWT token.

#### Setup Steps:

1. **Configure JWT Shared Secret**
   ```bash
   # In your .env file
   JWT_SECRET_KEY=your_shared_secret_key_with_gitcompass
   GITCOMPASS_BASE_URL=https://gitcompass.com
   ```

2. **Update GitCompass to redirect to CompassChat**
   Add a "Chat with Code" button or link that redirects to:
   ```
   https://chat.gitcompass.com?token=JWT_TOKEN_HERE
   ```

3. **Token Validation Endpoint**
   CompassChat validates tokens via `/api/auth/gitcompass/validate`

### Option 2: OAuth App Integration

Use the same Google/GitHub OAuth apps from your main product.

#### Google OAuth Setup:

1. **Configure OAuth credentials**
   ```bash
   GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=your_client_secret
   ```

2. **Add redirect URI to Google OAuth app**
   ```
   https://chat.gitcompass.com/api/auth/oauth/google/callback
   ```

#### GitHub OAuth Setup:

1. **Configure OAuth credentials**
   ```bash
   GITHUB_CLIENT_ID=your_github_client_id
   GITHUB_CLIENT_SECRET=your_github_client_secret
   ```

2. **Add redirect URI to GitHub OAuth app**
   ```
   https://chat.gitcompass.com/api/auth/oauth/github/callback
   ```

## Frontend Integration

The frontend now includes OAuth buttons that:

1. Redirect users to OAuth providers
2. Handle callback tokens
3. Automatically log users in
4. Show user avatars and display names

## API Endpoints

### New Authentication Endpoints:

- `GET /api/auth/oauth/{provider}` - Initiate OAuth flow
- `GET /api/auth/oauth/{provider}/callback` - Handle OAuth callback
- `POST /api/auth/oauth/callback` - Handle OAuth via POST
- `POST /api/auth/gitcompass/validate` - Validate GitCompass tokens

### Updated User Response:

```json
{
  "id": 1,
  "username": "john_doe",
  "email": "john@example.com",
  "display_name": "John Doe",
  "avatar_url": "https://avatar.url",
  "oauth_provider": "google",
  "created_at": "2024-01-01T00:00:00"
}
```

## Database Changes

The User model now includes OAuth fields:

- `oauth_provider` - Which provider was used ('google', 'github', 'gitcompass')
- `oauth_provider_id` - Provider's user ID
- `display_name` - Full name from OAuth
- `avatar_url` - Profile picture URL
- `hashed_password` - Now nullable for OAuth users

## Security Considerations

1. **JWT Secret**: Use a strong, shared secret between GitCompass and CompassChat
2. **HTTPS**: Ensure all OAuth redirects use HTTPS
3. **Token Expiry**: JWT tokens should have reasonable expiry times
4. **CORS**: Update CORS origins to include your domains

## Environment Variables

Required environment variables for OAuth integration:

```bash
# JWT Configuration
JWT_SECRET_KEY=your_super_secret_jwt_key
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30

# GitCompass Integration
GITCOMPASS_BASE_URL=https://gitcompass.com
GITCOMPASS_OAUTH_CLIENT_ID=optional_for_direct_oauth
GITCOMPASS_OAUTH_CLIENT_SECRET=optional_for_direct_oauth

# Google OAuth
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret

# GitHub OAuth
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret
```

## Integration Flow Examples

### Flow 1: GitCompass → CompassChat

1. User logs into GitCompass
2. User clicks "Chat with Code" 
3. GitCompass generates JWT token
4. User redirected to `https://chat.gitcompass.com?token=JWT_TOKEN`
5. CompassChat validates token and logs user in

### Flow 2: Direct OAuth

1. User visits CompassChat
2. User clicks "Continue with Google/GitHub"
3. Redirected to OAuth provider
4. After authentication, redirected back to CompassChat
5. CompassChat creates or links user account

## Testing

To test OAuth integration:

1. Set up OAuth apps with localhost redirect URIs for development
2. Use ngrok or similar for testing webhooks locally
3. Test token validation with sample JWT tokens

## Migration

Existing users can link their OAuth accounts:
- Email matching automatically links accounts
- Display names and avatars are updated from OAuth providers
- Traditional password login remains available as fallback

This implementation provides a seamless authentication experience while maintaining security and flexibility.
