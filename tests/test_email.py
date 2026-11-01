import os
import smtplib

from dotenv import load_dotenv
from email.message import EmailMessage

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM")
OPS_EMAIL = os.getenv("OPS_EMAIL")


message = EmailMessage()

message["Subject"] = "OpsPilot Email Test"
message["From"] = SMTP_FROM
message["To"] = OPS_EMAIL

message.set_content(
    """
Hello!

This is a test email from OpsPilot.

If you received this email, SMTP integration is working correctly.

OpsPilot AI Operations Automation
"""
)


print("SMTP Host:", SMTP_HOST)
print("SMTP Port:", SMTP_PORT)
print("From:", SMTP_FROM)
print("To:", OPS_EMAIL)

print("\nConnecting to Gmail...")


with smtplib.SMTP(
    SMTP_HOST,
    SMTP_PORT,
    timeout=10,
) as server:

    server.starttls()

    print("TLS connection established.")

    server.login(
        SMTP_USERNAME,
        SMTP_PASSWORD,
    )

    print("SMTP authentication successful.")

    server.send_message(message)

    print("Email sent successfully!")