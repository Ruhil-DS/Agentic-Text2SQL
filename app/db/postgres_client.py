import psycopg2
from sqlalchemy import create_engine, MetaData, Table, inspect
from psycopg2.extras import RealDictCursor
from app.core.config import settings
from app.core.logger import app_logger

class PostgreSQLClient:
    _instance = None
    
    def __new__(cls, connection_uri=None):
        if cls._instance is None:
            cls._instance = super(PostgreSQLClient, cls).__new__(cls)
            cls._instance._uri = connection_uri or settings.POSTGRES_URI
            cls._instance._init_connection()
        return cls._instance
    
    def _init_connection(self):
        try:
            self.engine = create_engine(self._uri)
            self.metadata = MetaData()
            self.metadata.reflect(bind=self.engine)
            app_logger.info("PostgreSQL connection established")
        except Exception as e:
            app_logger.error(f"PostgreSQL connection error: {str(e)}")
            raise
    
    def get_connection(self):
        """Get a psycopg2 connection for direct SQL execution"""
        try:
            conn = psycopg2.connect(self._uri)
            return conn
        except Exception as e:
            app_logger.error(f"Error creating psycopg2 connection: {str(e)}")
            raise
    
    def execute_query(self, query):
        """
        Execute a read-only SQL query and return results
        """
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(query)
            results = cursor.fetchall()
            conn.close()
            app_logger.info(f"Successfully executed query: {query[:100]}...")
            return results
        except Exception as e:
            app_logger.error(f"Error executing query: {str(e)}")
            if conn:
                conn.close()
            raise
    
    def get_schema_info(self):
        """
        Get the database schema information
        """
        try:
            inspector = inspect(self.engine)
            schema_info = {}
            
            for table_name in inspector.get_table_names():
                columns = []
                for column in inspector.get_columns(table_name):
                    columns.append({
                        "name": column["name"],
                        "type": str(column["type"]),
                        "nullable": column.get("nullable", True)
                    })
                
                # In SQLAlchemy 2.0+, get_primary_keys has been replaced with get_pk_constraint
                try:
                    # Try the SQLAlchemy 2.0+ method
                    pk_constraint = inspector.get_pk_constraint(table_name)
                    primary_keys = pk_constraint.get("constrained_columns", [])
                except (AttributeError, NotImplementedError):
                    # Fall back to direct query for primary keys
                    primary_keys = self._get_primary_keys_fallback(table_name)
                
                foreign_keys = []
                
                # Get foreign keys
                try:
                    for fk in inspector.get_foreign_keys(table_name):
                        foreign_keys.append({
                            "constrained_columns": fk["constrained_columns"],
                            "referred_table": fk["referred_table"],
                            "referred_columns": fk["referred_columns"]
                        })
                except (AttributeError, NotImplementedError):
                    # Fall back to direct query for foreign keys if needed
                    foreign_keys = self._get_foreign_keys_fallback(table_name)
                
                schema_info[table_name] = {
                    "columns": columns,
                    "primary_keys": primary_keys,
                    "foreign_keys": foreign_keys
                }
            
            app_logger.info("Successfully retrieved schema information")
            return schema_info
        except Exception as e:
            app_logger.error(f"Error getting schema info: {str(e)}")
            raise
    
    def _get_primary_keys_fallback(self, table_name):
        """
        Fallback method to get primary keys using direct SQL query
        """
        try:
            query = """
            SELECT a.attname
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = %s::regclass AND i.indisprimary
            """
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(query, (table_name,))
            primary_keys = [row[0] for row in cursor.fetchall()]
            conn.close()
            return primary_keys
        except Exception as e:
            app_logger.error(f"Error getting primary keys for {table_name}: {str(e)}")
            return []
    
    def _get_foreign_keys_fallback(self, table_name):
        """
        Fallback method to get foreign keys using direct SQL query
        """
        try:
            query = """
            SELECT
                kcu.column_name as constrained_column,
                ccu.table_name as referred_table,
                ccu.column_name as referred_column
            FROM
                information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name = %s
            """
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(query, (table_name,))
            
            foreign_keys = []
            temp_dict = {}
            
            for row in cursor.fetchall():
                constrained_column = row[0]
                referred_table = row[1]
                referred_column = row[2]
                
                key = f"{referred_table}"
                if key not in temp_dict:
                    temp_dict[key] = {
                        "constrained_columns": [],
                        "referred_table": referred_table,
                        "referred_columns": []
                    }
                
                temp_dict[key]["constrained_columns"].append(constrained_column)
                temp_dict[key]["referred_columns"].append(referred_column)
            
            foreign_keys = list(temp_dict.values())
            conn.close()
            return foreign_keys
        except Exception as e:
            app_logger.error(f"Error getting foreign keys for {table_name}: {str(e)}")
            return []
    
    def get_table_sample(self, table_name, limit=5):
        """
        Get a sample of data from a table
        """
        try:
            query = f"SELECT * FROM {table_name} LIMIT {limit}"
            sample = self.execute_query(query)
            return sample
        except Exception as e:
            app_logger.error(f"Error getting table sample: {str(e)}")
            return []


# Create a singleton instance
postgres_client = PostgreSQLClient() 