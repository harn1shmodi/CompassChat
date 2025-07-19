#!/usr/bin/env python3
"""
Migration utilities for user-specific repository storage.

This script helps migrate existing repositories to the new user-specific
storage architecture while maintaining backward compatibility.
"""

import sys
import os
import logging
from typing import List, Dict, Any
from datetime import datetime

# Add the backend directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.neo4j_conn import neo4j_conn
from core.database import db_manager, User, RepositoryCache
from services.graph_service import GraphService
from services.cache_service import cache_service

logger = logging.getLogger(__name__)

class MigrationManager:
    """Manages migration of repositories to user-specific storage"""
    
    def __init__(self):
        self.graph_service = GraphService()
    
    def migrate_repositories_to_user_specific(self, target_user: str = "default_user"):
        """
        Migrate existing repositories to user-specific storage.
        
        Args:
            target_user: The username to assign all existing repositories to
        """
        logger.info("Starting migration to user-specific repository storage")
        
        try:
            with neo4j_conn.get_session() as session:
                # Get all existing repositories without user_id
                query = """
                MATCH (repo:Repository)
                WHERE repo.user_id IS NULL
                RETURN repo.owner as owner, repo.name as name, repo.url as url
                """
                
                results = session.run(query)
                repositories = []
                
                for record in results:
                    repositories.append({
                        'owner': record['owner'],
                        'name': record['name'],
                        'url': record['url']
                    })
                
                if not repositories:
                    logger.info("No repositories found that need migration")
                    return
                
                logger.info(f"Found {len(repositories)} repositories to migrate")
                
                # Create or get the target user
                try:
                    user = db_manager.create_user(
                        username=target_user,
                        email=f"{target_user}@compasschat.local",
                        password="migrated_user_2024"
                    )
                    logger.info(f"Created migration user: {target_user}")
                except ValueError:
                    # User already exists, get existing user
                    user = db_manager.authenticate_user(target_user, "migrated_user_2024")
                    logger.info(f"Using existing migration user: {target_user}")
                
                # Update each repository to include user_id
                updated_count = 0
                for repo in repositories:
                    try:
                        self._migrate_single_repository(session, repo, target_user)
                        updated_count += 1
                        
                        # Create cache entry for this repository
                        repo_url = repo.get('url', f"https://github.com/{repo['owner']}/{repo['name']}")
                        cache_service.update_repository_cache(
                            repo_url=repo_url,
                            repo_name=f"{repo['owner']}/{repo['name']}"
                        )
                        
                        # Grant user access
                        cache_service.grant_user_access(user, repo_url)
                        
                        logger.info(f"Migrated repository: {repo['owner']}/{repo['name']}")
                        
                    except Exception as e:
                        logger.error(f"Failed to migrate repository {repo['owner']}/{repo['name']}: {e}")
                
                logger.info(f"Migration completed. Updated {updated_count} repositories")
                
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            raise
    
    def _migrate_single_repository(self, session, repo: Dict[str, Any], user_id: str):
        """Migrate a single repository to user-specific storage"""
        
        # Update Repository node
        update_repo_query = """
        MATCH (repo:Repository {owner: $owner, name: $name})
        WHERE repo.user_id IS NULL
        SET repo.user_id = $user_id
        RETURN repo
        """
        
        session.run(update_repo_query, {
            'owner': repo['owner'],
            'name': repo['name'],
            'user_id': user_id
        })
        
        # Update File nodes
        update_files_query = """
        MATCH (repo:Repository {owner: $owner, name: $name, user_id: $user_id})-[:CONTAINS]->(file:File)
        WHERE file.user_id IS NULL
        SET file.user_id = $user_id
        RETURN count(file) as updated_files
        """
        
        result = session.run(update_files_query, {
            'owner': repo['owner'],
            'name': repo['name'],
            'user_id': user_id
        })
        
        updated_files = result.single()['updated_files']
        
        # Update Function nodes
        update_functions_query = """
        MATCH (file:File {user_id: $user_id})-[:DEFINES]->(func:Function)
        WHERE func.user_id IS NULL
        SET func.user_id = $user_id
        RETURN count(func) as updated_functions
        """
        
        result = session.run(update_functions_query, {'user_id': user_id})
        updated_functions = result.single()['updated_functions']
        
        # Update Class nodes
        update_classes_query = """
        MATCH (file:File {user_id: $user_id})-[:DEFINES]->(cls:Class)
        WHERE cls.user_id IS NULL
        SET cls.user_id = $user_id
        RETURN count(cls) as updated_classes
        """
        
        result = session.run(update_classes_query, {'user_id': user_id})
        updated_classes = result.single()['updated_classes']
        
        # Update Chunk nodes
        update_chunks_query = """
        MATCH (file:File {user_id: $user_id})-[:PART_OF]->(chunk:Chunk)
        WHERE chunk.user_id IS NULL
        SET chunk.user_id = $user_id
        RETURN count(chunk) as updated_chunks
        """
        
        result = session.run(update_chunks_query, {'user_id': user_id})
        updated_chunks = result.single()['updated_chunks']
        
        logger.info(f"Updated {updated_files} files, {updated_functions} functions, {updated_classes} classes, {updated_chunks} chunks")
    
    def verify_migration(self, user_id: str = None):
        """Verify the migration was successful"""
        try:
            with neo4j_conn.get_session() as session:
                # Check repositories with user_id
                if user_id:
                    query = """
                    MATCH (repo:Repository {user_id: $user_id})
                    RETURN repo.owner as owner, repo.name as name, count(repo) as repo_count
                    """
                    results = session.run(query, {'user_id': user_id})
                else:
                    query = """
                    MATCH (repo:Repository)
                    RETURN repo.user_id as user_id, count(repo) as repo_count
                    """
                    results = session.run(query)
                
                repositories = []
                for record in results:
                    repositories.append({
                        'owner': record.get('owner', 'unknown'),
                        'name': record.get('name', 'unknown'),
                        'user_id': record.get('user_id', 'unknown'),
                        'count': record['repo_count']
                    })
                
                logger.info(f"Migration verification: Found {len(repositories)} repositories")
                
                for repo in repositories:
                    logger.info(f"  - {repo['owner']}/{repo['name']} (user: {repo['user_id']})")
                
                return repositories
                
        except Exception as e:
            logger.error(f"Migration verification failed: {e}")
            raise
    
    def rollback_migration(self, target_user: str = None):
        """
        Rollback migration by removing user_id from all nodes.
        
        Args:
            target_user: If provided, only rollback repositories for this user
        """
        logger.info("Starting migration rollback")
        
        try:
            with neo4j_conn.get_session() as session:
                # Remove user_id from Repository nodes
                if target_user:
                    repo_query = """
                    MATCH (repo:Repository {user_id: $user_id})
                    REMOVE repo.user_id
                    RETURN count(repo) as removed_repos
                    """
                    result = session.run(repo_query, {'user_id': target_user})
                else:
                    repo_query = """
                    MATCH (repo:Repository)
                    WHERE repo.user_id IS NOT NULL
                    REMOVE repo.user_id
                    RETURN count(repo) as removed_repos
                    """
                    result = session.run(repo_query)
                
                removed_repos = result.single()['removed_repos']
                
                # Remove user_id from all related nodes
                nodes_to_update = ['File', 'Function', 'Class', 'Chunk']
                
                for node_type in nodes_to_update:
                    if target_user:
                        query = f"""
                        MATCH (n:{node_type} {{user_id: $user_id}})
                        REMOVE n.user_id
                        RETURN count(n) as removed_nodes
                        """
                        result = session.run(query, {'user_id': target_user})
                    else:
                        query = f"""
                        MATCH (n:{node_type})
                        WHERE n.user_id IS NOT NULL
                        REMOVE n.user_id
                        RETURN count(n) as removed_nodes
                        """
                        result = session.run(query)
                    
                    removed_nodes = result.single()['removed_nodes']
                    logger.info(f"Removed user_id from {removed_nodes} {node_type} nodes")
                
                logger.info(f"Rollback completed. Removed user_id from {removed_repos} repositories")
                
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            raise


def main():
    """Main CLI interface for migration"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Migrate repositories to user-specific storage')
    parser.add_argument('--action', choices=['migrate', 'verify', 'rollback'], required=True,
                        help='Action to perform')
    parser.add_argument('--user', default='default_user',
                        help='Username for migration (default: default_user)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    migration_manager = MigrationManager()
    
    try:
        if args.action == 'migrate':
            migration_manager.migrate_repositories_to_user_specific(args.user)
            migration_manager.verify_migration(args.user)
            
        elif args.action == 'verify':
            migration_manager.verify_migration(args.user)
            
        elif args.action == 'rollback':
            migration_manager.rollback_migration(args.user)
            migration_manager.verify_migration()
            
    except Exception as e:
        logger.error(f"Migration action failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()