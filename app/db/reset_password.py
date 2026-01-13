"""Reset super admin password"""

import asyncio

from sqlalchemy import select

from app.core.security import get_password_hash
from app.core.settings import settings
from app.db import SessionLocal
from app.db.schema import Admin


async def reset_password():
    async with SessionLocal() as session:
        try:
            # Find admin by email
            query = select(Admin).where(Admin.email == settings.SUPER_ADMIN_EMAIL)
            result = await session.execute(query)
            admin = result.scalar_one_or_none()

            if not admin:
                print(f"Admin with email {settings.SUPER_ADMIN_EMAIL} not found!")
                return

            # Update password
            new_password_hash = get_password_hash(settings.SUPER_ADMIN_PASSWORD)
            admin.password_hash = new_password_hash
            await session.commit()

            print(f"Password reset successfully for {settings.SUPER_ADMIN_EMAIL}")
            print(f"New password: {settings.SUPER_ADMIN_PASSWORD}")

        except Exception as e:
            print(f"Error resetting password: {e}")
            await session.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(reset_password())
