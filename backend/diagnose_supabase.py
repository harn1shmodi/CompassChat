#!/usr/bin/env python3
"""
Supabase connection diagnostic script
Run this to test different connection methods
"""

import os
import socket
import time
import psycopg2
from urllib.parse import urlparse

def test_dns_resolution(hostname):
    """Test if we can resolve the Supabase hostname"""
    print(f"🔍 Testing DNS resolution for {hostname}")
    try:
        ip_addresses = socket.getaddrinfo(hostname, 5432, socket.AF_UNSPEC, socket.SOCK_STREAM)
        print(f"✅ DNS resolved to {len(ip_addresses)} addresses:")
        for addr in ip_addresses:
            print(f"   - {addr[4][0]} ({addr[0].name})")
        return True
    except Exception as e:
        print(f"❌ DNS resolution failed: {e}")
        return False

def test_tcp_connection(hostname, port=5432):
    """Test if we can establish a TCP connection"""
    print(f"🔌 Testing TCP connection to {hostname}:{port}")
    try:
        # Try IPv4 first
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        result = sock.connect_ex((hostname, port))
        sock.close()
        
        if result == 0:
            print(f"✅ TCP connection successful")
            return True
        else:
            print(f"❌ TCP connection failed (error code: {result})")
            return False
    except Exception as e:
        print(f"❌ TCP connection error: {e}")
        return False

def test_postgres_connection(database_url):
    """Test PostgreSQL connection with different SSL modes"""
    parsed = urlparse(database_url)
    hostname = parsed.hostname
    
    print(f"🐘 Testing PostgreSQL connection to {hostname}")
    
    # Test different SSL modes
    ssl_modes = ['require', 'prefer', 'disable']
    
    for ssl_mode in ssl_modes:
        print(f"   Trying SSL mode: {ssl_mode}")
        try:
            # Modify URL to include SSL mode
            test_url = database_url
            if '?' in test_url:
                test_url += f"&sslmode={ssl_mode}"
            else:
                test_url += f"?sslmode={ssl_mode}"
            
            conn = psycopg2.connect(test_url, connect_timeout=15)
            cursor = conn.cursor()
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            print(f"   ✅ Connected with {ssl_mode}: {version[:50]}...")
            conn.close()
            return ssl_mode
        except Exception as e:
            print(f"   ❌ Failed with {ssl_mode}: {e}")
    
    return None

def main():
    print("🚀 Supabase Connection Diagnostics")
    print("=" * 50)
    
    # Get DATABASE_URL from environment or use default
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ No DATABASE_URL environment variable found")
        print("Please set your Supabase connection string:")
        print("export DATABASE_URL='postgresql://postgres:[password]@db.[project-ref].supabase.co:5432/postgres'")
        return
    
    print(f"📝 Database URL: {database_url.split('@')[0]}@***")
    
    # Parse the URL
    try:
        parsed = urlparse(database_url)
        hostname = parsed.hostname
        port = parsed.port or 5432
        
        print(f"🎯 Target: {hostname}:{port}")
        print()
        
        # Run tests
        dns_ok = test_dns_resolution(hostname)
        tcp_ok = test_tcp_connection(hostname, port) if dns_ok else False
        ssl_mode = test_postgres_connection(database_url) if tcp_ok else None
        
        print()
        print("📊 Summary:")
        print(f"   DNS Resolution: {'✅' if dns_ok else '❌'}")
        print(f"   TCP Connection: {'✅' if tcp_ok else '❌'}")
        print(f"   PostgreSQL:     {'✅' if ssl_mode else '❌'}")
        
        if ssl_mode:
            print(f"   Best SSL mode: {ssl_mode}")
            print()
            print("🎉 Connection successful! Your Supabase database is reachable.")
            print(f"💡 Recommended connection string addition: ?sslmode={ssl_mode}")
        else:
            print()
            print("❌ Connection failed. Possible issues:")
            print("   1. Check your Supabase project is running")
            print("   2. Verify the connection string is correct")
            print("   3. Check Digital Ocean's network connectivity")
            print("   4. Try using a different region for your Supabase project")
    
    except Exception as e:
        print(f"❌ URL parsing failed: {e}")

if __name__ == "__main__":
    main()
