import random
import logging
import os
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_async_db
from app.models.user import User
from app.models.user_oauth import UserOAuth
from app.models.user_tenant import UserTenant
from app.models.tenant import Tenant
from app.models.verification_code import EmailVerificationCode
from app.core.auth_jwt import create_access_token, decode_access_token
from app.core.config import settings
from app.api.dependencies import get_tenant_context, generate_ws_token, TenantContext
import httpx

logger = logging.getLogger(__name__)
router = APIRouter()

# Schema definitions
class OTPRequest(BaseModel):
    email: EmailStr

class OTPVerify(BaseModel):
    email: EmailStr
    code: str

# Google OAuth configs from environment
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/oauth/google/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

@router.post("/ws-token")
async def get_ws_token(ctx: TenantContext = Depends(get_tenant_context)):
    """
    Generate a short-lived (30s), cryptographically signed token for WebSocket authentication.
    """
    token = generate_ws_token(ctx.tenant_id, ctx.scopes)
    return {"token": token}

@router.post("/otp/request")
async def request_otp(payload: OTPRequest, db: AsyncSession = Depends(get_async_db)):
    """
    Generate a 6-digit OTP code, save it to the database, and log it to container stdout for dev access.
    """
    email = payload.email.lower().strip()
    code = f"{random.randint(100000, 999999)}"
    expires_at = datetime.utcnow() + timedelta(minutes=10)

    # Save verification code
    verification = EmailVerificationCode(
        email=email,
        code=code,
        expires_at=expires_at,
        is_used=False
    )
    db.add(verification)
    await db.commit()

    # Log to container stdout clearly for development
    logger.warning("==================================================")
    logger.warning(f"🔑 VERIFICATION CODE FOR: {email}")
    logger.warning(f"👉 YOUR OTP CODE IS: {code}")
    logger.warning("==================================================")

    return {"message": "Verification code generated and sent (check server/container logs)."}

@router.post("/otp/verify")
async def verify_otp(payload: OTPVerify, db: AsyncSession = Depends(get_async_db)):
    """
    Verify the OTP code. On success, auto-provision user and personal tenant if missing, and return a JWT.
    """
    email = payload.email.lower().strip()
    code = payload.code.strip()

    # Verify code in DB
    result = await db.execute(
        select(EmailVerificationCode)
        .filter(
            EmailVerificationCode.email == email,
            EmailVerificationCode.code == code,
            EmailVerificationCode.is_used == False,
            EmailVerificationCode.expires_at > datetime.utcnow()
        )
        .order_by(EmailVerificationCode.created_at.desc())
    )
    verification = result.scalar_one_or_none()

    if not verification:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code."
        )

    # Mark code as used
    verification.is_used = True
    await db.commit()

    # Retrieve or create user
    user_res = await db.execute(select(User).filter(User.email == email))
    user = user_res.scalar_one_or_none()

    if not user:
        # Create user
        user = User(email=email, is_active=True, is_admin=False)
        db.add(user)
        await db.flush()

        # Provision personal tenant
        email_prefix = email.split("@")[0]
        tenant_slug = f"personal-{email_prefix}-{random.randint(1000, 9999)}"
        tenant = Tenant(
            name=f"{email_prefix}'s Personal Org",
            slug=tenant_slug,
            is_active=True
        )
        db.add(tenant)
        await db.flush()

        # Associate user as owner of the tenant
        user_tenant = UserTenant(
            user_id=user.id,
            tenant_id=tenant.id,
            role="owner"
        )
        db.add(user_tenant)
        await db.commit()

    # Issue JWT
    token_data = {"sub": str(user.id), "email": user.email, "is_admin": user.is_admin}
    token = create_access_token(token_data)

    return {"access_token": token, "token_type": "bearer"}

@router.get("/oauth/google/login")
async def google_login(email: Optional[str] = Query(None, description="Optional email for mock flow shortcut")):
    """
    Initiate Google OAuth2 flow. If Client ID/Secret are not set, it redirects to mock callback.
    """
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        # Fallback to Mock flow callback
        mock_email = email if email else "google-user@example.com"
        mock_code = f"mock_code_for_{mock_email}"
        redirect_url = f"{GOOGLE_REDIRECT_URI}?code={mock_code}"
        return RedirectResponse(url=redirect_url)
    
    # Real Google OAuth2 Redirect URL
    params = {
        "response_type": "code",
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account"
    }
    query_str = "&".join(f"{k}={v}" for k, v in params.items())
    google_url = f"https://accounts.google.com/o/oauth2/v2/auth?{query_str}"
    return RedirectResponse(url=google_url)

