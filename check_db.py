import asyncio
from app.core.database import async_session_maker
from app.models.user import User
from app.models.tenant import Tenant
from app.models.user_tenant import UserTenant
from sqlalchemy import select

async def main():
    async with async_session_maker() as session:
        # Get users
        res = await session.execute(select(User))
        users = res.scalars().all()
        print("=== Users ===")
        for u in users:
            print(f"ID: {u.id}, Email: {u.email}, Admin: {u.is_admin}, Active: {u.is_active}")
        
        # Get tenants
        res = await session.execute(select(Tenant))
        tenants = res.scalars().all()
        print("\n=== Tenants ===")
        for t in tenants:
            print(f"ID: {t.id}, Name: {t.name}, Slug: {t.slug}")
            
        # Get UserTenants
        res = await session.execute(select(UserTenant))
        uts = res.scalars().all()
        print("\n=== UserTenants ===")
        for ut in uts:
            print(f"User ID: {ut.user_id}, Tenant ID: {ut.tenant_id}, Role: {ut.role}")

if __name__ == "__main__":
    asyncio.run(main())
