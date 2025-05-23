from app.core.logger import app_logger

class MockResponseGenerator:
    def __init__(self):
        self.error_responses = {
            "sql_generation_failed": "I couldn't generate a valid SQL query for your question. Please try rephrasing or providing more context.",
            "sql_validation_failed": "The generated SQL query doesn't meet security requirements. Only read-only queries are allowed.",
            "database_connection_error": "There was an issue connecting to the database. Please try again later.",
            "execution_error": "An error occurred while executing the query. Please check your question for clarity.",
            "insufficient_permissions": "You don't have permission to access this information.",
            "empty_results": "The query executed successfully but returned no results.",
            "summarization_failed": "I couldn't generate a summary for the query results.",
            "general_error": "An unexpected error occurred. Please try again later."
        }
    
    def get_mock_response(self, error_type, custom_message=None):
        """
        Get a mock response for a specific error type
        
        Args:
            error_type: Type of error
            custom_message: Optional custom message to override default
            
        Returns:
            dict: Response with error info
        """
        app_logger.warning(f"Generating mock response for error: {error_type}")
        
        error_message = custom_message if custom_message else self.error_responses.get(
            error_type, self.error_responses["general_error"]
        )
        
        response = {
            "success": False,
            "error": {
                "type": error_type,
                "message": error_message
            },
            "mock": True,
            "data": None
        }
        
        return response
    
    def get_empty_results_response(self, query=None):
        """
        Get a mock response for empty results
        """
        app_logger.info("Generating empty results response")
        
        response = {
            "success": True,
            "message": "Query executed successfully but returned no results.",
            "query": query,
            "data": [],
            "summary": "No data was found for your query."
        }
        
        return response


# Create an instance
mock_response = MockResponseGenerator() 