@router.get("/oauth/google/callback")
async def google_callback(code: str, db: AsyncSession = Depends(get_async_db)):
    """
    OAuth2 callback handler. Exchanges code with Google or handles mock flow, registers user, and redirects to frontend with token.
    """
    email = ""
    google_id = ""

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET or code.startswith("mock_code_for_"):
        # Mock Flow
        if code.startswith("mock_code_for_"):
            email = code.replace("mock_code_for_", "").lower().strip()
        else:
            email = "google-user@example.com"
        google_id = f"mock_google_id_{hash(email)}"
    else:
        # Real Google Flow
        try:
            # 1. Exchange auth code for access token
            token_url = "https://oauth2.googleapis.com/token"
            data = {
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code"
            }
            async with httpx.AsyncClient() as client:
                token_resp = await client.post(token_url, data=data)
                token_resp.raise_for_status()
                token_json = token_resp.json()
                access_token = token_json.get("access_token")

                # 2. Fetch user details
                user_info_resp = await client.get(
                    "https://www.googleapis.com/oauth2/v3/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                user_info_resp.raise_for_status()
                user_info = user_info_resp.json()
                email = user_info.get("email", "").lower().strip()
                google_id = user_info.get("sub", "")
        except Exception as e:
            logger.error(f"Google OAuth exchange failed: {e}")
            return RedirectResponse(url=f"{FRONTEND_URL}/login?error=OAuthExchangeFailed")

    if not email or not google_id:
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=InvalidUserInfo")

    # Retrieve or create user
    # First check UserOAuth linkage
    oauth_res = await db.execute(
        select(UserOAuth)
        .options(selectinload(UserOAuth.user))
        .filter(UserOAuth.provider == "google", UserOAuth.provider_user_id == google_id)
    )
    user_oauth = oauth_res.scalar_one_or_none()
    user = user_oauth.user if user_oauth else None

    if not user:
        # Check if user already exists by email
        user_res = await db.execute(select(User).filter(User.email == email))
        user = user_res.scalar_one_or_none()

        if not user:
            # Create new user
            user = User(email=email, is_active=True, is_admin=False)
            db.add(user)
            await db.flush()

            # Provision personal tenant
            email_prefix = email.split("@")[0]
            tenant_slug = f"personal-{email_prefix}-{random.randint(1000, 9999)}"
            tenant = Tenant(
                name=f"{email_prefix}'s Personal Org",
                slug=tenant_slug,
                is_active=True
            )
            db.add(tenant)
            await db.flush()

            # Associate role
            user_tenant = UserTenant(
                user_id=user.id,
                tenant_id=tenant.id,
                role="owner"
            )
            db.add(user_tenant)
            await db.flush()

        # Link Google OAuth
        new_oauth = UserOAuth(
            user_id=user.id,
            provider="google",
            provider_user_id=google_id
        )
        db.add(new_oauth)
        await db.commit()

    # Issue JWT
    token_data = {"sub": str(user.id), "email": user.email, "is_admin": user.is_admin}
    token = create_access_token(token_data)

    # Redirect to frontend with JWT token in query string
    return RedirectResponse(url=f"{FRONTEND_URL}/?token={token}")

from app.api.dependencies import get_current_user

@router.get("/me")
async def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Gets the current logged in user and lists their associated tenants.
    """
    result = await db.execute(
        select(UserTenant)
        .options(selectinload(UserTenant.tenant))
        .filter(UserTenant.user_id == current_user.id)
    )
    user_tenants = result.scalars().all()
    
    tenants_list = [
        {
            "id": str(ut.tenant_id),
            "name": ut.tenant.name,
            "slug": ut.tenant.slug,
            "role": ut.role
        }
        for ut in user_tenants if ut.tenant
    ]
    
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "is_admin": current_user.is_admin,
        "tenants": tenants_list
    }
