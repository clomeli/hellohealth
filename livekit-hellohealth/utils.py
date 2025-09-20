import os
import yaml

import time
import random
import csv
from typing import Dict, List, Optional, Tuple
import re
from datetime import datetime

import dateparser

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

import phonenumbers
from phonenumbers import NumberParseException, is_valid_number, format_number, PhoneNumberFormat

from email_validator import validate_email, EmailNotValidError

import asyncio

from smartystreets_python_sdk import StaticCredentials, ClientBuilder
from smartystreets_python_sdk.us_street import Lookup

import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

async def verify_email(email: str) -> bool:
    """Validate an email address.

    Returns True when `email` is valid according to `email_validator`, otherwise False.
    This function catches validation errors and logs them for debugging.
    """
    try:
        _ = validate_email(email)  # throws if invalid
        return True
    except EmailNotValidError as exc:
        logger.info("Email validation failed for %s: %s", email, exc)
        return False
    except Exception:
        logger.exception("Unexpected error validating email: %s", email)
        return False

async def verify_phone(phone: str, region: str = "US") -> Optional[str]:
    """Parse and validate a phone number.

    Returns an international formatted phone string when valid, otherwise None.
    """
    try:
        parsed = phonenumbers.parse(phone, region)
        if is_valid_number(parsed):
            return format_number(parsed, PhoneNumberFormat.INTERNATIONAL)
        return None
    except NumberParseException as exc:
        logger.info("Phone parse error for %s: %s", phone, exc)
        return None
    except Exception:
        logger.exception("Unexpected error parsing phone: %s", phone)
        return None

async def get_valid_addresses(address: str) -> list[str]:
    """Validate a freeform address string using Smarty (SmartyStreets) when available.

    This function runs the blocking SDK call in a threadpool via
    `asyncio.get_running_loop().run_in_executor(...)` to avoid blocking the event loop.
    """

    logger.info("Looking up address: %s", address)
    auth_id = os.environ.get("SMARTY_AUTH_ID")
    auth_token = os.environ.get("SMARTY_AUTH_TOKEN")

    # Build client and lookup object (blocking SDK calls will be executed in executor)
    credentials = StaticCredentials(auth_id, auth_token)
    client = ClientBuilder(credentials).build_us_street_api_client()
    lookup = Lookup()
    # Provide the freeform address in the `street` field; Smarty will attempt to parse it.
    lookup.street = address
    lookup.candidates = 3  # max candidates to return

    loop = asyncio.get_running_loop()
    try:
        # client.send_lookup is blocking; run in default threadpool
        await loop.run_in_executor(None, client.send_lookup, lookup)
    except Exception:
        logger.exception("Smarty lookup failed for address: %s", address)
        return []

    # `lookup.result` is a list of candidate objects
    result = getattr(lookup, "result", None)

    logger.info(result)
    formatted = []
    for result in result:
        formatted.append(result.delivery_line_1 + ", " + result.last_line)

    return formatted

def to_date_string(date_str: str) -> str:
    """Parse a natural-language date and return it as MM-DD-YYYY.

    Raises ValueError when parsing fails.
    """
    dt = dateparser.parse(date_str)
    if not dt:
        logger.info("to_date_string could not parse: %s", date_str)
        raise ValueError(f"Invalid date: {date_str}")
    return dt.strftime("%m-%d-%Y")

def to_time_string(date_str: str) -> str:
    """Parse a natural-language time and return it as HH:MM (24-hour).

    Raises ValueError when parsing fails.
    """
    dt = dateparser.parse(date_str)
    if not dt:
        logger.info("to_time_string could not parse: %s", date_str)
        raise ValueError(f"Invalid time: {date_str}")
    return dt.strftime("%H:%M")

def load_prompt(filename):
    """Load a prompt from a YAML file in `prompts/`.

    Returns the `instructions` field or an empty string on error.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_path = os.path.join(script_dir, "prompts", filename)
    
    try:
        with open(prompt_path, 'r') as file:
            prompt_data = yaml.safe_load(file)
            return prompt_data.get('instructions', '')
    except (FileNotFoundError, yaml.YAMLError) as e:
        logger.exception("Error loading prompt file %s: %s", filename, e)
        return ""

def load_emails(filename="emails.txt") -> List[str]:
    """Load a list of email addresses from a text file in the project root.

    Returns a list of email strings, or an empty list on error.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    email_path = os.path.join(script_dir, filename)

    try:
        with open(email_path, 'r') as file:
            emails = [line.strip() for line in file if line.strip()]
            return emails
    except FileNotFoundError:
        logger.exception("Emails file not found: %s", email_path)
        return []
    except Exception:
        logger.exception("Failed to load emails from file: %s", email_path)
        return []

