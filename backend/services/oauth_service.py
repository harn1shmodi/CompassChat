import httpx
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from core.config import Settings
from core.database import db_manager
import logging

logger = logging.getLogger(__name__)
settings = Settings()

class OAuthService:
    """Service for handling OAuth integration with GitCompass and external providers"""
    
    def __init__(self):
        self.settings = settings
        
    async def validate_gitcompass_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate a JWT token from GitCompass main product"""
        try:
            # If you have a shared secret with GitCompass, validate locally
            if self.settings.jwt_secret_key:
                payload = jwt.decode(
                    token, 
                    self.settings.jwt_secret_key, 
                    algorithms=[self.settings.jwt_algorithm]
                )
                return payload
            
            # Otherwise, validate with GitCompass API
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.settings.gitcompass_base_url}/api/auth/validate",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    return response.json()
                    
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
        except Exception as e:
            logger.error(f"Error validating GitCompass token: {e}")
            return None
            
        return None
    
    async def exchange_oauth_code(self, provider: str, code: str, redirect_uri: str) -> Optional[Dict[str, Any]]:
        """Exchange OAuth code for user information"""
        try:
            if provider == "google":
                return await self._exchange_google_code(code, redirect_uri)
            elif provider == "github":
                return await self._exchange_github_code(code, redirect_uri)
            else:
                logger.error(f"Unsupported OAuth provider: {provider}")
                return None
                
        except Exception as e:
            logger.error(f"Error exchanging OAuth code: {e}")
            return None
    
    async def _exchange_google_code(self, code: str, redirect_uri: str) -> Optional[Dict[str, Any]]:
        """Exchange Google OAuth code for user info"""
        async with httpx.AsyncClient() as client:
            # Exchange code for access token
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": self.settings.google_client_id,
                    "client_secret": self.settings.google_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                }
            )
            
            if token_response.status_code != 200:
                logger.error(f"Google token exchange failed: {token_response.text}")
                return None
                
            token_data = token_response.json()
            access_token = token_data.get("access_token")
            
            # Get user info
            user_response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if user_response.status_code == 200:
                user_data = user_response.json()
                return {
                    "provider": "google",
                    "provider_id": user_data.get("id"),
                    "email": user_data.get("email"),
                    "name": user_data.get("name"),
                    "avatar_url": user_data.get("picture"),
                    "username": user_data.get("email").split("@")[0] if user_data.get("email") else None
                }
                
        return None
    
    async def _exchange_github_code(self, code: str, redirect_uri: str) -> Optional[Dict[str, Any]]:
        """Exchange GitHub OAuth code for user info"""
        async with httpx.AsyncClient() as client:
            # Exchange code for access token
            token_response = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": self.settings.github_client_id,
                    "client_secret": self.settings.github_client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"}
            )
            
            if token_response.status_code != 200:
                logger.error(f"GitHub token exchange failed: {token_response.text}")
                return None
                
            token_data = token_response.json()
            access_token = token_data.get("access_token")
            
            # Get user info
            user_response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            
            if user_response.status_code == 200:
                user_data = user_response.json()
                
                # Get user email (might be private)
                email_response = await client.get(
                    "https://api.github.com/user/emails",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github.v3+json"
                    }
                )
                
                email = None
                if email_response.status_code == 200:
                    emails = email_response.json()
                    primary_email = next((e for e in emails if e.get("primary")), None)
                    email = primary_email.get("email") if primary_email else user_data.get("email")
                
                return {
                    "provider": "github",
                    "provider_id": str(user_data.get("id")),
                    "email": email,
                    "name": user_data.get("name") or user_data.get("login"),
                    "avatar_url": user_data.get("avatar_url"),
                    "username": user_data.get("login")
                }
                
        return None
    
    def create_jwt_token(self, user_data: Dict[str, Any]) -> str:
        """Create a JWT token for the user"""
        payload = {
            "user_id": user_data.get("id"),
            "username": user_data.get("username"),
            "email": user_data.get("email"),
            "exp": datetime.utcnow() + timedelta(minutes=self.settings.jwt_access_token_expire_minutes),
            "iat": datetime.utcnow(),
            "iss": "compasschat"
        }
        
        return jwt.encode(payload, self.settings.jwt_secret_key, algorithm=self.settings.jwt_algorithm)
    
    async def get_or_create_oauth_user(self, oauth_data: Dict[str, Any]) -> Optional[Any]:
        """Get or create user from OAuth data"""
        try:
            provider = oauth_data.get("provider")
            provider_id = oauth_data.get("provider_id")
            email = oauth_data.get("email")
            username = oauth_data.get("username")
            name = oauth_data.get("name")
            
            if not email or not username:
                logger.error("Missing required OAuth data: email or username")
                return None
            
            # Check if user exists by email
            user = db_manager.get_user_by_email(email)
            
            if not user:
                # Create new user
                user = db_manager.create_oauth_user(
                    username=username,
                    email=email,
                    provider=provider,
                    provider_id=provider_id,
                    display_name=name,
                    avatar_url=oauth_data.get("avatar_url")
                )
                logger.info(f"Created new OAuth user: {username} ({provider})")
            else:
                # Update existing user with OAuth info if needed
                db_manager.update_user_oauth_info(
                    user.id,
                    provider=provider,
                    provider_id=provider_id,
                    avatar_url=oauth_data.get("avatar_url")
                )
                logger.info(f"Updated existing user with OAuth info: {username} ({provider})")
            
            return user
            
        except Exception as e:
            logger.error(f"Error creating/updating OAuth user: {e}")
            return None

oauth_service = OAuthService()
