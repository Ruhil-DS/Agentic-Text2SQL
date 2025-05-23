from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import timedelta

from app.core.auth import authenticate_customer, create_access_token, get_current_customer, Credentials, Token, create_customer_credentials
from app.core.config import settings
from app.core.logger import app_logger
from app.services.query_service import query_service
from app.db.mongo_client import mongo_client
from app.utils.prompt_initializer import prompt_initializer

# API Router
router = APIRouter(prefix=settings.API_V1_STR)

# Models
class QueryRequest(BaseModel):
    query: str
    customer_id: Optional[str] = None

class QueryResponse(BaseModel):
    success: bool
    query: Optional[str] = None
    data: Optional[List[Dict[str, Any]]] = None
    summary: Optional[str] = None
    record_count: Optional[int] = None
    error: Optional[Dict[str, str]] = None
    mock: Optional[bool] = None
    was_debugged: Optional[bool] = None
    original_query: Optional[str] = None

class CredentialsResponse(BaseModel):
    success: bool
    message: str

class PromptRequest(BaseModel):
    prompt_id: str
    prompt_text: str
    description: Optional[str] = None
    is_default: bool = False

class PromptResponse(BaseModel):
    success: bool
    message: str

# Authentication endpoints
@router.post("/auth/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Get an access token using username (customer_id) and password
    """
    customer = authenticate_customer(form_data.username, form_data.password)
    if not customer:
        app_logger.warning(f"Failed login attempt for customer: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect customer ID or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": customer["customer_id"]}, expires_delta=access_token_expires
    )
    
    app_logger.info(f"Successful login for customer: {form_data.username}")
    return Token(access_token=access_token, token_type="bearer")

@router.post("/customers", response_model=CredentialsResponse)
async def create_customer(credentials: Credentials):
    """
    Create a new customer with credentials
    """
    success, message = create_customer_credentials(credentials)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )
    
    return CredentialsResponse(success=True, message=message)

# Query endpoint
@router.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest, customer=Depends(get_current_customer)):
    """
    Process a natural language query to SQL and return results
    """
    # Log the request
    app_logger.info(f"Query request from customer: {customer['customer_id']}")
    
    # Get customer API key from credentials
    openai_api_key = customer.get("openai_api_key", settings.OPENAI_API_KEY)
    
    # Process the query
    result = query_service.process_query(
        request.query, 
        customer_id=customer["customer_id"],
        openai_api_key=openai_api_key
    )
    
    # Convert to response model
    if not result.get("success", False):
        app_logger.warning(f"Query processing failed for customer: {customer['customer_id']}")
    else:
        app_logger.info(f"Query processed successfully for customer: {customer['customer_id']}")
    
    return result

# Prompt management endpoints
@router.post("/prompts", response_model=PromptResponse)
async def create_or_update_prompt(request: PromptRequest, customer=Depends(get_current_customer)):
    """
    Create or update a customer-specific prompt
    """
    try:
        # Only allow is_default=True for admin users
        # For simplicity, we're not implementing admin checks here
        is_default = False
        
        success = mongo_client.create_or_update_prompt(
            prompt_id=request.prompt_id,
            prompt_text=request.prompt_text,
            customer_id=customer["customer_id"],
            is_default=is_default
        )
        
        if success:
            return PromptResponse(
                success=True, 
                message=f"Prompt '{request.prompt_id}' created or updated successfully"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create or update prompt"
            )
    except Exception as e:
        app_logger.error(f"Error creating/updating prompt: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/prompts")
async def get_customer_prompts(customer=Depends(get_current_customer)):
    """
    Get all prompts available for a customer
    """
    try:
        prompts = mongo_client.get_all_prompts_for_customer(customer["customer_id"])
        return {
            "success": True,
            "prompts": prompts
        }
    except Exception as e:
        app_logger.error(f"Error retrieving prompts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/prompts/info")
async def get_prompt_info(customer=Depends(get_current_customer)):
    """
    Get information about available prompts
    """
    try:
        info = prompt_initializer.get_prompt_info()
        return {
            "success": True,
            "info": info
        }
    except Exception as e:
        app_logger.error(f"Error retrieving prompt info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

# Health check endpoint
@router.get("/health")
async def health_check():
    """
    Health check endpoint
    """
    return {"status": "healthy", "service": settings.PROJECT_NAME} 