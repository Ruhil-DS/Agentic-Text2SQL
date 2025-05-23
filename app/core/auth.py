from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from app.core.config import settings
from app.core.logger import app_logger
from app.db.mongo_client import mongo_client

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/token")

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    customer_id: Optional[str] = None

class Credentials(BaseModel):
    customer_id: str
    password: str
    openai_api_key: Optional[str] = None
    postgres_username: Optional[str] = None
    postgres_password: Optional[str] = None
    postgres_host: Optional[str] = None
    postgres_db: Optional[str] = None

def verify_password(plain_password, stored_password):
    if isinstance(stored_password, dict) and "$binary" in stored_password:
        app_logger.info("Password is stored in binary format - converting to plain text")
        return False  # We can't easily convert binary back to plaintext
    return plain_password == stored_password

def get_password_hash(password):
    # No hashing, return the password as is
    return password

def authenticate_customer(customer_id: str, password: str):
    """
    Authenticate customer by customer_id and password
    """
    try:
        app_logger.info(f"Authenticating customer: {customer_id}")
        
        # Get customer credentials from MongoDB
        customer = mongo_client.get_credentials(customer_id)
        app_logger.info(f"Customer data: {customer}")
        
        if not customer:
            app_logger.warning(f"Authentication failed - unknown customer: {customer_id}")
            return False
        
        # Check if password field exists (for testing/development)
        if "password" not in customer:
            app_logger.warning(f"Customer {customer_id} has no password set")
            return False
        
        # Get password value
        stored_password = customer["password"]
        
        # Verify password with simple string comparison
        if not verify_password(password, stored_password):
            app_logger.warning(f"Authentication failed - invalid password for: {customer_id}")
            return False
        
        app_logger.info(f"Authentication successful for customer: {customer_id}")
        return customer
    except Exception as e:
        app_logger.error(f"Authentication error: {str(e)}")
        return False

def get_customer_secret_key(customer_id: str = None):
    """
    Get the SECRET_KEY for a specific customer or the default one
    """
    if customer_id:
        try:
            customer = mongo_client.get_credentials(customer_id)
            if customer and "security" in customer and "secret_key" in customer["security"]:
                return customer["security"]["secret_key"]
        except Exception as e:
            app_logger.error(f"Error retrieving customer secret key: {str(e)}")
    
    # Fall back to default secret key from settings
    return settings.SECRET_KEY

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """
    Create a JWT access token
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    
    # Get customer-specific secret key if available
    customer_id = to_encode.get("sub")
    secret_key = get_customer_secret_key(customer_id)
    
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm="HS256")
    return encoded_jwt

async def get_current_customer(token: str = Depends(oauth2_scheme)):
    """
    Validate token and get current customer information
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Try to decode with default key first to get customer_id
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            customer_id = payload.get("sub")
        except JWTError:
            # If default key fails, the token might be encoded with a customer-specific key
            # First, extract the customer_id from the token without verification
            # This is safe because we'll verify the token afterward
            unverified_payload = jwt.get_unverified_claims(token)
            customer_id = unverified_payload.get("sub")
            
            if not customer_id:
                app_logger.warning("Token validation failed - missing customer_id")
                raise credentials_exception
                
            # Try to decode with customer-specific key
            secret_key = get_customer_secret_key(customer_id)
            payload = jwt.decode(token, secret_key, algorithms=["HS256"])
        
        if not customer_id:
            app_logger.warning("Token validation failed - missing customer_id")
            raise credentials_exception
        
        token_data = TokenData(customer_id=customer_id)
    except JWTError as e:
        app_logger.warning(f"Token validation failed - JWT error: {str(e)}")
        raise credentials_exception
    
    # Get customer data from MongoDB
    customer = mongo_client.get_credentials(token_data.customer_id)
    
    if customer is None:
        app_logger.warning(f"Token validation failed - customer not found: {token_data.customer_id}")
        raise credentials_exception
    
    return customer

def create_customer_credentials(credentials: Credentials):
    """
    Create new customer credentials
    """
    try:
        # No password hashing needed
        plain_password = credentials.password
        
        # Check if customer already exists
        existing = mongo_client.get_credentials(credentials.customer_id)
        if existing:
            app_logger.warning(f"Customer already exists: {credentials.customer_id}")
            return False, "Customer ID already exists"
        
        # Create new credentials
        result = mongo_client.create_credentials(
            customer_id=credentials.customer_id,
            openai_api_key=credentials.openai_api_key,
            postgres_username=credentials.postgres_username,
            postgres_password=credentials.postgres_password,
            postgres_host=credentials.postgres_host,
            postgres_db=credentials.postgres_db
        )
        
        # Add plain password
        if result:
            mongo_client.credentials_collection.update_one(
                {"customer_id": credentials.customer_id},
                {"$set": {"password": plain_password}}
            )
            app_logger.info(f"Customer credentials created: {credentials.customer_id}")
            return True, "Customer credentials created successfully"
        
        return False, "Failed to create credentials"
    except Exception as e:
        app_logger.error(f"Error creating customer credentials: {str(e)}")
        return False, f"Error: {str(e)}" 