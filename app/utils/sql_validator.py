import sqlparse
from app.core.config import settings
from app.core.logger import app_logger

class SQLValidator:
    def __init__(self):
        self.allowed_keywords = set(settings.ALLOWED_SQL_KEYWORDS)
        self.blocked_keywords = set(settings.BLOCKED_SQL_KEYWORDS)
    
    def is_read_only(self, query):
        """
        Check if the query is read-only (SELECT only)
        """
        try:
            # Parse the SQL query
            parsed = sqlparse.parse(query)
            if not parsed:
                app_logger.warning("Empty or invalid SQL query")
                return False
            
            # Get the first statement
            stmt = parsed[0]
            
            # Check if it's a SELECT statement
            if stmt.get_type() != 'SELECT':
                app_logger.warning(f"Non-SELECT statement detected: {stmt.get_type()}")
                return False
            
            return True
        except Exception as e:
            app_logger.error(f"Error checking if query is read-only: {str(e)}")
            return False
    
    def has_blocked_keywords(self, query):
        """
        Check if the query contains any blocked keywords
        """
        try:
            query_upper = query.upper()
            
            for keyword in self.blocked_keywords:
                # Check with word boundaries to avoid false positives
                if f" {keyword} " in f" {query_upper} ":
                    app_logger.warning(f"Blocked keyword detected: {keyword}")
                    return True
            
            return False
        except Exception as e:
            app_logger.error(f"Error checking for blocked keywords: {str(e)}")
            return True  # Fail safe
    
    def validate_query(self, query):
        """
        Validate an SQL query for safety
        
        Returns:
            tuple: (is_valid, error_message)
        """
        try:
            # Check if the query is empty
            if not query or not query.strip():
                return False, "Empty query"
            
            # Check for read-only property
            if not self.is_read_only(query):
                return False, "Only SELECT queries are allowed"
            
            # Check for blocked keywords
            if self.has_blocked_keywords(query):
                return False, "Query contains disallowed keywords"
            
            # Additional checks can be added here
            
            return True, None
        except Exception as e:
            app_logger.error(f"Error validating SQL query: {str(e)}")
            return False, f"Validation error: {str(e)}"
    
    def validate_and_sanitize(self, query):
        """
        Validate and sanitize a query
        
        Returns:
            tuple: (is_valid, sanitized_query or error_message)
        """
        is_valid, error = self.validate_query(query)
        
        if not is_valid:
            return False, error
        
        # Add any additional sanitization steps here
        sanitized_query = query
        
        return True, sanitized_query


# Create an instance
sql_validator = SQLValidator() 