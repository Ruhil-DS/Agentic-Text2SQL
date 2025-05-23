from app.db.mongo_client import mongo_client
from app.core.logger import app_logger
from app.services.llm_service import DEFAULT_SQL_GENERATION_PROMPT, DEFAULT_SUMMARY_PROMPT
from app.agents.sql_agent import DEFAULT_SQL_DEBUG_PROMPT

class PromptInitializer:
    """
    Utility to initialize default prompts in MongoDB
    """
    @staticmethod
    def initialize_default_prompts():
        """
        Initialize default prompts in MongoDB if they don't exist
        """
        app_logger.info("Initializing default prompts in MongoDB")
        
        # Define the default prompts
        default_prompts = [
            {
                "prompt_id": "sql_system_message",
                "prompt_text": DEFAULT_SQL_GENERATION_PROMPT,
                "description": "System message for SQL generation from natural language"
            },
            {
                "prompt_id": "sql_debug_system_message",
                "prompt_text": DEFAULT_SQL_DEBUG_PROMPT,
                "description": "System message for SQL debugging and fixing"
            },
            {
                "prompt_id": "result_summary_system_message",
                "prompt_text": DEFAULT_SUMMARY_PROMPT,
                "description": "System message for summarizing SQL query results"
            }
        ]
        
        # Insert or update each prompt
        for prompt in default_prompts:
            try:
                success = mongo_client.create_or_update_prompt(
                    prompt_id=prompt["prompt_id"],
                    prompt_text=prompt["prompt_text"],
                    is_default=True
                )
                
                if success:
                    app_logger.info(f"Default prompt '{prompt['prompt_id']}' initialized")
                else:
                    app_logger.warning(f"Failed to initialize default prompt '{prompt['prompt_id']}'")
            except Exception as e:
                app_logger.error(f"Error initializing prompt '{prompt['prompt_id']}': {str(e)}")
        
        app_logger.info("Default prompts initialization completed")
    
    @staticmethod
    def get_prompt_info():
        """
        Get information about available prompts
        """
        try:
            # Find all default prompts
            default_prompts = list(mongo_client.prompts_collection.find(
                {"is_default": True},
                {"_id": 0, "prompt_id": 1, "description": 1}
            ))
            
            # Find all customer-specific prompt counts
            customer_prompts = list(mongo_client.prompts_collection.aggregate([
                {"$match": {"customer_id": {"$exists": True}}},
                {"$group": {"_id": "$customer_id", "count": {"$sum": 1}}}
            ]))
            
            return {
                "default_prompts": default_prompts,
                "customer_prompts": customer_prompts
            }
        except Exception as e:
            app_logger.error(f"Error getting prompt info: {str(e)}")
            return {"error": str(e)}


# Create an instance
prompt_initializer = PromptInitializer() 