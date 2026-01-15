"""
Gmail OAuth Authentication Utilities - Multi-User Support
Handles OAuth 2.0 flow for Gmail API access with user-specific tokens
"""
import os
import json
from django.conf import settings
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import logging
from ..models import GmailToken

logger = logging.getLogger(__name__)


def get_gmail_service(user=None, account_email=None):
    """
    Get authenticated Gmail API service for a specific user or account
    
    Args:
        user: Django User object
        account_email: Gmail account email address
    
    Returns:
        Gmail service object or None if not authenticated
    """
    if user and account_email:
        # Get token for specific user and account
        token_obj = GmailToken.objects.filter(user=user, email_account=account_email, is_active=True).first()
    elif account_email:
        # Get token by exact account email (first available)
        token_obj = GmailToken.objects.filter(email_account=account_email, is_active=True).first()
    elif user:
        # Get any active token for user
        token_obj = GmailToken.objects.filter(user=user, is_active=True).first()
    else:
        return None
    
    if not token_obj:
        return None
    
    token_data = token_obj.token_data
    
    # Create credentials from stored token
    creds = Credentials.from_authorized_user_info(token_data, settings.GMAIL_SCOPES)
    
    # Refresh token if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Save refreshed token
            token_obj.token_data = json.loads(creds.to_json())
            token_obj.save()
        except Exception as e:
            logger.error(f"Error refreshing token for {token_obj.email_account}: {e}")
            return None
    
    if not creds or not creds.valid:
        return None
    
    # Build and return Gmail service
    service = build('gmail', 'v1', credentials=creds)
    return service


def initiate_oauth_flow():
    """
    Start OAuth flow and return authorization URL
    
    Returns:
        (authorization_url, state) tuple
    """
    flow = Flow.from_client_secrets_file(
        settings.GMAIL_CREDENTIALS_PATH,
        scopes=settings.GMAIL_SCOPES,
        redirect_uri=settings.GMAIL_REDIRECT_URI
    )
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'  # Force consent to get refresh token
    )
    
    return authorization_url, state


def handle_oauth_callback(authorization_response, state=None, user=None):
    """
    Handle OAuth callback and store tokens for a specific user
    
    Args:
        authorization_response: Full callback URL from Google
        state: OAuth state parameter for verification
        user: Django User object to associate token with
    
    Returns:
        (success: bool, email_account: str or None)
    """
    try:
        logger.debug(f"Authorization response URL: {authorization_response}")
        logger.debug(f"State provided: {state}")
        logger.debug(f"User: {user.username if user else 'None'}")
        
        # Parse the URL to extract the authorization code
        from urllib.parse import urlparse, parse_qs
        parsed_url = urlparse(authorization_response)
        query_params = parse_qs(parsed_url.query)
        
        logger.debug(f"Parsed query params: {query_params}")
        
        # Extract the code
        if 'code' not in query_params:
            logger.error("No authorization code found in callback URL")
            return False, None
        
        auth_code = query_params['code'][0]
        logger.debug(f"Extracted authorization code: {auth_code[:20]}...")
        
        # Create flow
        flow = Flow.from_client_secrets_file(
            settings.GMAIL_CREDENTIALS_PATH,
            scopes=settings.GMAIL_SCOPES,
            redirect_uri=settings.GMAIL_REDIRECT_URI
        )
        
        # Fetch token using the authorization code
        flow.fetch_token(code=auth_code)
        
        logger.info("Token fetched successfully!")
        
        # Get credentials
        creds = flow.credentials
        token_data = json.loads(creds.to_json())
        
        # Get the Gmail account email address
        service = build('gmail', 'v1', credentials=creds)
        profile = service.users().getProfile(userId='me').execute()
        email_account = profile.get('emailAddress')
        
        # Validate that all required scopes were granted
        required_scopes = set(settings.GMAIL_SCOPES)
        granted_scopes = set(creds.scopes) if creds.scopes else set()
        
        # Check if we have all required scopes (or at least the critical ones)
        # Note: Google sometimes returns full URLs or short names depending on version
        # So we ensure the 'send' scope is present if we asked for it.
        
        missing_scopes = [s for s in required_scopes if s not in granted_scopes]
        
        # Special check for 'send' scope if it's required
        send_scope = 'https://www.googleapis.com/auth/gmail.send'
        if send_scope in required_scopes and send_scope not in granted_scopes:
            logger.warning(f"User {user.username} authenticated but did NOT grant 'gmail.send' permission.")
            return False, "Permission denied: You must grant 'Send email' permission on the Google consent screen."
            
        logger.info(f"Gmail account: {email_account} (Scopes: {granted_scopes})")
        
        # Save token to database with user association
        if user:
            GmailToken.save_token_for_user(
                user=user,
                email_account=email_account,
                token_data=token_data
            )
            logger.info(f"Token saved for user {user.username}, account {email_account}")
        else:
            logger.error("No user provided for OAuth callback. Cannot save token.")
            return False, None
        
        return True, email_account
        
    except Exception as e:
        logger.exception(f"OAuth callback failed: {e}")
        return False, None


def is_authenticated(user=None):
    """
    Check if user is authenticated with Gmail
    
    Args:
        user: Django User object (optional)
    
    Returns:
        bool: True if user has valid Gmail token
    """
    service = get_gmail_service(user=user)
    return service is not None


def refresh_token_if_needed(user=None, account_email=None):
    """
    Check and refresh token if needed for a specific user or account
    
    Args:
        user: Django User object
        account_email: Gmail account email
    
    Returns:
        bool: True if token is valid, False otherwise
    """
    if account_email:
        token_obj = GmailToken.objects.filter(email_account=account_email, is_active=True).first()
    elif user:
        token_obj = GmailToken.objects.filter(user=user, is_active=True).first()
    else:
        return False
    
    if not token_obj:
        return False
    
    token_data = token_obj.token_data
    creds = Credentials.from_authorized_user_info(token_data, settings.GMAIL_SCOPES)
    
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_obj.token_data = json.loads(creds.to_json())
            token_obj.save()
            return True
        except Exception as e:
            logger.error(f"Error refreshing token for {token_obj.email_account}: {e}")
            return False
    
    return creds.valid


def get_all_services_for_user(user):
    """
    Get Gmail services for all active accounts of a user
    
    Args:
        user: Django User object
    
    Returns:
        dict: {email_account: service} mapping
    """
    services = {}
    tokens = GmailToken.objects.filter(user=user, is_active=True)
    
    for token_obj in tokens:
        service = get_gmail_service(account_email=token_obj.email_account)
        if service:
            services[token_obj.email_account] = service
    
    return services
