"""English messages for the application"""

MESSAGES_EN = {
    # ============================================
    # Authentication Messages
    # ============================================
    "LOGIN_SUCCESS": "Login successful",
    "LOGOUT_SUCCESS": "Logged out successfully",
    "REGISTRATION_SUCCESS": "Registration successful",
    "TOKEN_REFRESHED": "Token refreshed successfully",
    "PASSWORD_CHANGED": "Password changed successfully",
    "INVALID_CREDENTIALS": "Invalid phone number or password",
    "INVALID_EMAIL_PASSWORD": "Invalid email or password",
    "ACCOUNT_INACTIVE": "Account is inactive",
    "SESSION_REVOKED": "Session has been revoked or is invalid. Please login again.",
    "TOKEN_INVALID": "Could not validate credentials",
    "TOKEN_REVOKED": "Token has been revoked or is invalid. Please login again.",
    "INSUFFICIENT_PERMISSIONS": "Insufficient permissions",
    # ============================================
    # User Management
    # ============================================
    "USER_NOT_FOUND": "User not found",
    "USERS_RETRIEVED_SUCCESS": "Users retrieved successfully",
    "NO_USERS_FOUND": "No users found",
    "USER_DETAIL_RETRIEVED": "User details retrieved successfully",
    "PROFILE_RETRIEVED": "User profile retrieved successfully",
    "NAME_REQUIRED": "Name is required",
    "NAME_EMPTY": "Name cannot be empty",
    "PHONE_IN_USE": "Phone number already in use",
    "PHONE_REGISTERED": "Phone number already registered",
    "EMAIL_IN_USE": "Email already in use",
    "EMAIL_REGISTERED": "Email already registered",
    "LINE_REGISTERED": "LINE account already registered",
    "NO_PASSWORD_ACCOUNT": "This account was not created with a password",
    "INCORRECT_PASSWORD": "Current password is incorrect",
    "INVALID_PHONE_FORMAT": "Invalid phone number format. Please provide a valid Indian (10 digits starting with 6-9) or Japanese (11 digits starting with 070/080/090) phone number.",
    # ============================================
    # LINE Integration
    # ============================================
    "LINE_TOKEN_INVALID": "Invalid LINE access token",
    "LINE_PROFILE_FAILED": "Failed to fetch LINE profile",
    "LINE_TIMEOUT": "LINE API request timed out. Please check your network connection or try again later.",
    "LINE_CONNECTION_FAILED": "Failed to connect to LINE API: {error}",
    # ============================================
    # Appointments
    # ============================================
    "APPOINTMENT_BOOKED": "Appointment booked successfully",
    "APPOINTMENT_CANCELLED": "Appointment cancelled successfully",
    "APPOINTMENT_UPDATED": "Appointment status updated successfully",
    "APPOINTMENT_RETRIEVED": "Appointment retrieved successfully",
    "APPOINTMENTS_RETRIEVED": "Appointments retrieved successfully",
    "APPOINTMENT_STATS_RETRIEVED": "Appointment statistics retrieved successfully",
    "APPOINTMENT_NOT_FOUND": "Appointment with ID {appointment_id} not found",
    "TIME_SLOT_FULL": "No available slots in this time slot",
    "INVALID_STATUS_TRANSITION": "Cannot change appointment from {current} to {new}",
    "CANNOT_CANCEL_COMPLETED": "Cannot cancel a completed appointment",
    "SLOT_UNAVAILABLE": "Selected time slot is no longer available",
    "SERVICE_REQUIRED": "At least one service is required",
    "INVALID_SERVICE": "Invalid service code: {code}",
    "PAST_SLOT": "Cannot book appointments in past time slots",
    # ============================================
    # Services
    # ============================================
    "SERVICE_CREATED": "Service created successfully",
    "SERVICE_UPDATED": "Service updated successfully",
    "SERVICE_DELETED": "Service deleted successfully",
    "SERVICE_RETRIEVED": "Service retrieved successfully",
    "SERVICES_RETRIEVED": "Services retrieved successfully",
    "SERVICE_ORDER_UPDATED": "Service display order updated successfully",
    "SERVICE_NOT_FOUND": "Service with code {code} not found",
    "CATEGORY_NOT_FOUND_FOR_SERVICE": "Category with code {category_code} not found",
    "CSV_UPLOAD_SUCCESS": "CSV uploaded successfully",
    "FILE_MUST_BE_CSV": "File must be a CSV file",
    "DB_CONSTRAINT_VIOLATION": "Database constraint violation. Please check your data.",
    "CSV_UPLOAD_ERROR": "An error occurred during CSV upload",
    # ============================================
    # Categories
    # ============================================
    "CATEGORY_CREATED": "Category created successfully",
    "CATEGORY_UPDATED": "Category updated successfully",
    "CATEGORY_DELETED": "Category deleted successfully",
    "CATEGORY_RETRIEVED": "Category retrieved successfully",
    "CATEGORIES_RETRIEVED": "Categories retrieved successfully",
    "PUBLIC_CATEGORIES_RETRIEVED": "Public categories retrieved successfully",
    "CATEGORY_ORDER_UPDATED": "Category display order updated successfully",
    "CATEGORY_NOT_FOUND": "Category with code {code} not found",
    "CATEGORY_HAS_SERVICES": "Cannot delete category with {count} active services. Delete services first.",
    # ============================================
    # Time Slots
    # ============================================
    "TIME_SLOT_CREATED": "Time slot created successfully",
    "TIME_SLOT_UPDATED": "Time slot updated successfully",
    "TIME_SLOT_DELETED": "Time slot deleted successfully",
    "TIME_SLOT_RETRIEVED": "Time slot retrieved successfully",
    "TIME_SLOTS_RETRIEVED": "Time slots retrieved successfully",
    "AVAILABLE_SLOTS_RETRIEVED": "Available time slots retrieved successfully",
    "BULK_CREATION_COMPLETED": "Bulk time slot creation completed",
    "BULK_CREATION_SUMMARY": "Created {created} time slots, skipped {skipped} dates",
    "TIME_SLOT_NOT_FOUND": "Time slot with ID {time_slot_id} not found",
    "OVERLAPPING_SLOT": "Overlapping time slot exists on {date} from {start_time} to {end_time}",
    "CANNOT_UPDATE_DELETED": "Cannot update a deleted time slot. Activate it first by setting is_active=true",
    "START_BEFORE_END": "New start time must be before existing end time ({end_time})",
    "END_AFTER_START": "New end time must be after existing start time ({start_time})",
    "CAPACITY_TOO_LOW": "Cannot reduce capacity to {capacity}. Current bookings: {bookings}",
    "CANNOT_DELETE_WITH_BOOKINGS": "Cannot delete time slot with {bookings} booking(s). Cancel all appointments first.",
    # ============================================
    # Admin & Sessions
    # ============================================
    "ADMIN_PROFILE_RETRIEVED": "Admin profile retrieved successfully",
    "INACTIVE_ADMIN": "Inactive admin account",
    "INACTIVE_USER": "Inactive user account",
    "OTP_SENT": "If email exists, OTP has been sent",
    "OTP_INVALID": "Invalid or expired OTP",
    "OTP_EXPIRED": "OTP has expired",
    "OTP_TOO_MANY_ATTEMPTS": "Too many attempts",
    "OTP_VERIFIED": "OTP verified successfully",
    "PASSWORD_RESET_SUCCESS": "Password reset successful",
    "SESSIONS_RETRIEVED": "Sessions retrieved successfully",
    "SESSION_REVOKED_SUCCESS": "Session revoked successfully",
    "SESSIONS_REVOKED": "Revoked {count} sessions",
    "LOGIN_HISTORY_RETRIEVED": "Login history retrieved successfully",
    # ============================================
    # System Messages
    # ============================================
    "INTERNAL_ERROR": "An internal error occurred",
    "VALIDATION_ERROR": "Validation error",
    "NOT_FOUND": "Resource not found",
    "UNAUTHORIZED": "Unauthorized access",
    "FORBIDDEN": "Access forbidden",
}
