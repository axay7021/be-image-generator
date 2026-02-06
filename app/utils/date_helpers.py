"""Date utility functions for analytics and reporting."""

from datetime import date, timedelta
from typing import Literal

Period = Literal["daily", "weekly", "monthly"]


def get_date_range(period: Period, start_date: date | None = None, end_date: date | None = None) -> list[date]:
    """
    Get a list of dates for the specified period and range.

    Args:
        period: "daily", "weekly", or "monthly"
        start_date: Start date (inclusive). Defaults to 30 days ago if not provided.
        end_date: End date (inclusive). Defaults to today if not provided.

    Returns:
        List of date objects representing the period boundaries.
    """
    if end_date is None:
        end_date = date.today()

    if start_date is None:
        start_date = end_date - timedelta(days=30)

    if start_date > end_date:
        raise ValueError("start_date must be before or equal to end_date")

    dates = []
    current = start_date

    if period == "daily":
        while current <= end_date:
            dates.append(current)
            current += timedelta(days=1)

    elif period == "weekly":
        # Start from the beginning of the week containing start_date
        current = start_of_week(start_date)
        while current <= end_date:
            dates.append(current)
            current += timedelta(weeks=1)

    elif period == "monthly":
        # Start from the beginning of the month containing start_date
        current = start_of_month(start_date)
        while current <= end_date:
            dates.append(current)
            # Move to next month
            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)

    return dates


def start_of_week(d: date) -> date:
    """Get the start of the week (Monday) for the given date."""
    return d - timedelta(days=d.weekday())


def end_of_week(d: date) -> date:
    """Get the end of the week (Sunday) for the given date."""
    return d + timedelta(days=6 - d.weekday())


def start_of_month(d: date) -> date:
    """Get the first day of the month for the given date."""
    return date(d.year, d.month, 1)


def end_of_month(d: date) -> date:
    """Get the last day of the month for the given date."""
    if d.month == 12:
        return date(d.year, 12, 31)
    else:
        return date(d.year, d.month + 1, 1) - timedelta(days=1)


def start_of_year(d: date) -> date:
    """Get the first day of the year for the given date."""
    return date(d.year, 1, 1)


def end_of_year(d: date) -> date:
    """Get the last day of the year for the given date."""
    return date(d.year, 12, 31)


def group_by_period(period: Period) -> str:
    """
    Get the SQL date_trunc format string for PostgreSQL.

    Args:
        period: "daily", "weekly", or "monthly"

    Returns:
        Format string for use with date_trunc SQL function.
    """
    mapping = {"daily": "day", "weekly": "week", "monthly": "month"}
    return mapping[period]


def format_date_for_display(d: date, period: Period) -> str:
    """
    Format a date for display based on the period granularity.

    Args:
        d: Date to format
        period: "daily", "weekly", or "monthly"

    Returns:
        Formatted date string.
    """
    if period == "daily":
        return d.strftime("%Y-%m-%d")
    elif period == "weekly":
        week_end = min(end_of_week(d), date.today())
        return f"{d.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}"
    elif period == "monthly":
        return d.strftime("%Y-%m")
    return d.isoformat()


def get_period_boundaries(d: date, period: Period) -> tuple[date, date]:
    """
    Get the start and end dates for the period containing the given date.

    Args:
        d: Date within the period
        period: "daily", "weekly", or "monthly"

    Returns:
        Tuple of (start_date, end_date) for the period.
    """
    if period == "daily":
        return (d, d)
    elif period == "weekly":
        return (start_of_week(d), end_of_week(d))
    elif period == "monthly":
        return (start_of_month(d), end_of_month(d))
    raise ValueError(f"Invalid period: {period}")
