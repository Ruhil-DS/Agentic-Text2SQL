from pymongo import MongoClient
from app.core.config import settings
from app.core.logger import app_logger
from datetime import datetime

class MongoDBClient:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoDBClient, cls).__new__(cls)
            cls._instance._init_connection()
        return cls._instance
    
    def _init_connection(self):
        try:
            # Log connection details for debugging
            app_logger.info(f"Connecting to MongoDB: URI={settings.MONGODB_URI[:10]}...{settings.MONGODB_URI[-10:]}, DB={settings.MONGODB_DB}, Collection={settings.CREDENTIALS_COLLECTION}")
            
            self.client = MongoClient(settings.MONGODB_URI)
            self.db = self.client[settings.MONGODB_DB]
            self.credentials_collection = self.db[settings.CREDENTIALS_COLLECTION]
            self.prompts_collection = self.db["prompts"]
            
            # List all collections for debugging
            collections = self.db.list_collection_names()
            app_logger.info(f"Available collections: {collections}")
            
            app_logger.info("MongoDB connection established")
        except Exception as e:
            app_logger.error(f"MongoDB connection error: {str(e)}")
            raise
    
    def get_credentials(self, customer_id):
        """
        Retrieve API credentials for a specific customer
        """
        try:
            app_logger.info(f"----------------")
            app_logger.info(f"Looking for customer ID: {customer_id}")
            
            credentials = self.credentials_collection.find_one({"customer_id": customer_id})
            
            # If credentials exist, verify OpenAI API key
            if credentials and "openai_api_key" in credentials:
                api_key = credentials["openai_api_key"]
                
                # Validate API key format
                if not api_key or not api_key.strip():
                    app_logger.warning(f"Empty API key found for {customer_id}")
            
            app_logger.info(f"cred found: {credentials is not None}")
            app_logger.info(f"--------------------")
            if not credentials:
                app_logger.warning(f"No credentials found for customer ID: {customer_id}")
                return None
            return credentials
        except Exception as e:
            app_logger.error(f"Error retrieving credentials: {str(e)}")
            return None
    
    def get_prompt(self, prompt_id, customer_id=None):
        """
        Retrieve a prompt by ID, with optional customer-specific override
        
        Args:
            prompt_id (str): The prompt identifier
            customer_id (str, optional): Customer ID for customer-specific prompts
            
        Returns:
            str: The prompt text or None if not found
        """
        try:
            # First try to get a customer-specific prompt if customer_id is provided
            if customer_id:
                customer_prompt = self.prompts_collection.find_one({
                    "prompt_id": prompt_id,
                    "customer_id": customer_id
                })
                if customer_prompt:
                    app_logger.info(f"Found customer-specific prompt: {prompt_id} for {customer_id}")
                    return customer_prompt["prompt_text"]
            
            # If no customer-specific prompt or no customer_id, get the default prompt
            default_prompt = self.prompts_collection.find_one({
                "prompt_id": prompt_id,
                "is_default": True
            })
            
            if default_prompt:
                app_logger.info(f"Found default prompt: {prompt_id}")
                return default_prompt["prompt_text"]
            
            app_logger.warning(f"No prompt found with ID: {prompt_id}")
            return None
        except Exception as e:
            app_logger.error(f"Error retrieving prompt: {str(e)}")
            return None
    
    def get_all_prompts_for_customer(self, customer_id):
        """
        Get all prompts available for a customer (including defaults)
        
        Args:
            customer_id (str): Customer ID
            
        Returns:
            dict: Dictionary of prompt_id -> prompt_text
        """
        try:
            # Get all default prompts
            default_prompts = list(self.prompts_collection.find({"is_default": True}))
            
            # Get all customer-specific prompts
            customer_prompts = list(self.prompts_collection.find({"customer_id": customer_id}))
            
            # Create a map of prompt_id -> prompt_text, customer prompts override defaults
            prompt_map = {p["prompt_id"]: p["prompt_text"] for p in default_prompts}
            prompt_map.update({p["prompt_id"]: p["prompt_text"] for p in customer_prompts})
            
            return prompt_map
        except Exception as e:
            app_logger.error(f"Error retrieving prompts for customer: {str(e)}")
            return {}
    
    def create_or_update_prompt(self, prompt_id, prompt_text, customer_id=None, is_default=False):
        """
        Create or update a prompt
        
        Args:
            prompt_id (str): The prompt identifier
            prompt_text (str): The prompt text
            customer_id (str, optional): Customer ID for customer-specific prompt
            is_default (bool): Whether this is a default prompt
            
        Returns:
            bool: Success status
        """
        try:
            query = {"prompt_id": prompt_id}
            if customer_id:
                query["customer_id"] = customer_id
            elif is_default:
                query["is_default"] = True
            
            update = {
                "$set": {
                    "prompt_text": prompt_text,
                    "updated_at": datetime.utcnow()
                }
            }
            
            if customer_id:
                update["$set"]["customer_id"] = customer_id
            
            if is_default:
                update["$set"]["is_default"] = True
            
            result = self.prompts_collection.update_one(
                query,
                update,
                upsert=True
            )
            
            if result.modified_count or result.upserted_id:
                app_logger.info(f"Prompt {prompt_id} created or updated successfully")
                return True
            
            app_logger.warning(f"No changes made to prompt {prompt_id}")
            return False
        except Exception as e:
            app_logger.error(f"Error creating/updating prompt: {str(e)}")
            return False
    
    def create_credentials(self, customer_id, openai_api_key, postgres_username=None, 
                           postgres_password=None, postgres_host=None, postgres_db=None):
        """
        Create new credentials for a customer
        """
        try:
            # Validate OpenAI API key
            if not openai_api_key or not openai_api_key.strip():
                app_logger.warning(f"Attempting to create customer {customer_id} with empty API key")
            elif not openai_api_key.startswith("sk-"):
                app_logger.warning(f"Attempting to create customer {customer_id} with invalid API key format")
                
            # Make sure API key has no whitespace
            openai_api_key = openai_api_key.strip() if openai_api_key else ""
            
            credential_data = {
                "customer_id": customer_id,
                "openai_api_key": openai_api_key,
                "postgres_connection": {
                    "username": postgres_username,
                    "password": postgres_password,
                    "host": postgres_host,
                    "database": postgres_db
                },
                "prompt_settings": {
                    "sql_system_message": None,
                    "sql_debug_system_message": None,
                    "result_summary_system_message": None
                }
            }
            
            result = self.credentials_collection.insert_one(credential_data)
            app_logger.info(f"Credentials created for customer ID: {customer_id}")
            return str(result.inserted_id)
        except Exception as e:
            app_logger.error(f"Error creating credentials: {str(e)}")
            return None
    
    def update_credentials(self, customer_id, **kwargs):
        """
        Update existing credentials
        """
        try:
            updates = {}
            
            for key, value in kwargs.items():
                if value is not None:
                    if key in ["openai_api_key"]:
                        updates[key] = value
                    elif key in ["postgres_username", "postgres_password", "postgres_host", "postgres_db"]:
                        field = key.replace("postgres_", "")
                        updates[f"postgres_connection.{field}"] = value
                    elif key.startswith("prompt_"):
                        prompt_key = key.replace("prompt_", "")
                        updates[f"prompt_settings.{prompt_key}"] = value
            
            if updates:
                self.credentials_collection.update_one(
                    {"customer_id": customer_id},
                    {"$set": updates}
                )
                app_logger.info(f"Credentials updated for customer ID: {customer_id}")
                return True
            return False
        except Exception as e:
            app_logger.error(f"Error updating credentials: {str(e)}")
            return False
    
    def delete_credentials(self, customer_id):
        """
        Delete credentials for a customer
        """
        try:
            result = self.credentials_collection.delete_one({"customer_id": customer_id})
            if result.deleted_count:
                app_logger.info(f"Credentials deleted for customer ID: {customer_id}")
                return True
            app_logger.warning(f"No credentials found to delete for customer ID: {customer_id}")
            return False
        except Exception as e:
            app_logger.error(f"Error deleting credentials: {str(e)}")
            return False
    
    def get_customer_prompt_settings(self, customer_id):
        """
        Get prompt settings for a customer
        
        Args:
            customer_id (str): Customer ID
            
        Returns:
            dict: Prompt settings or empty dict if not found
        """
        try:
            credentials = self.get_credentials(customer_id)
            if not credentials or "prompt_settings" not in credentials:
                return {}
            return credentials.get("prompt_settings", {})
        except Exception as e:
            app_logger.error(f"Error getting prompt settings: {str(e)}")
            return {}


# Create a singleton instance
mongo_client = MongoDBClient() 