#!/usr/bin/env python3
"""
Test script for OAuth integration
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta
import jwt

# Add the backend directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from services.oauth_service import oauth_service
from core.config import Settings

async def test_oauth_service():
    """Test OAuth service functionality"""
    print("Testing OAuth Service...")
    
    settings = Settings()
    
    # Test 1: Create a test JWT token (simulating GitCompass)
    print("\n1. Testing JWT token creation and validation...")
    
    test_user_data = {
        "id": 1,
        "username": "test_user",
        "email": "test@example.com",
        "name": "Test User"
    }
    
    # Create a test token
    test_token = oauth_service.create_jwt_token(test_user_data)
    print(f"Created test token: {test_token[:50]}...")
    
    # Validate the token
    try:
        validated_data = await oauth_service.validate_gitcompass_token(test_token)
        if validated_data:
            print("✅ Token validation successful")
            print(f"   User: {validated_data.get('username')}")
            print(f"   Email: {validated_data.get('email')}")
        else:
            print("❌ Token validation failed")
    except Exception as e:
        print(f"❌ Token validation error: {e}")
    
    # Test 2: Mock OAuth data processing
    print("\n2. Testing OAuth data processing...")
    
    mock_google_data = {
        "provider": "google",
        "provider_id": "123456789",
        "email": "testuser@gmail.com",
        "name": "Test User",
        "username": "testuser",
        "avatar_url": "https://example.com/avatar.jpg"
    }
    
    try:
        user = await oauth_service.get_or_create_oauth_user(mock_google_data)
        if user:
            print("✅ OAuth user creation/retrieval successful")
            print(f"   User ID: {user.id}")
            print(f"   Username: {user.username}")
            print(f"   Provider: {user.oauth_provider}")
        else:
            print("❌ OAuth user creation failed")
    except Exception as e:
        print(f"❌ OAuth user processing error: {e}")
    
    print("\n3. Configuration check...")
    print(f"   JWT Secret Key: {'✅ Set' if settings.jwt_secret_key else '❌ Not set'}")
    print(f"   GitCompass URL: {settings.gitcompass_base_url}")
    print(f"   Google Client ID: {'✅ Set' if settings.google_client_id else '❌ Not set'}")
    print(f"   GitHub Client ID: {'✅ Set' if settings.github_client_id else '❌ Not set'}")
    
    print("\nOAuth service test completed!")

if __name__ == "__main__":
    try:
        asyncio.run(test_oauth_service())
    except Exception as e:
        print(f"Test failed with error: {e}")
        sys.exit(1)
