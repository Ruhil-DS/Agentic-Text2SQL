import re
import json
from openai import OpenAI
import sqlparse
from app.db.postgres_client import postgres_client
from app.core.config import settings
from app.core.logger import app_logger
from app.db.mongo_client import mongo_client
from app.utils import json_utils

# Default debug prompt (fallback if MongoDB is unavailable)
DEFAULT_SQL_DEBUG_PROMPT = """You are an expert SQL debugging agent. Your task is to analyze a broken SQL query 
and fix any issues while ensuring it remains a read-only SELECT query.

The database schema is:
{schema}

When fixing queries, follow these rules:
1. Only fix the query if you're confident in the solution
2. ONLY generate SELECT queries - never modify to include writes/updates/deletes
3. Maintain the original intent of the query
4. Fix syntax errors, type casting issues, and schema compliance problems
5. Use proper PostgreSQL syntax
6. If you can't fix the query, provide a clear error message explaining why

The original query failed with this error: {error}"""

class SQLAgent:
    def __init__(self, api_key=None, customer_id=None):
        # Store the initial API key (could be from settings or direct arg)
        # This will be used as a fallback if customer-specific key isn't found
        self._initial_api_key = api_key or settings.OPENAI_API_KEY
        self.model_name = settings.LLM_MODEL
        self.customer_id = customer_id
        self.client = None # Initialize client as None
        self.current_api_key_in_use = None # To track which key initialized the client

    def _resolve_api_key(self):
        """Resolves the API key to be used, prioritizing customer-specific key."""
        key_to_use = None
        key_source = "unknown"

        if self.customer_id:
            customer = mongo_client.get_credentials(self.customer_id)
            if customer and "openai_api_key" in customer and customer["openai_api_key"]:
                key_to_use = customer["openai_api_key"]
                key_source = f"customer ({self.customer_id})"
                app_logger.info(f"SQLAgent: Using customer-specific OpenAI API key for: {self.customer_id}")

        if not key_to_use:
            key_to_use = self._initial_api_key
            if key_to_use:
                key_source = "global settings"
                app_logger.info(f"SQLAgent: Using API key from global settings.")
            else:
                key_source = "fallback (none found)"

        if not key_to_use or key_to_use.strip() == "":
            app_logger.error("SQLAgent: OpenAI API key is missing from all sources (customer-specific and global).")
            raise ValueError("OpenAI API key is required for SQLAgent.")

        if not key_to_use.startswith("sk-"):
            app_logger.warning(f"SQLAgent: API key from {key_source} may be invalid, doesn't start with 'sk-'.")

        return key_to_use.strip()

    def _get_or_initialize_client(self):
        """Initializes the OpenAI client if not already, or if API key context changed."""
        resolved_api_key = self._resolve_api_key() # This will raise ValueError if no key

        if self.client and self.current_api_key_in_use == resolved_api_key:
            return self.client

        app_logger.info(f"SQLAgent: Initializing OpenAI client with API key: {resolved_api_key[:8]}...")
        try:
            self.client = OpenAI(api_key=resolved_api_key)
            self.current_api_key_in_use = resolved_api_key
            app_logger.info(f"SQLAgent: OpenAI client initialized/updated with model: {self.model_name}")
        except Exception as e:
            app_logger.error(f"SQLAgent: Error initializing OpenAI client: {str(e)}")
            self.client = None
            self.current_api_key_in_use = None
            raise
        return self.client

    def validate_query(self, query):
        """
        Validate an SQL query for safety and correctness
        """
        # Standardize query for validation
        try:
            # Parse the query
            parsed = sqlparse.parse(query.strip())
            if not parsed:
                return False, "Empty or invalid SQL query"
            
            # Get the first statement // we don't allow multiple statements
            stmt = parsed[0]
            
            # Check that it's a SELECT statement
            if not stmt.get_type() or stmt.get_type().upper() != 'SELECT':
                return False, "Only SELECT queries are allowed"
            
            # Check for disallowed SQL keywords
            for keyword in settings.BLOCKED_SQL_KEYWORDS:
                if re.search(r'\b' + keyword + r'\b', query, re.IGNORECASE):
                    return False, f"Disallowed SQL keyword found: {keyword}"
            
            return True, "Query validation successful"
        except Exception as e:
            app_logger.error(f"Error validating query: {str(e)}")
            return False, f"Validation error: {str(e)}"
    
    def get_debug_prompt(self, schema_info, error_message):
        """
        Get debugging prompt from MongoDB or use default
        """
        prompt_id = "sql_debug_system_message"
        prompt_text = None
        
        # First try to get from customer prompt settings
        if self.customer_id:
            prompt_settings = mongo_client.get_customer_prompt_settings(self.customer_id)
            prompt_text = prompt_settings.get(prompt_id)
        
        # If not found, try the generic prompt collection
        if not prompt_text:
            prompt_text = mongo_client.get_prompt(prompt_id, self.customer_id)
        
        # If still not found, use default
        if not prompt_text:
            app_logger.warning(f"No debug prompt found in MongoDB, using default")
            prompt_text = DEFAULT_SQL_DEBUG_PROMPT
        
        # Format the prompt with schema and error
        schema_str = json_utils.dumps(schema_info, indent=2)
        formatted_prompt = prompt_text.format(schema=schema_str, error=error_message)
        
        return formatted_prompt
    
    def debug_query(self, query, schema_info, error_message):
        """
        Debug a failed SQL query and try to fix it
        
        Args:
            query: The original SQL query
            schema_info: Database schema information
            error_message: Error message from the failed execution
            
        Returns:
            tuple: (success, fixed_query or error_message)
        """
        try:
            self._get_or_initialize_client() # Ensures client is ready

            app_logger.info(f"Attempting to debug SQL query: {query[:100]}...")
            
            # Get system message from MongoDB
            system_message = self.get_debug_prompt(schema_info, error_message)
            app_logger.info(f"Debug system message retrieved")
            
            functions = [
                {
                    "name": "fix_sql_query",
                    "description": "Fix a broken SQL query",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "fixed_query": {
                                "type": "string",
                                "description": "The fixed SQL query"
                            },
                            "explanation": {
                                "type": "string",
                                "description": "Explanation of what was fixed"
                            },
                            "error": {
                                "type": "string",
                                "description": "Error message if unable to fix the query"
                            }
                        },
                        "required": ["fixed_query", "explanation"]
                    }
                }
            ]
            
            # Create the messages for the chat
            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": f"Fix this SQL query: {query}"}
            ]
            
            # Make the API call with function calling - using the new client pattern
            app_logger.info(f"Sending debug request to OpenAI API with model: {self.model_name}")
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    tools=[{"type": "function", "function": f} for f in functions],
                    tool_choice={"type": "function", "function": {"name": "fix_sql_query"}}
                )
                app_logger.info(f"Debug API call successful")
            except Exception as model_error:
                app_logger.error(f"Error with model {self.model_name}: {str(model_error)}")
                # If the first attempt fails, try with a fallback model
                if self.model_name != "gpt-3.5-turbo":
                    app_logger.info(f"Attempting fallback with gpt-3.5-turbo...")
                    response = self.client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=messages,
                        tools=[{"type": "function", "function": f} for f in functions],
                        tool_choice={"type": "function", "function": {"name": "fix_sql_query"}}
                    )
                    app_logger.info(f"Fallback successful")
                else:
                    raise model_error
            
            # Extract the function call response
            tool_calls = response.choices[0].message.tool_calls
            if tool_calls and tool_calls[0].function.name == "fix_sql_query":
                arguments = json_utils.loads(tool_calls[0].function.arguments)
                fixed_query = arguments.get("fixed_query", "")
                explanation = arguments.get("explanation", "")
                error = arguments.get("error")
                
                if error:
                    app_logger.warning(f"Agent couldn't fix query: {error}")
                    return False, error
                
                if not fixed_query:
                    app_logger.warning("Empty fixed query returned")
                    return False, "Failed to generate a fixed query"
                
                # Validate the fixed query
                is_valid, validation_result = self.validate_query(fixed_query)
                if not is_valid:
                    app_logger.warning(f"Fixed query validation failed: {validation_result}")
                    return False, validation_result
                
                app_logger.info(f"Query fixed successfully: {fixed_query[:100]}\nExplanation: ({explanation})")
                return True, fixed_query
            else:
                app_logger.warning("No function call in response")
                return False, "Failed to debug query"
                
        except Exception as e:
            app_logger.error(f"Error debugging SQL query: {str(e)}")
            app_logger.error(f"Error type: {type(e).__name__}")
            app_logger.error(f"Error details: {repr(e)}")
            import traceback
            app_logger.error(f"Traceback: {traceback.format_exc()}")
            return False, f"Debugging error: {str(e)}"
    
    def detect_and_fix_common_issues(self, query, schema_info):
        """
        Detect and fix common issues in SQL queries without using LLM
        
        Args:
            query: SQL query to check
            schema_info: Database schema information
            
        Returns:
            tuple: (modified_query, was_modified)
        """
        modified_query = query
        was_modified = False
        
        # Fix 1: Missing quotes around string literals
        def add_quotes_to_strings(match):
            # nonlocal to modify the outer scope variable and not the global one
            # The nonlocal keyword is used to indicate that a variable belongs to the 
            # nearest enclosing scope (outside the current function but not global).
            nonlocal was_modified
            was_modified = True
            return f"= '{match.group(1)}'"
        
        string_pattern = r"= ([a-zA-Z0-9_]+)(?!\s*\(|\s*'|\s*\d|\s*::)"
        modified_query = re.sub(string_pattern, add_quotes_to_strings, modified_query)
        
        # Fix 2: Fix incorrect table names if we can clearly identify them
        for table_name in schema_info.keys():
            # Check for slight misspellings or case issues (simple example)
            pattern = r'\b' + re.escape(table_name) + r'[s]?\b'
            for match in re.finditer(pattern, modified_query, re.IGNORECASE):
                if match.group(0) != table_name:
                    modified_query = modified_query.replace(match.group(0), table_name)
                    was_modified = True
        
        if was_modified:
            app_logger.info(f"Automatically fixed common issues in query")
        
        return modified_query, was_modified
    
    def process_query(self, query, schema_info):
        """
        Process an SQL query through validation and debugging if needed
        
        Args:
            query: The SQL query to process
            schema_info: Database schema information
            
        Returns:
            tuple: (success, processed_query or error_message)
        """
        # First try to fix common issues automatically
        fixed_query, was_modified = self.detect_and_fix_common_issues(query, schema_info)
        if was_modified:
            app_logger.info(f"---------------\nOriginal SQL query: {query}\n---------------")
            app_logger.info(f"---------------\nFixed SQL query: {fixed_query}\n---------------")
            query = fixed_query
            
        # Validate the query for safety and correctness
        is_valid, validation_result = self.validate_query(query)
        if is_valid:
            return True, query
        
        # If validation failed, attempt to debug and fix
        app_logger.info(f"Validation failed: {validation_result}. Attempting to debug.")
        
        # Try running the query to get a more specific error
        try:
            postgres_client.execute_query(query)
            # If we reach here, the query actually ran despite validation failure
            # This shouldn't happen normally, but just in case
            # THIS IS POTENTIALLY DANGEROUS - What if we execute a harmful query?
            app_logger.warning(f"Query passed execution but failed validation: {validation_result}")
            return True, query
        except Exception as exec_error:
            # Debug with the execution error
            debug_success, debug_result = self.debug_query(query, schema_info, str(exec_error))
            if debug_success:
                # Validate the fixed query one more time
                is_valid, validation_result = self.validate_query(debug_result)
                if is_valid:
                    return True, debug_result
            
            return False, debug_result if debug_success else validation_result
    
    def set_customer_id(self, customer_id):
        """Set the customer ID. This may cause the client to re-initialize on next use."""
        if self.customer_id != customer_id:
            self.customer_id = customer_id
            # Reset client so it gets re-initialized with potentially new API key
            self.client = None
            self.current_api_key_in_use = None
            app_logger.info(f"SQLAgent: Customer ID set to {customer_id}. OpenAI client will re-evaluate API key on next use.")



# Create an instance
sql_agent = SQLAgent()
 