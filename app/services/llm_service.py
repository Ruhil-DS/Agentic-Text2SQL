from pydantic import BaseModel, Field
from typing import Optional
import json
from openai import OpenAI
from app.core.config import settings
from app.core.logger import app_logger
from app.utils.mock_response import mock_response
from app.db.mongo_client import mongo_client
from app.utils import json_utils

class SQLQueryOutput(BaseModel):
    """Output schema for SQL query generation"""
    query: str = Field(description="The SQL query to execute")
    error: Optional[str] = Field(description="Error message if unable to generate a valid query", default=None)

# Default prompts if not found in MongoDB
DEFAULT_SQL_GENERATION_PROMPT = """You are an expert SQL assistant that converts natural language queries into PostgreSQL queries.
Given the database schema and examples of data, generate a valid PostgreSQL SELECT query.
Follow these rules strictly:
1. ONLY generate SELECT queries - never write, update or delete operations
2. Use proper PostgreSQL syntax and table/column names exactly as shown in the schema
3. Include appropriate JOINs when needed based on the schema relationships
4. If you cannot generate a valid query, provide a clear error message
5. Never make assumptions about the schema, only use what is provided

The database schema is as follows:
{schema}

{samples}"""

DEFAULT_SUMMARY_PROMPT = """You are an expert data analyst that summarizes SQL query results.
Your task is to provide a clear, concise summary of the query results in natural language.
Focus on key findings, patterns, and the most relevant information that answers the user's original question.
Keep the summary simple, direct, and to the point."""

