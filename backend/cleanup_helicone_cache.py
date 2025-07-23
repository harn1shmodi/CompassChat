#!/usr/bin/env python3
"""
Script to delete cached Helicone repository data from SQLite database
This will clear both the repository cache and user analyses for Helicone
"""

import sys
import os
from pathlib import Path

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from core.database import db_manager, RepositoryCache, UserRepositoryAnalysis
from services.graph_service import GraphService
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def delete_helicone_cache():
    """Delete all cached data for the Helicone repository"""
    
    # Possible variations of Helicone repository URLs and names
    helicone_identifiers = [
        "https://github.com/helicone/helicone",
        "https://github.com/helicone/helicone.git",
        "helicone/helicone",
        "git@github.com:helicone/helicone.git"
    ]
    
    session = db_manager.get_session()
    deleted_repos = 0
    deleted_user_analyses = 0
    
    try:
        # Find all repository cache entries that match Helicone
        for identifier in helicone_identifiers:
            # Check by repo_url
            repo_caches = session.query(RepositoryCache).filter(
                RepositoryCache.repo_url.like(f"%{identifier}%")
            ).all()
            
            # Check by repo_name
            if "helicone/helicone" in identifier:
                repo_caches_by_name = session.query(RepositoryCache).filter(
                    RepositoryCache.repo_name == "helicone/helicone"
                ).all()
                repo_caches.extend(repo_caches_by_name)
        
        # Remove duplicates
        unique_repo_caches = list({repo.id: repo for repo in repo_caches}.values())
        
        if not unique_repo_caches:
            print("❌ No Helicone repository cache entries found")
            return
        
        print(f"🔍 Found {len(unique_repo_caches)} Helicone repository cache entries:")
        
        for repo_cache in unique_repo_caches:
            print(f"  - ID: {repo_cache.id}")
            print(f"    URL: {repo_cache.repo_url}")
            print(f"    Name: {repo_cache.repo_name}")
            print(f"    Files: {repo_cache.total_files}, Chunks: {repo_cache.total_chunks}")
            print(f"    Last analyzed: {repo_cache.analysis_completed_at}")
            print()
        
        # Confirm deletion
        confirm = input("🗑️  Delete these entries? (yes/no): ").lower().strip()
        if confirm not in ['yes', 'y']:
            print("❌ Deletion cancelled")
            return
        
        # Delete user repository analyses first (foreign key constraint)
        for repo_cache in unique_repo_caches:
            user_analyses = session.query(UserRepositoryAnalysis).filter(
                UserRepositoryAnalysis.repository_cache_id == repo_cache.id
            ).all()
            
            for analysis in user_analyses:
                session.delete(analysis)
                deleted_user_analyses += 1
                print(f"🗑️  Deleted user analysis: {analysis.id}")
        
        # Delete repository cache entries
        for repo_cache in unique_repo_caches:
            session.delete(repo_cache)
            deleted_repos += 1
            print(f"🗑️  Deleted repository cache: {repo_cache.repo_name}")
        
        # Commit the changes
        session.commit()
        
        print(f"\n✅ Successfully deleted:")
        print(f"   - {deleted_repos} repository cache entries")
        print(f"   - {deleted_user_analyses} user repository analyses")
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ Error deleting Helicone cache: {e}")
        raise
    finally:
        session.close()

def delete_helicone_from_neo4j():
    """Delete Helicone data from Neo4j graph database"""
    try:
        print("\n🔍 Checking Neo4j for Helicone data...")
        graph_service = GraphService()
        
        # Check if repository exists
        if graph_service.repository_exists("helicone/helicone"):
            print("🗑️  Deleting Helicone data from Neo4j...")
            graph_service.clear_repository("helicone/helicone")
            print("✅ Helicone data deleted from Neo4j")
        else:
            print("ℹ️  No Helicone data found in Neo4j")
            
    except Exception as e:
        logger.error(f"❌ Error deleting from Neo4j: {e}")

def main():
    """Main function to orchestrate the deletion"""
    print("🧹 Helicone Repository Cache Cleanup Tool")
    print("=" * 50)
    
    try:
        # Delete from SQLite database
        delete_helicone_cache()
        
        # Delete from Neo4j graph database
        delete_helicone_from_neo4j()
        
        print("\n🎉 Cleanup completed successfully!")
        print("💡 You can now re-analyze the Helicone repository with the new optimizations")
        
    except Exception as e:
        logger.error(f"❌ Cleanup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
