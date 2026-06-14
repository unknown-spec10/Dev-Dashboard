import asyncio
import httpx
from app.core.auth_jwt import create_access_token
from app.core.database import async_session_maker
from app.models.user import User
from sqlalchemy import select

async def main():
    async with async_session_maker() as session:
        res = await session.execute(select(User).filter(User.email == 'deeppodder50@gmail.com'))
        user = res.scalar_one_or_none()
        if not user:
            print("User not found")
            return
            
        token_data = {"sub": str(user.id), "email": user.email, "is_admin": user.is_admin}
        token = create_access_token(token_data)
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "http://localhost:8000/api/auth/me",
                headers={"Authorization": f"Bearer {token}"}
            )
            print("Response status:", resp.status_code)
            print("Response body:", resp.json())

if __name__ == "__main__":
    asyncio.run(main())