def send_email_sendgrid(to_email: str, subject: str, content: str):
    message = Mail(
        from_email='scheduling@hellohealth.live',
        to_emails=to_email,
        subject=subject,
        html_content=content
    )
    sg = SendGridAPIClient(os.getenv('SENDGRID_API_KEY'))
    try:
        response = sg.send(message)
        print("Status:", response.status_code)
        return response.status_code, response.body
    except Exception as e:
        print("Error sending with SendGrid:", e)
        raise

async def send_email(userdata) -> bool:
    """Prepare and (stub) send an email summary of the appointment request.

    This is a placeholder. Integrate with a real email provider in production.
    Returns True on success.
    """
    try:
        email_content = f"""
        Thank you for calling HelloHealth. Here are the details of your appointment request:

        Patient Name: {userdata.patient_name}
        Date and Time: {userdata.appointment_info.appointment_date} {userdata.appointment_info.appointment_time}
        Physician: {userdata.appointment_info.physician}
        Date of Birth: {userdata.date_of_birth}
        Insurance Payer: {userdata.insurance_payer_name}
        Insurance ID: {userdata.insurance_id}
        Reason for Visit: {userdata.reason_for_visit}
        Address: {userdata.address}
        Phone Number: {userdata.phone_number}
        Email: {userdata.email}
        """
        logger.info("Simulated send email with content:\n%s", email_content)
    except Exception:
        logger.exception("Failed to prepare/send email")
        return False
    html_content = email_content.replace("\n", "<br>")

    emails = load_emails()
    if not emails:
        logger.error("No emails loaded to send notification to.")
        return False
    
    for email in emails:
        status, _ = send_email_sendgrid(email, "New Appointment Request", html_content)
        if status != 202:
            logger.error("Failed to send email to %s, status code: %s", email, status)
            return False
    
    return True

# Regex to strip "Dr." if present
def normalize_name(name: str) -> str:
    """Normalize a physician's name by removing a leading 'Dr.' and trimming whitespace."""
    pattern = r"^(?:Dr\.?\s+)?([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)"
    match = re.match(pattern, name.strip())
    return match.group(1) if match else name.strip()

def verify_physician(physician: str) -> Tuple[bool, Optional[List[str]]]:
    """Check whether the provided physician name matches names in the fake physicians CSV.

    Returns (True, [matches]) if found; otherwise (False, list_of_all_names).
    """
    physician_info = load_physicians("physicians.csv")
    cleaned_name = normalize_name(physician)
    for doc in physician_info.keys():
        if cleaned_name.lower() in doc.lower():
            return True, [doc]
    return False, physician_info.keys()

async def get_avaliability(time_str: str, physician: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Return an available (physician, time) tuple for the requested slot.

    If `physician` is provided, prefer that physician and return the nearest time.
    If `physician` is None, search for the first physician with a matching rounded time slot.
    """
    physician_info = load_physicians("physicians.csv")
    if physician is not None:
        if time_str in physician_info[physician]:
            return physician, time_str
        return physician, nearest_time(time_str, physician_info[physician])

    rounded = round_to_nearest_half_hour(time_str)
    for doc, times in physician_info.items():
        if rounded in times:
            return doc, rounded
    return None, None

# AI Gened function not throughly vetted
def nearest_time(target: str, times: List[str]) -> str:
    """Return the closest time string in `times` to the `target` time (HH:MM).

    Raises ValueError when no valid times are provided.
    """
    t = datetime.strptime(target, "%H:%M")
    t_minutes = t.hour * 60 + t.minute

    closest = None
    min_diff = float("inf")

    for time_str in times:
        candidate = datetime.strptime(time_str, "%H:%M")
        c_minutes = candidate.hour * 60 + candidate.minute
        diff = abs(c_minutes - t_minutes)

        if diff < min_diff:
            min_diff = diff
            closest = time_str

    return closest

# AI Gened function not throughly vetted
def round_to_nearest_half_hour(time_str: str) -> str:
    """Round a HH:MM time string to the nearest 30-minute slot."""
    t = datetime.strptime(time_str, "%H:%M")
    minutes = t.hour * 60 + t.minute
    rounded = round(minutes / 30) * 30
    new_hour, new_minute = divmod(rounded, 60)
    rounded_time = t.replace(hour=new_hour % 24, minute=new_minute)
    return rounded_time.strftime("%H:%M")

def load_physicians(csv_file: str) -> Dict[str, List[str]]:
    """Load physicians' availability from a CSV file in `fakedata/`.

    Each row should start with the physician's name followed by zero or more HH:MM time slots.
    Returns a dict mapping physician name -> list of HH:MM strings.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, "fakedata", csv_file)

    schedule: Dict[str, List[str]] = {}
    try:
        with open(csv_path, newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                physician = row[0].strip()
                times = [t.strip() for t in row[1:] if t.strip()]
                schedule[physician] = times
    except FileNotFoundError:
        logger.exception("Physicians CSV not found: %s", csv_path)
    except Exception:
        logger.exception("Failed to load physicians CSV: %s", csv_path)
    return schedule


