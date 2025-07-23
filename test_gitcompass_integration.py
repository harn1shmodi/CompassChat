#!/usr/bin/env python3
"""
Test script to simulate GitCompass JWT token generation and validation
This helps you test the integration before implementing in GitCompass
"""
import jwt
import json
from datetime import datetime, timedelta

# Test configuration (use your actual values)
JWT_SECRET = "test_secret_key_change_in_production"  # Same as in your .env
COMPASSCHAT_URL = "https://chat.gitcompass.com"  # Your CompassChat URL

def generate_gitcompass_token(user_data):
    """Simulate how GitCompass would generate a JWT token"""
    payload = {
        "user_id": user_data["id"],
        "username": user_data["username"],
        "email": user_data["email"],
        "name": user_data.get("name", ""),
        "avatar_url": user_data.get("avatar_url", ""),
        "exp": datetime.utcnow() + timedelta(minutes=30),  # 30 minutes
        "iat": datetime.utcnow(),
        "iss": "gitcompass"
    }
    
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    return token

def validate_token(token):
    """Simulate how CompassChat validates the token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        return {"error": "Token expired"}
    except jwt.InvalidTokenError as e:
        return {"error": f"Invalid token: {e}"}

def main():
    print("🧪 GitCompass JWT Integration Test")
    print("=" * 50)
    
    # Simulate a GitCompass user
    test_user = {
        "id": 123,
        "username": "john_doe",
        "email": "john@example.com",
        "name": "John Doe",
        "avatar_url": "https://github.com/johndoe.png"
    }
    
    print("📋 Test User Data:")
    print(json.dumps(test_user, indent=2))
    
    # Generate token (this is what GitCompass would do)
    print("\n🔐 Generating JWT Token...")
    token = generate_gitcompass_token(test_user)
    print(f"Token: {token[:50]}...")
    
    # Validate token (this is what CompassChat would do)
    print("\n✅ Validating Token...")
    validation_result = validate_token(token)
    
    if "error" in validation_result:
        print(f"❌ Validation failed: {validation_result['error']}")
    else:
        print("✅ Token validated successfully!")
        print("Decoded payload:")
        print(json.dumps(validation_result, indent=2, default=str))
    
    # Generate CompassChat URL
    print(f"\n🔗 CompassChat URL:")
    compasschat_url = f"{COMPASSCHAT_URL}?token={token}"
    print(compasschat_url)
    
    print("\n" + "=" * 50)
    print("📝 Integration Steps for GitCompass:")
    print("1. Add JWT library to your GitCompass project")
    print("2. Set JWT_SECRET_KEY in your .env file")
    print("3. Create token generation endpoint")
    print("4. Add 'Chat with Code' buttons that call the endpoint")
    print("5. Redirect users to CompassChat with the token")
    
    print("\n🎯 Example GitCompass Implementation:")
    print("""
// Node.js/Express example
const jwt = require('jsonwebtoken');

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
""")

if __name__ == "__main__":
    main()
