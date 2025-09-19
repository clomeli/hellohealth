import os
import yaml

import dateparser
import time
import random
import csv
from typing import Dict, List, Optional, Tuple
import re
from datetime import datetime


import phonenumbers
from phonenumbers import NumberParseException, is_valid_number, format_number, PhoneNumberFormat
from email_validator import validate_email, EmailNotValidError
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def verify_email(email: str) -> bool:
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

def verify_phone(phone: str, region: str = "US") -> Optional[str]:
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

def send_email(userdata) -> bool:
    """Prepare and (stub) send an email summary of the appointment request.

    This is a placeholder. Integrate with a real email provider in production.
    Returns True on success.
    """
    try:
        email_content = (
            f"Thank you for calling HelloHealth. Here are the details of your appointment request:\n"
            f"Date and Time: {userdata.appointment_info.appointment_date} {userdata.appointment_info.appointment_time}\n"
            f"Physician: {userdata.appointment_info.physician}\n"
            f"Patient Name: {userdata.patient_name}\n"
            f"Date of Birth: {userdata.date_of_birth}\n"
            f"Insurance Payer: {userdata.insurance_payer_name}\n"
            f"Insurance ID: {userdata.insurance_id}\n"
            f"Reason for Visit: {userdata.reason_for_visit}\n"
            f"Address: {userdata.address}\n"
            f"Phone Number: {userdata.phone_number}\n"
            f"Email: {userdata.email}\n"
        )
        logger.info("Simulated send email with content:\n%s", email_content)
        return True
    except Exception:
        logger.exception("Failed to prepare/send email")
        return False

# Regex to strip "Dr." if present
def normalize_name(name: str) -> str:
    """Normalize a doctor's name by removing a leading 'Dr.' and trimming whitespace."""
    pattern = r"^(?:Dr\.?\s+)?([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)"
    match = re.match(pattern, name.strip())
    return match.group(1) if match else name.strip()

def verify_doctor(doctor: str) -> Tuple[bool, Optional[List[str]]]:
    """Check whether the provided doctor name matches names in the fake doctors CSV.

    Returns (True, [matches]) if found; otherwise (False, list_of_all_names).
    """
    doctor_info = load_doctors("fakedata/doctors.csv")
    cleaned_name = normalize_name(doctor)
    for doc in doctor_info.keys():
        if cleaned_name.lower() in doc.lower():
            return True, [doc]
    return False, doctor_info.keys()

def get_avaliability(time_str: str, physician: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Return an available (doctor, time) tuple for the requested slot.

    If `physician` is provided, prefer that physician and return the nearest time.
    If `physician` is None, search for the first doctor with a matching rounded time slot.
    """
    doctor_info = load_doctors("fakedata/doctors.csv")
    if physician is not None:
        if time_str in doctor_info[physician]:
            return physician, time_str
        return physician, nearest_time(time_str, doctor_info[physician])

    rounded = round_to_nearest_half_hour(time_str)
    for doc, times in doctor_info.items():
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

def load_doctors(csv_file: str) -> Dict[str, List[str]]:
    """Load doctors' availability from a CSV file in `fakedata/`.

    Each row should start with the doctor's name followed by zero or more HH:MM time slots.
    Returns a dict mapping doctor name -> list of HH:MM strings.
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
                doctor = row[0].strip()
                times = [t.strip() for t in row[1:] if t.strip()]
                schedule[doctor] = times
    except FileNotFoundError:
        logger.exception("Doctors CSV not found: %s", csv_path)
    except Exception:
        logger.exception("Failed to load doctors CSV: %s", csv_path)
    return schedule


