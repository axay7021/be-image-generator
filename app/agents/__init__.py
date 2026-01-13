from datetime import datetime

from mcp.server.fastmcp import FastMCP

import app.db
from app.core.logger import logger
from app.db.schema import UserGender
from app.services import (
    user_service,
)

mcp = FastMCP("barber-poc", stateless_http=True)


# @mcp.tool(description="Debug tool for Vapi integration")
# async def mcp_tool(**kwargs) -> str:
#     """
#     Debug tool to catch requests for 'mcp_tool'.
#     """
#     logger.warning(f"⚠️ Received call to 'mcp_tool' with args: {kwargs}")
#     return "Received call to 'mcp_tool'. Available tools: authenticate_user, list_services, etc."


@mcp.tool(description="Authenticate or register a user. checks existence by phone; creates if name provided.")
async def authenticate_user(
    phone_number: str,
    name: str = None,
    gender: str = "other",
) -> str:
    """
    Authenticate a user by phone number. If user exists, returns details.
    If not, and name is provided, creates a new user.
    If not, and name is NOT provided, returns a prompt to ask for name.

    Args:
        phone_number: The user's phone number
        name: The user's full name (required for creation)
        gender: The user's gender (male/female/other). Please try to provide specific gender 'male' or 'female' if known.
    """
    async with app.db.SessionLocal() as db:
        logger.info("Authenticating user: %s", phone_number)

        # 1. Check if user exists
        user = await user_service.get_user_by_phone(phone_number, db)
        if user:
            return f"User found: {user.full_name} (ID: {user.id})"

        # 2. If not found, check if name is provided for creation
        if not name:
            return "User not found. Please ask the user for their name to create an account."

        # 3. Create new user
        logger.info("Creating new user: %s, %s, %s", name, phone_number, gender)
        try:
            # Map gender string to Enum
            gender_enum = UserGender.OTHER
            if gender:
                if gender.lower() == "male":
                    gender_enum = UserGender.MALE
                elif gender.lower() == "female":
                    gender_enum = UserGender.FEMALE

            user = await user_service.create_user_from_ai_call(name=name, phone=phone_number, gender=gender_enum, db=db)
            return f"User created successfully: {user.full_name} (ID: {user.id})"
        except Exception as e:
            logger.error("Error creating user: %s", e)
            return f"Failed to create user: {str(e)}"


@mcp.tool(description="Check if a user exists by phone number")
async def check_existing_user(phone_number: str) -> str:
    """
    Check if a user exists by phone number.

    Args:
        phone_number: The user's phone number
    """
    async with app.db.SessionLocal() as db:
        logger.info("Checking user with phone: %s", phone_number)
        user = await user_service.get_user_by_phone(phone_number, db)
        if user:
            return f"User found: {user.full_name} (ID: {user.id})"
        return "User not found"


@mcp.tool(description="Create a new user")
async def create_new_user(
    name: str,
    phone_number: str,
    gender: str,
) -> str:
    """
    Create a new user.

    Args:
        name: The user's full name
        phone_number: The user's phone number
        gender: The user's gender (male/female/other)
    """
    async with app.db.SessionLocal() as db:
        logger.info("Creating user: %s, %s, %s", name, phone_number, gender)
        try:
            # Map gender string to Enum
            gender_enum = None
            if gender.lower() == "male":
                gender_enum = UserGender.MALE
            elif gender.lower() == "female":
                gender_enum = UserGender.FEMALE
            else:
                gender_enum = UserGender.OTHER

            user = await user_service.create_user_from_ai_call(name=name, phone=phone_number, gender=gender_enum, db=db)
            return f"User created successfully: {user.full_name} (ID: {user.id})"
        except Exception as e:
            logger.error("Error creating user: %s", e)
            return f"Failed to create user: {str(e)}"


@mcp.tool(description="List available services")
async def list_services() -> str:
    """
    List available services.
    """
    return "Services information is currently unavailable."
