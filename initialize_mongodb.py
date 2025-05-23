#!/usr/bin/env python
import pymongo
from pymongo import MongoClient
from datetime import datetime
import json
import os
import secrets

# MongoDB connection settings
MONGO_URI = ""
DB_NAME = "text2sql"

# Default system prompts
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

DEFAULT_SUMMARY_PROMPT = """You are an expert data analyst that summarizes SQL query results.
Your task is to provide a clear, concise summary of the query results in natural language.
Focus on key findings, patterns, and the most relevant information that answers the user's original question.
Keep the summary simple, direct, and to the point."""


def initialize_mongodb():
    """Initialize MongoDB with necessary collections and default data"""
    try:
        # Connect to MongoDB
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        
        print(f"Connected to MongoDB database: {DB_NAME}")
        
        # Create collections if they don't exist
        if "credentials" not in db.list_collection_names():
            db.create_collection("credentials")
            print("Created 'credentials' collection")
        
        if "prompts" not in db.list_collection_names():
            db.create_collection("prompts")
            print("Created 'prompts' collection")
        
        # Initialize default prompts
        initialize_default_prompts(db)
        
        # Create a test customer if needed
        create_test_customer(db)
        
        print("MongoDB initialization completed successfully")
        
    except Exception as e:
        print(f"Error initializing MongoDB: {str(e)}")


def initialize_default_prompts(db):
    """Initialize default prompts in the prompts collection"""
    prompts_collection = db["prompts"]
    
    # Define default prompts
    default_prompts = [
        {
            "prompt_id": "sql_system_message",
            "prompt_text": DEFAULT_SQL_GENERATION_PROMPT,
            "description": "System message for SQL generation from natural language",
            "is_default": True,
            "updated_at": datetime.utcnow()
        },
        {
            "prompt_id": "sql_debug_system_message",
            "prompt_text": DEFAULT_SQL_DEBUG_PROMPT,
            "description": "System message for SQL debugging and fixing",
            "is_default": True,
            "updated_at": datetime.utcnow()
        },
        {
            "prompt_id": "result_summary_system_message",
            "prompt_text": DEFAULT_SUMMARY_PROMPT,
            "description": "System message for summarizing SQL query results",
            "is_default": True,
            "updated_at": datetime.utcnow()
        }
    ]
    
    # Insert default prompts (update if they already exist)
    for prompt in default_prompts:
        try:
            result = prompts_collection.update_one(
                {"prompt_id": prompt["prompt_id"], "is_default": True},
                {"$set": prompt},
                upsert=True
            )
            
            if result.upserted_id:
                print(f"Created default prompt: {prompt['prompt_id']}")
            else:
                print(f"Updated default prompt: {prompt['prompt_id']}")
        except Exception as e:
            print(f"Error initializing prompt {prompt['prompt_id']}: {str(e)}")


def create_test_customer(db):
    """Create a test customer with default credentials"""
    create_customer = input("Do you want to create a test customer? (y/n): ").lower() == 'y'
    
    if not create_customer:
        return
    
    credentials_collection = db["credentials"]
    
    # Get customer details
    customer_id = input("Enter customer ID (default: test_customer): ") or "test_customer"
    password = input("Enter password (default: password123): ") or "password123"
    openai_api_key = input("Enter OpenAI API key (optional): ")
    
    # Check if customer already exists
    existing_customer = credentials_collection.find_one({"customer_id": customer_id})
    if existing_customer:
        update = input(f"Customer '{customer_id}' already exists. Update? (y/n): ").lower() == 'y'
        if not update:
            print("Skipping customer creation")
            return
    
    # Store plain text password (no hashing)
    
    # Generate a secret key if not provided
    secret_key = input("Enter secret key (leave empty to generate): ")
    if not secret_key:
        secret_key = secrets.token_hex(16)
        print(f"Generated secret key: {secret_key}")
    
    # Create customer data
    customer_data = {
        "customer_id": customer_id,
        "password": password,  # Plain text password
        "openai_api_key": openai_api_key,
        "postgres_connection": {
            "username": "postgres",
            "password": "Aa000000",
            "host": "localhost",
            "database": "university"
        },
        "prompt_settings": {
            "sql_system_message": None,
            "sql_debug_system_message": None,
            "result_summary_system_message": None
        },
        "security": {
            "secret_key": secret_key
        },
        "created_at": datetime.utcnow()
    }
    
    try:
        if existing_customer:
            result = credentials_collection.update_one(
                {"customer_id": customer_id},
                {"$set": customer_data}
            )
            print(f"Updated customer: {customer_id}")
        else:
            result = credentials_collection.insert_one(customer_data)
            print(f"Created customer: {customer_id}")
    except Exception as e:
        print(f"Error creating customer: {str(e)}")


def generate_env_file():
    """Generate a .env file template"""
    try:
        with open("env_file", "w") as env_file:
            env_content = f"""# API configuration
API_V1_STR=/api/v1
PROJECT_NAME=Agentic Text2SQL

# MongoDB settings
MONGODB_URI={MONGO_URI}
MONGODB_DB={DB_NAME}
CREDENTIALS_COLLECTION=credentials

# PostgreSQL settings
POSTGRES_URI=postgresql://postgres:Aa000000@localhost:5432/university

# OpenAI settings
# We'll fetch this from MongoDB for each customer instead of hardcoding
OPENAI_API_KEY=
LLM_MODEL=gpt-3.5-turbo

# Security settings
SECRET_KEY={secrets.token_hex(16)}
ACCESS_TOKEN_EXPIRE_MINUTES=30
"""
            env_file.write(env_content)
            print("\nCreated env_file template (rename to .env to use)")
            print("Note: The OPENAI_API_KEY is deliberately left empty as it will be retrieved from MongoDB")
    except Exception as e:
        print(f"Error generating env file: {str(e)}")


if __name__ == "__main__":
    print("=== MongoDB Initialization Script for Agentic Text2SQL ===")
    initialize_mongodb()
    generate_env_file() 