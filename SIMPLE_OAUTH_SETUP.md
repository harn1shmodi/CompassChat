# Option 2: Shared OAuth Apps - Simple Setup Guide

## Quick Setup (No New OAuth Apps Needed!)

Since you want to use your existing GitCompass OAuth setup, here's the simplified approach:

### Step 1: Copy Your Existing OAuth Credentials

If you already have Google/GitHub OAuth set up for GitCompass, just copy those same credentials to CompassChat:

**From your GitCompass `.env` file, copy these values:**

```bash
# Add to CompassChat backend/.env
GOOGLE_CLIENT_ID=your_existing_google_client_id
GOOGLE_CLIENT_SECRET=your_existing_google_client_secret
GITHUB_CLIENT_ID=your_existing_github_client_id  
GITHUB_CLIENT_SECRET=your_existing_github_client_secret

# Add a JWT secret for session management
JWT_SECRET_KEY=your_super_secret_jwt_key_change_in_production
```

### Step 2: Update OAuth App Redirect URIs

In your existing OAuth applications, add CompassChat's redirect URIs:

**Google OAuth Console:**
- Go to your existing Google OAuth app
- Add redirect URI: `https://chat.gitcompass.com/api/auth/oauth/google/callback`
- (For development: `http://localhost:8000/api/auth/oauth/google/callback`)

**GitHub OAuth App:**
- Go to your existing GitHub OAuth app  
- Add redirect URI: `https://chat.gitcompass.com/api/auth/oauth/github/callback`
- (For development: `http://localhost:8000/api/auth/oauth/github/callback`)

### Step 3: That's It!

Deploy CompassChat and the OAuth buttons will automatically appear. Users can login with the same Google/GitHub accounts they use for GitCompass.

## If You Don't Have OAuth Apps Yet

No problem! You can start without OAuth and add it later:

### Current State (No OAuth)
- Users see only "Login/Register" form
- Traditional username/password authentication works
- You can add OAuth anytime later

### Adding OAuth Later
When you create OAuth apps for GitCompass, just add the CompassChat redirect URIs and copy the credentials.

## Testing Without OAuth

You can test CompassChat right now:

1. **Create a test account:**
   ```bash
   # Visit http://localhost:5173 (or your CompassChat URL)
   # Click "Register" 
   # Create username/password account
   ```

2. **OAuth buttons won't show** (which is correct since no OAuth is configured)

3. **Traditional login works perfectly**

## What You'll See

**Without OAuth configured:**
- Only login/register form
- No OAuth buttons
- Clean, simple interface

**With OAuth configured:**
- Login/register form
- "Continue with Google" button (if Google OAuth configured)
- "Continue with GitHub" button (if GitHub OAuth configured)  
- "Continue with GitCompass" button (always available)

## Easy Migration Path

```bash
# Phase 1: Deploy CompassChat with traditional auth
# No OAuth needed - works immediately

# Phase 2: Add OAuth when ready
# Copy existing OAuth credentials from GitCompass
# Add redirect URIs to existing OAuth apps
# Redeploy - OAuth buttons appear automatically

# Phase 3: Add GitCompass integration
# Generate JWT tokens in GitCompass
# Link to CompassChat with tokens
# Seamless user experience
```

## Quick Test

Want to see if it works? Just deploy with minimal config:

```bash
# Minimum required .env
DATABASE_URL=sqlite:///./compasschat.db
OPENAI_API_KEY=your_openai_key
JWT_SECRET_KEY=any_random_secret_for_now

# That's it! OAuth is completely optional
```

The system is designed to gracefully handle missing OAuth configuration - users just won't see those login options.
