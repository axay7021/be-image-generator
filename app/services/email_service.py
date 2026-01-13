"""Email service for sending emails via SMTP"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.logger import logger
from app.core.settings import settings


class EmailService:
    """SMTP Email service for sending notifications"""

    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL
        self.from_name = settings.SMTP_FROM_NAME
        self.use_tls = settings.SMTP_USE_TLS

    def send_email(
        self,
        to_email: str | list[str],
        subject: str,
        body: str,
        html: str | None = None,
    ) -> bool:
        """
        Send an email via SMTP

        Args:
            to_email: Recipient email address or list of addresses
            subject: Email subject
            body: Plain text email body
            html: Optional HTML email body

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = to_email if isinstance(to_email, str) else ", ".join(to_email)
            msg["Subject"] = subject

            # Add plain text and HTML parts
            msg.attach(MIMEText(body, "plain"))
            if html:
                msg.attach(MIMEText(html, "html"))

            # Connect to SMTP server and send
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            logger.info(f"Email sent successfully to {to_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    def send_otp_email(self, to_email: str, otp: str, purpose: str = "password reset") -> bool:
        """
        Send OTP verification email

        Args:
            to_email: Recipient email address
            otp: 6-digit OTP code
            purpose: Purpose of OTP (password reset, email verification)

        Returns:
            bool: True if sent successfully
        """
        subject = f"{self.from_name} - Verification Code"

        body = f"""
Hello,

Your verification code for {purpose} is:

{otp}

This code will expire in {settings.OTP_EXPIRE_MINUTES} minutes.

If you did not request this code, please ignore this email.

Best regards,
{self.from_name} Team
        """.strip()

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: #4CAF50; color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; background-color: #f9f9f9; }}
        .otp-code {{ 
            font-size: 32px; 
            font-weight: bold; 
            text-align: center; 
            padding: 20px; 
            background-color: #fff; 
            border: 2px dashed #4CAF50;
            letter-spacing: 8px;
            margin: 20px 0;
        }}
        .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #777; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{self.from_name}</h1>
        </div>
        <div class="content">
            <h2>Verification Code</h2>
            <p>Your verification code for {purpose} is:</p>
            <div class="otp-code">{otp}</div>
            <p>This code will expire in <strong>{settings.OTP_EXPIRE_MINUTES} minutes</strong>.</p>
            <p>If you did not request this code, please ignore this email.</p>
        </div>
        <div class="footer">
            <p>&copy; 2025 {self.from_name}. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
        """.strip()

        return self.send_email(to_email, subject, body, html)

    def send_password_changed_email(self, to_email: str, admin_name: str) -> bool:
        """
        Send password changed notification email

        Args:
            to_email: Recipient email address
            admin_name: Name of the admin

        Returns:
            bool: True if sent successfully
        """
        subject = f"{self.from_name} - Password Changed"

        body = f"""
Hello {admin_name},

Your password has been successfully changed.

If you did not make this change, please contact us immediately.

Best regards,
{self.from_name} Team
        """.strip()

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: #2196F3; color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; background-color: #f9f9f9; }}
        .alert {{ 
            background-color: #fff3cd; 
            border-left: 4px solid #ffc107; 
            padding: 15px; 
            margin: 20px 0;
        }}
        .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #777; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{self.from_name}</h1>
        </div>
        <div class="content">
            <h2>Password Changed</h2>
            <p>Hello {admin_name},</p>
            <p>Your password has been successfully changed.</p>
            <div class="alert">
                <strong>Security Alert:</strong> If you did not make this change, please contact us immediately.
            </div>
        </div>
        <div class="footer">
            <p>&copy; 2025 {self.from_name}. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
        """.strip()

        return self.send_email(to_email, subject, body, html)


# Singleton instance
email_service = EmailService()
