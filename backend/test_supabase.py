#!/usr/bin/env python3
"""
Test script to verify Supabase database connection
Run this locally with your Supabase DATABASE_URL to test the connection
"""

import os
from sqlalchemy import create_engine, text
from core.database import Base, DatabaseManager

def test_supabase_connection():
    # Replace with your actual Supabase URL for testing
    database_url = "postgresql://postgres:RadhaSoami12#$@db.cmkzjrtnksomsjmfishm.supabase.co:5432/postgres"
    
    try:
        print("Testing Supabase connection...")
        
        # Test basic connection
        engine = create_engine(database_url, connect_args={"sslmode": "require"})
        
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            print(f"✅ Connected to PostgreSQL: {version}")
        
        # Test table creation
        print("Testing table creation...")
        Base.metadata.create_all(bind=engine)
        print("✅ Tables created successfully")
        
        # Test DatabaseManager
        print("Testing DatabaseManager...")
        os.environ["DATABASE_URL"] = database_url
        db_manager = DatabaseManager()
        print("✅ DatabaseManager initialized successfully")
        
        print("\n🎉 All tests passed! Your Supabase database is ready.")
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("Double-check your DATABASE_URL and network connection")

if __name__ == "__main__":
    test_supabase_connection()
