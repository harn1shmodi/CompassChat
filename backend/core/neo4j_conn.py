from neo4j import GraphDatabase
from core.config import settings
import logging

logger = logging.getLogger(__name__)


class Neo4jConnection:
    def __init__(self):
        self.driver = None
        self.connect()
    
    def connect(self):
        try:
            self.driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password)
            )
            # Test connection
            with self.driver.session(database=settings.neo4j_database) as session:
                session.run("RETURN 1")
            logger.info("Connected to Neo4j successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise
    
    def close(self):
        if self.driver:
            self.driver.close()
    
    def get_session(self):
        return self.driver.session(database=settings.neo4j_database)
    
    def create_indexes(self):
        """Create necessary indexes and constraints"""
        with self.get_session() as session:
            # Create constraints
            constraints = [
                "CREATE CONSTRAINT file_path_unique IF NOT EXISTS FOR (f:File) REQUIRE f.path IS UNIQUE",
                "CREATE CONSTRAINT function_id_unique IF NOT EXISTS FOR (fn:Function) REQUIRE fn.id IS UNIQUE",
                "CREATE CONSTRAINT class_id_unique IF NOT EXISTS FOR (c:Class) REQUIRE c.id IS UNIQUE",
                "CREATE CONSTRAINT chunk_id_unique IF NOT EXISTS FOR (ch:Chunk) REQUIRE ch.id IS UNIQUE",
                "CREATE CONSTRAINT changelog_id_unique IF NOT EXISTS FOR (cl:Changelog) REQUIRE cl.id IS UNIQUE",
                "CREATE CONSTRAINT repository_unique IF NOT EXISTS FOR (r:Repository) REQUIRE (r.owner, r.name) IS UNIQUE"
            ]
            
            for constraint in constraints:
                try:
                    session.run(constraint)
                    logger.info(f"Created constraint: {constraint}")
                except Exception as e:
                    logger.warning(f"Constraint may already exist: {e}")
            
            # Create vector index for embeddings
            vector_index_query = """
            CREATE VECTOR INDEX chunk_embeddings IF NOT EXISTS
            FOR (c:Chunk) ON (c.embedding)
            OPTIONS {
                indexConfig: {
                    `vector.dimensions`: 1536,
                    `vector.similarity_function`: 'cosine'
                }
            }
            """
            try:
                session.run(vector_index_query)
                logger.info("Created vector index for chunk embeddings")
            except Exception as e:
                logger.warning(f"Vector index may already exist: {e}")
            
            # Create full-text search index
            fulltext_index_query = """
            CREATE FULLTEXT INDEX chunk_content IF NOT EXISTS
            FOR (c:Chunk) ON EACH [c.content, c.summary]
            """
            try:
                session.run(fulltext_index_query)
                logger.info("Created full-text index for chunk content")
            except Exception as e:
                logger.warning(f"Full-text index may already exist: {e}")
            
            # Create full-text search index for changelog content
            changelog_fulltext_index_query = """
            CREATE FULLTEXT INDEX changelog_content IF NOT EXISTS
            FOR (cl:Changelog) ON EACH [cl.content, cl.summary]
            """
            try:
                session.run(changelog_fulltext_index_query)
                logger.info("Created full-text index for changelog content")
            except Exception as e:
                logger.warning(f"Changelog full-text index may already exist: {e}")
            
            # Create index for changelog version and date
            changelog_indexes = [
                "CREATE INDEX changelog_version IF NOT EXISTS FOR (cl:Changelog) ON (cl.version)",
                "CREATE INDEX changelog_date IF NOT EXISTS FOR (cl:Changelog) ON (cl.date)",
                "CREATE INDEX changelog_repository IF NOT EXISTS FOR (cl:Changelog) ON (cl.repository_id)"
            ]
            
            for index_query in changelog_indexes:
                try:
                    session.run(index_query)
                    logger.info(f"Created index: {index_query}")
                except Exception as e:
                    logger.warning(f"Index may already exist: {e}")


# Global connection instance
neo4j_conn = Neo4jConnection()