class LLMService:
    def __init__(self, api_key=None, customer_id=None):
        self.customer_id = customer_id
        # Store the initial API key (could be from settings or direct arg)
        # This will be used as a fallback if customer-specific key isn't found
        self._initial_api_key = api_key or settings.OPENAI_API_KEY
        self.model_name = settings.LLM_MODEL
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
                app_logger.info(f"Using customer-specific OpenAI API key for: {self.customer_id}")

        if not key_to_use:
            key_to_use = self._initial_api_key
            if key_to_use:
                key_source = "global settings"
                app_logger.info(f"Using API key from global settings.")
            else:
                key_source = "fallback (none found)"

        if not key_to_use or key_to_use.strip() == "":
            app_logger.error("OpenAI API key is missing from all sources (customer-specific and global).")
            raise ValueError("OpenAI API key is required.")

        if not key_to_use.startswith("sk-"):
            app_logger.warning(f"API key from {key_source} may be invalid, doesn't start with 'sk-'.")

        return key_to_use.strip()

    def _get_or_initialize_client(self):
        """Initializes the OpenAI client if not already, or if API key context changed."""
        resolved_api_key = self._resolve_api_key() # This will raise ValueError if no key

        if self.client and self.current_api_key_in_use == resolved_api_key:
            return self.client

        app_logger.info(f"Initializing OpenAI client with API key: {resolved_api_key[:6]}...")
        try:
            self.client = OpenAI(api_key=resolved_api_key)
            self.current_api_key_in_use = resolved_api_key
            app_logger.info(f"LLM service client initialized/updated with model: {self.model_name}")
        except Exception as e:
            app_logger.error(f"Error initializing OpenAI client: {str(e)}")
            self.client = None
            self.current_api_key_in_use = None
            app_logger.error(f"Failed to initialize OpenAI client while resolving API key from {self.customer_id or 'global settings'}.")
            raise Exception(f"Failed to initialize OpenAI client: {str(e)}")
        app_logger.info(f"OpenAI client initialized successfully with API key source.")
        return self.client

    def get_sql_generation_prompt(self, schema_info, table_samples):
        """
        Get SQL generation prompt from MongoDB or use default
        """
        prompt_id = "sql_system_message"
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
            app_logger.warning(f"No SQL generation prompt found in MongoDB, using default")
            prompt_text = DEFAULT_SQL_GENERATION_PROMPT
        
        # Format the prompt with schema and samples
        schema_str = json_utils.dumps(schema_info, indent=2)
        
        # Format table samples if provided
        samples_str = ""
        if table_samples:
            samples_str = "Here are some examples of the data:\n"
            for table, samples in table_samples.items():
                samples_str += f"\nTable: {table}\n"
                samples_str += json_utils.dumps(samples, indent=2)[:500] + "...\n"
        
        formatted_prompt = prompt_text.format(schema=schema_str, samples=samples_str)
        return formatted_prompt
    
    def get_summary_prompt(self):
        """
        Get summary prompt from MongoDB or use default
        """
        prompt_id = "result_summary_system_message"
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
            app_logger.warning(f"No summary prompt found in MongoDB, using default")
            prompt_text = DEFAULT_SUMMARY_PROMPT
        
        return prompt_text
    
    def generate_sql_query(self, user_query, schema_info, table_samples=None):
        """
        Generate an SQL query based on user input and database schema
        
        Args:
            user_query: Natural language query from user
            schema_info: Database schema information
            table_samples: Sample data from tables (optional)
            
        Returns:
            tuple: (success, query or error_message)
        """
        try:
            self._get_or_initialize_client() # Ensures client is ready and self.client is set

            app_logger.info(f"Generating SQL for query: {user_query}")
            
            # Get system message from MongoDB
            system_message = self.get_sql_generation_prompt(schema_info, table_samples)
            app_logger.info(f"------\nsyst msg: {system_message[:100]}\n--------")
            
            functions = [
                {
                    "name": "generate_sql_query",
                    "description": "Generate a PostgreSQL query from natural language",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The SQL query to execute"
                            },
                            "error": {
                                "type": "string",
                                "description": "Error message if unable to generate a valid query"
                            }
                        },
                        "required": ["query"]
                    }
                }
            ]
            
            # Create the messages for the chat
            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_query}
            ]
            
            app_logger.info(f"Using OpenAI model: {self.model_name}")
            
            try:
                # Make the API call with function calling using the new client pattern
                app_logger.info(f"Attempting API call to OpenAI...")
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    tools=[{"type": "function", "function": f} for f in functions],
                    tool_choice={"type": "function", "function": {"name": "generate_sql_query"}}
                )
                app_logger.info(f"------\nOpenAI response received\n--------")
            except Exception as model_error:
                app_logger.error(f"Error with model {self.model_name}: {str(model_error)}")
                # If the first attempt fails, try with a fallback model
                if self.model_name != "gpt-4":
                    app_logger.info(f"Attempting fallback with gpt-4...")
                    response = self.client.chat.completions.create(
                        model="gpt-4",
                        messages=messages,
                        tools=[{"type": "function", "function": f} for f in functions],
                        tool_choice={"type": "function", "function": {"name": "generate_sql_query"}}
                    )
                    app_logger.info(f"Fallback successful")
                else:
                    raise model_error
            
            app_logger.info(f"------\nresp: {response}\n--------")
            
            # Extract the function call response
            tool_calls = response.choices[0].message.tool_calls
            if tool_calls and tool_calls[0].function.name == "generate_sql_query":
                arguments = json_utils.loads(tool_calls[0].function.arguments)
                sql_query = arguments.get("query", "")
                error = arguments.get("error")
                
                if error:
                    app_logger.warning(f"LLM returned error: {error}")
                    return False, error
                
                if not sql_query:
                    app_logger.warning("Empty SQL query returned")
                    return False, "Generated SQL query is empty"
                
                app_logger.info(f"Successfully generated SQL query: {sql_query[:100]}...")
                return True, sql_query
            else:
                app_logger.warning("No function call in response")
                return False, "Failed to generate SQL query"
                
        except Exception as e:
            app_logger.error(f"Error generating SQL query: {str(e)}")
            app_logger.error(f"Error type: {type(e).__name__}")
            app_logger.error(f"Error details: {repr(e)}")
            import traceback
            app_logger.error(f"Traceback: {traceback.format_exc()}")
            return False, f"Error: {str(e)}"
    
    def summarize_query_results(self, user_query, sql_query, results, max_rows=10):
        """
        Summarize the SQL query results in natural language
        
        Args:
            user_query: Original user question
            sql_query: Executed SQL query
            results: Query results
            max_rows: Maximum number of rows to display in markdown table (default: 10)
            
        Returns:
            str: Natural language summary of results with markdown formatted table
        """
        try:
            self._get_or_initialize_client() # Ensures client is ready and self.client is set

            app_logger.info("Summarizing query results")
            
            # If no results, return simple message
            if not results or len(results) == 0:
                return "The query returned no results."
            
            # Format the results for the prompt
            results_str = json_utils.dumps(results[:10], indent=2)
            if len(results) > 10:
                results_str += f"\n... and {len(results) - 10} more rows"
            
            # Get system message from MongoDB
            system_message = self.get_summary_prompt()
            
            # Create the messages for the chat
            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": f"""Original question: {user_query}
