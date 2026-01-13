"""CSV parsing and validation utilities for service management"""

import csv
import io
from decimal import Decimal, InvalidOperation

from fastapi import UploadFile
from pydantic import ValidationError

from app.dto.service_dto import CSVRowSchema, CSVValidationError

# Required CSV headers
REQUIRED_HEADERS = [
    "category_code",
    "category_name",
    "category_order",
    "service_code",
    "service_name",
    "duration_minutes",
    "price",
    "service_order",
]

# Optional headers
OPTIONAL_HEADERS = ["description"]


async def parse_csv_file(file: UploadFile) -> list[dict[str, str]]:
    """
    Read and parse CSV file with proper encoding handling

    Args:
        file: Uploaded CSV file

    Returns:
        List of dictionaries representing CSV rows

    Raises:
        ValueError: If file cannot be parsed or encoding is invalid
    """
    try:
        # Read file content
        content = await file.read()

        # Try UTF-8 first, then fallback to latin-1
        try:
            decoded_content = content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                decoded_content = content.decode("latin-1")
            except UnicodeDecodeError as e:
                raise ValueError("File encoding not supported. Please use UTF-8 or Latin-1 encoding") from e

        # Parse CSV
        csv_reader = csv.DictReader(io.StringIO(decoded_content))
        rows = list(csv_reader)

        if not rows:
            raise ValueError("CSV file is empty")

        return rows

    except csv.Error as e:
        raise ValueError(f"Invalid CSV format: {str(e)}") from e
    except Exception as e:
        raise ValueError(f"Failed to parse CSV file: {str(e)}") from e


def validate_csv_headers(rows: list[dict[str, str]]) -> list[str]:
    """
    Check for missing required columns and return list of missing headers

    Args:
        rows: Parsed CSV rows with headers as keys

    Returns:
        List of missing required headers (empty if all present)
    """
    if not rows:
        return REQUIRED_HEADERS.copy()

    headers = set(rows[0].keys())
    missing_headers = [h for h in REQUIRED_HEADERS if h not in headers]

    return missing_headers


def validate_csv_row(row: dict[str, str], row_number: int) -> tuple[CSVRowSchema, list[CSVValidationError]]:
    """
    Validate individual CSV row using Pydantic schema

    Args:
        row: Dictionary representing a single CSV row
        row_number: Row number for error reporting (1-indexed, excluding header)

    Returns:
        Tuple of (validated schema or None, list of validation errors)
    """
    errors = []

    # Check for empty required fields first
    for field in REQUIRED_HEADERS:
        if field == "description":  # description is optional
            continue
        value = row.get(field, "").strip()
        if not value:
            errors.append(CSVValidationError(row=row_number, field=field, error=f"Required field '{field}' is empty"))

    # If we have empty field errors, return early
    if errors:
        return None, errors

    # Prepare data for Pydantic validation
    try:
        # Convert numeric fields
        validated_data = {
            "category_code": int(row["category_code"]),
            "category_name": row["category_name"].strip(),
            "category_order": int(row.get("category_order", "0") or "0"),
            "service_code": int(row["service_code"]),
            "service_name": row["service_name"].strip(),
            "description": row.get("description", "").strip() or None,
            "duration_minutes": int(row["duration_minutes"]),
            "price": Decimal(row["price"]),
            "service_order": int(row.get("service_order", "0") or "0"),
        }

        # Validate with Pydantic
        schema = CSVRowSchema(**validated_data)
        return schema, []

    except (ValueError, InvalidOperation) as e:
        # Data type conversion errors
        field_name = str(e).split("'")[1] if "'" in str(e) else "unknown"
        errors.append(CSVValidationError(row=row_number, field=field_name, error=f"Invalid data type: {str(e)}"))
        return None, errors

    except ValidationError as e:
        # Pydantic validation errors
        for err in e.errors():
            field = ".".join(str(loc) for loc in err["loc"])
            errors.append(CSVValidationError(row=row_number, field=field, error=err["msg"]))
        return None, errors

    except Exception as e:
        errors.append(CSVValidationError(row=row_number, field="general", error=f"Validation error: {str(e)}"))
        return None, errors


def check_duplicate_codes(validated_rows: list[CSVRowSchema]) -> list[int]:
    """
    Find duplicate service codes within CSV

    Note: Category codes are expected to repeat across multiple services
    (multiple services belong to the same category), so we only check
    for duplicate service codes.

    Args:
        validated_rows: List of validated CSV rows

    Returns:
        List of duplicate service codes
    """
    service_codes = [row.service_code for row in validated_rows]

    # Find duplicate service codes
    duplicate_services = [code for code in set(service_codes) if service_codes.count(code) > 1]

    return duplicate_services


def normalize_service_data(row: CSVRowSchema) -> dict:
    """
    Clean and normalize CSV row data for database insertion

    Args:
        row: Validated CSV row schema

    Returns:
        Normalized dictionary ready for database
    """
    return {
        "category_code": row.category_code,
        "category_name": row.category_name.strip(),
        "category_order": row.category_order,
        "service_code": row.service_code,
        "service_name": row.service_name.strip(),
        "description": row.description.strip() if row.description else None,
        "duration_minutes": row.duration_minutes,
        "price": row.price,
        "service_order": row.service_order,
    }


async def validate_csv_file(
    file: UploadFile,
) -> tuple[list[CSVRowSchema], list[CSVValidationError]]:
    """
    Complete CSV validation pipeline

    Args:
        file: Uploaded CSV file

    Returns:
        Tuple of (validated rows, validation errors)

    Raises:
        ValueError: For file-level errors (parsing, headers)
    """
    # Parse CSV
    rows = await parse_csv_file(file)

    # Check headers
    missing_headers = validate_csv_headers(rows)
    if missing_headers:
        raise ValueError(f"Missing required columns: {', '.join(missing_headers)}")

    # Validate each row
    validated_rows = []
    all_errors = []

    for idx, row in enumerate(rows, start=1):
        validated_row, errors = validate_csv_row(row, idx)
        if errors:
            all_errors.extend(errors)
        elif validated_row:
            validated_rows.append(validated_row)

    # Check for duplicate codes
    if validated_rows and not all_errors:
        duplicate_services = check_duplicate_codes(validated_rows)

        if duplicate_services:
            all_errors.append(
                CSVValidationError(
                    row=0,
                    field="service_code",
                    error=f"Duplicate service codes found: {', '.join(map(str, duplicate_services))}",
                )
            )

    return validated_rows, all_errors
