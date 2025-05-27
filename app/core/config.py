import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings(BaseSettings):
    # API settings
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Agentic Text2SQL"
    
    # MongoDB settings
    MONGODB_URI: str = os.getenv("MONGODB_URI")
    MONGODB_DB: str = os.getenv("MONGODB_DB")
    CREDENTIALS_COLLECTION: str = os.getenv("CREDENTIALS_COLLECTION")
    
    # PostgreSQL settings
    POSTGRES_URI: str = os.getenv("POSTGRES_URI", None)
    
    # OpenAI settings
    # from the customer's credentials in MongoDB for each request.
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o")
    
    # Security settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", None)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    
    # SQL Safety settings
    ALLOWED_SQL_KEYWORDS: list = ["SELECT", "FROM", "WHERE", "JOIN", "INNER JOIN", "LEFT JOIN", "RIGHT JOIN",
                                  "GROUP BY", "HAVING", "ORDER BY", "LIMIT", "OFFSET", "WITH"]
    BLOCKED_SQL_KEYWORDS: list = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE", "GRANT",
                                 "REVOKE", "COMMIT", "ROLLBACK"]

    class Config:
        case_sensitive = True


settings = Settings() 