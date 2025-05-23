from app.core.logger import app_logger
from app.services.llm_service import llm_service
from app.agents.sql_agent import sql_agent
from app.db.postgres_client import postgres_client
from app.utils.mock_response import mock_response

class QueryService:
    def __init__(self):
        self.schema_info = None
        self.table_samples = {}
        self._load_schema_info()
    
    def _load_schema_info(self):
        """
        Load schema information from the database
        """
        try:
            self.schema_info = postgres_client.get_schema_info()
            app_logger.info("Schema information loaded successfully")
            
            # Load sample data for each table (for context)
            for table_name in self.schema_info.keys():
                sample = postgres_client.get_table_sample(table_name, limit=3)
                if sample:
                    self.table_samples[table_name] = sample
            
            app_logger.info(f"Loaded samples for {len(self.table_samples)} tables")
        except Exception as e:
            app_logger.error(f"Error loading schema information: {str(e)}")
            self.schema_info = {}
    
    def refresh_schema_info(self):
        """
        Refresh schema information (useful if database schema changes)
        """
        self._load_schema_info()
    
    def process_query(self, user_query, customer_id=None, openai_api_key=None):
        """
        Process a natural language query to SQL and return results
        
        Args:
            user_query: Natural language query from user
            customer_id: Optional customer ID for credential lookup
            openai_api_key: Optional OpenAI API key
            
        Returns:
            dict: Response with results and metadata
        """
        try:
            app_logger.info(f"Processing query: {user_query}")
            
            # Set customer_id for prompt retrieval
            llm_service.set_customer_id(customer_id)
            sql_agent.set_customer_id(customer_id)
            
            # Set OpenAI API key if provided
            if openai_api_key:
                llm_service.api_key = openai_api_key
                sql_agent.api_key = openai_api_key
            
            # Step 1: Generate SQL from user query
            
            generation_success, sql_result = llm_service.generate_sql_query(
                user_query, self.schema_info, self.table_samples
            )
            
            if not generation_success:
                app_logger.warning(f"SQL generation failed: {sql_result}")
                return mock_response.get_mock_response("sql_generation_failed", sql_result)
            
            # Step 2: Process the SQL through the SQL agent for validation and debugging
            processing_success, processed_sql = sql_agent.process_query(sql_result, self.schema_info)
            
            if not processing_success:
                app_logger.warning(f"SQL processing failed: {processed_sql}")
                return mock_response.get_mock_response("sql_validation_failed", processed_sql)
            
            # Step 3: Execute the validated SQL query
            try:
                query_results = postgres_client.execute_query(processed_sql)
                
                if not query_results:
                    app_logger.info("Query returned no results")
                    return mock_response.get_empty_results_response(processed_sql)
                
                # Step 4: Summarize the results
                summary = llm_service.summarize_query_results(user_query, processed_sql, query_results)
                
                # Prepare response
                response = {
                    "success": True,
                    "query": processed_sql,
                    "data": query_results,
                    "summary": summary,
                    "record_count": len(query_results)
                }
                
                app_logger.info(f"Query processed successfully, returned {len(query_results)} records")
                return response
                
            except Exception as e:
                app_logger.error(f"Error executing query: {str(e)}")
                
                # Try to debug the query with the execution error
                debug_success, debug_result = sql_agent.debug_query(
                    processed_sql, self.schema_info, str(e)
                )
                
                if debug_success:
                    try:
                        # Try executing the debugged query
                        query_results = postgres_client.execute_query(debug_result)
                        
                        if not query_results:
                            return mock_response.get_empty_results_response(debug_result)
                        
                        # Summarize the results
                        summary = llm_service.summarize_query_results(user_query, debug_result, query_results)
                        
                        # Prepare response
                        response = {
                            "success": True,
                            "query": debug_result,
                            "original_query": processed_sql,
                            "data": query_results,
                            "summary": summary,
                            "record_count": len(query_results),
                            "was_debugged": True
                        }
                        
                        app_logger.info(f"Query debugged and executed successfully")
                        return response
                    except Exception as debug_exec_error:
                        app_logger.error(f"Error executing debugged query: {str(debug_exec_error)}")
                
                return mock_response.get_mock_response("execution_error", str(e))
        
        except Exception as e:
            app_logger.error(f"Error in query processing: {str(e)}")
            return mock_response.get_mock_response("general_error", str(e))


# Create an instance
query_service = QueryService() 