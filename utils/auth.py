import os
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import Optional
import logging
from passlib.context import CryptContext
from jose import jwt
from email_validator import validate_email, EmailNotValidError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Load email configuration from environment variables
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
VERIFICATION_TOKEN_EXPIRE_MINUTES = 30

# Debug logging for environment variables
logging.info(f"SMTP Server: {SMTP_SERVER}")
logging.info(f"SMTP Port: {SMTP_PORT}")
logging.info(f"SMTP Username: {SMTP_USERNAME}")
logging.info("SMTP Password: [REDACTED]")
logging.info("JWT Secret: [REDACTED]")

# In-memory storage for pending registrations
pending_registrations = {}

def send_verification_email(email: str, verification_token: str) -> bool:
    """Send verification email to the user."""
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = SMTP_USERNAME
        msg['To'] = email
        msg['Subject'] = "Verify your email for Albion Scalp Analyzer"

        # Create verification link
        verification_link = f"http://localhost:8501/verify?token={verification_token}"

        # Email body
        body = f"""
        <html>
            <body>
                <h2>Welcome to Albion Scalp Analyzer!</h2>
                <p>Please click the link below to verify your email address:</p>
                <p><a href="{verification_link}">Verify Email</a></p>
                <p>This link will expire in {VERIFICATION_TOKEN_EXPIRE_MINUTES} minutes.</p>
                <p>If you did not request this registration, please ignore this email.</p>
            </body>
        </html>
        """
        msg.attach(MIMEText(body, 'html'))

        # Send email
        logging.info(f"Attempting to connect to SMTP server: {SMTP_SERVER}:{SMTP_PORT}")
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            logging.info("Starting TLS...")
            server.starttls()
            logging.info(f"Attempting to login with username: {SMTP_USERNAME}")
            try:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                logging.info("SMTP login successful")
            except smtplib.SMTPAuthenticationError as e:
                logging.error(f"SMTP Authentication failed: {str(e)}")
                return False
            except Exception as e:
                logging.error(f"SMTP login error: {str(e)}")
                return False
            
            try:
                server.send_message(msg)
                logging.info("Email sent successfully")
                return True
            except Exception as e:
                logging.error(f"Failed to send email: {str(e)}")
                return False
        
    except Exception as e:
        logging.error(f"Failed to send verification email: {str(e)}", exc_info=True)
        return False

def create_verification_token(email: str) -> str:
    """Create a JWT token for email verification."""
    expire = datetime.utcnow() + timedelta(minutes=VERIFICATION_TOKEN_EXPIRE_MINUTES)
    to_encode = {"exp": expire, "email": email}
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(token: str) -> Optional[str]:
    """Verify the JWT token and return the email if valid."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        email = payload.get("email")
        if email is None:
            return None
        return email
    except jwt.JWTError:
        return None

def validate_email_address(email: str) -> bool:
    """Validate email address format."""
    try:
        validate_email(email)
        return True
    except EmailNotValidError:
        return False

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password) 