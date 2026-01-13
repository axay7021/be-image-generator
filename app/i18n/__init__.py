"""Internationalization module for multi-language support"""

from app.core.settings import settings
from app.i18n.messages_en import MESSAGES_EN
from app.i18n.messages_ja import MESSAGES_JA


def get_message(key: str, **kwargs) -> str:
    """
    Get localized message based on MESSAGE_LANG environment variable

    Args:
        key: Message key (e.g., "LOGIN_SUCCESS", "USER_NOT_FOUND")
        **kwargs: Optional format arguments for the message

    Returns:
        str: Localized message string

    Example:
        >>> get_message("LOGIN_SUCCESS")
        "Login successful" (if MESSAGE_LANG=en)
        "ログインに成功しました" (if MESSAGE_LANG=ja)

        >>> get_message("SERVICE_NOT_FOUND", code=123)
        "Service with code 123 not found"
    """
    # Select message dictionary based on language setting
    messages = MESSAGES_JA if settings.MESSAGE_LANG == "ja" else MESSAGES_EN

    # Get message template
    message = messages.get(key, key)  # Fall back to key if not found

    # Format message with provided arguments if any
    if kwargs:
        try:
            return message.format(**kwargs)
        except KeyError:
            return message

    return message


# Convenience alias
msg = get_message