SQL query executed: {sql_query}
Query results: {results_str}

Please summarize these results to answer the original question."""}
            ]
            
            # Make the API call with the new client pattern
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
            )
            
            summary = response.choices[0].message.content.strip()
            app_logger.info("Successfully generated results summary")
            
            # Format results to markdown
            markdown_data = self.format_results_to_markdown(results, max_rows)
            total_rows = markdown_data["total_rows"]
            displayed_rows = markdown_data["displayed_rows"]
            markdown_results = markdown_data["markdown_results"]
            
            # Check if there was an error in formatting
            if "error" in markdown_data:
                app_logger.warning(f"Error in markdown formatting: {markdown_data['error']}")
                # Fallback to simple string representation
                summary += f"\n\nHere are the results (could not format as table due to error):\n{results[:max_rows]}"
            else:
                # Append appropriate message based on row count
                if total_rows > displayed_rows:
                    summary += f"\n\nHere are the top {displayed_rows} results out of {total_rows} total rows:\n\n{markdown_results}"
                else:
                    summary += f"\n\nHere are all {total_rows} results:\n\n{markdown_results}"
                
            return summary
            
        except Exception as e:
            app_logger.error(f"Error summarizing query results: {str(e)}")
            return mock_response.get_mock_response("summarization_failed")["error"]["message"]
    
    def format_results_to_markdown(self, results, max_rows=10):
        """
        Format SQL query results to a markdown table
        
        Args:
            results: Query results from database
            max_rows: Maximum number of rows to include in markdown (default: 10)
            
        Returns:
            dict: Dictionary with markdown formatted table and metadata
                {
                    "markdown_results": Formatted markdown table string,
                    "total_rows": Total number of rows in the results,
                    "displayed_rows": Number of rows included in the markdown
                }
        """
        try:
            total_rows = len(results)
            
            if total_rows == 0:
                return {
                    "markdown_results": "No results found",
                    "total_rows": 0,
                    "displayed_rows": 0
                }
            
            # Limit results to max_rows
            display_results = results[:max_rows]
            displayed_rows = len(display_results)
            
            # Get all possible column names across all results (in case results have different structures)
            columns = []
            for row in display_results:
                for key in row.keys():
                    if key not in columns:
                        columns.append(key)
            
            # If no columns found (shouldn't happen, but just in case)
            if not columns:
                return {
                    "markdown_results": "Results structure could not be determined",
                    "total_rows": total_rows,
                    "displayed_rows": 0
                }
            
            # Create markdown header
            markdown = "| " + " | ".join(columns) + " |\n"
            markdown += "| " + " | ".join(["---" for _ in columns]) + " |\n"
            
            # Add rows
            for row in display_results:
                # Format values, ensuring strings are properly escaped for markdown
                values = []
                for col in columns:
                    # Check if the column exists in this row
                    if col in row:
                        val = row[col]
                        # Convert None to empty string
                        if val is None:
                            val = ""
                        # If value has pipes or newlines, wrap in backticks
                        elif isinstance(val, str) and ('|' in val or '\n' in val):
                            val = f"`{val}`"
                        values.append(str(val))
                    else:
                        # Column doesn't exist in this row
                        values.append("")
                
                markdown += "| " + " | ".join(values) + " |\n"
            return {
                "markdown_results": markdown,
                "total_rows": total_rows,
                "displayed_rows": displayed_rows
            }
            
        except Exception as e:
            app_logger.error(f"Error formatting results to markdown: {str(e)}")
            return {
                "markdown_results": "Error formatting results",
                "total_rows": len(results) if results else 0,
                "displayed_rows": 0,
                "error": str(e)
            }
    
    def set_customer_id(self, customer_id):
        """Set the customer ID. This may cause the client to re-initialize on next use."""
        if self.customer_id != customer_id:
            self.customer_id = customer_id
            # Reset client so it gets re-initialized with potentially new API key
            self.client = None
            self.current_api_key_in_use = None
            app_logger.info(f"Customer ID set to {customer_id}. OpenAI client will re-evaluate API key on next use.")


# Create a default instance
llm_service = LLMService()