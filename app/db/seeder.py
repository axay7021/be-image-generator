import asyncio

from sqlalchemy import select

from app.core.logger import logger
from app.core.security import get_password_hash
from app.core.settings import settings
from app.db import SessionLocal
from app.db.schema import Admin, AdminRole


async def seed_super_admin():
    async with SessionLocal() as session:
        try:
            # Check if super admin exists
            query = select(Admin).where(Admin.role == AdminRole.SUPER_ADMIN)
            result = await session.execute(query)
            existing_admin = result.scalar_one_or_none()

            if existing_admin:
                logger.info("Super admin already exists.")
            else:
                logger.info("Creating super admin...")
                super_admin = Admin(
                    email=settings.SUPER_ADMIN_EMAIL,
                    password_hash=get_password_hash(settings.SUPER_ADMIN_PASSWORD),
                    full_name=settings.SUPER_ADMIN_NAME,
                    role=AdminRole.SUPER_ADMIN,
                    is_active=True,
                )
                session.add(super_admin)
                await session.commit()
                logger.info(
                    f"Super admin created successfully with email: {settings.SUPER_ADMIN_EMAIL}"
                )
        except Exception as e:
            logger.error(f"Error seeding super admin: {e}")
            await session.rollback()
            raise


def main():
    asyncio.run(seed_super_admin())


if __name__ == "__main__":
    main()
