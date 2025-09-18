import os
import yaml

import dateparser
import time
import random

import phonenumbers
from phonenumbers import NumberParseException, is_valid_number, format_number, PhoneNumberFormat
from email_validator import validate_email, EmailNotValidError

def verify_email(email: str) -> bool:
    try:
        v = validate_email(email)  # throws if invalid
        return True
    except EmailNotValidError:
        return False

def verify_phone(phone: str, region: str = "US") -> str:
    try:
        parsed = phonenumbers.parse(phone, region)
        print(f"parsed phone number: {parsed}")
        if is_valid_number(parsed):
            return format_number(parsed, PhoneNumberFormat.INTERNATIONAL)
        else:
            return None
    except NumberParseException:
        return None

def to_epoch(date_str: str) -> int:
    dt = dateparser.parse(date_str)
    print(f"og date '{date_str}' to datetime object: {dt}")
    return int(time.mktime(dt.timetuple()))

def load_prompt(filename):
    """Load a prompt from a YAML file."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_path = os.path.join(script_dir, "prompts", filename)
    
    try:
        with open(prompt_path, 'r') as file:
            prompt_data = yaml.safe_load(file)
            return prompt_data.get('instructions', '')
    except (FileNotFoundError, yaml.YAMLError) as e:
        print(f"Error loading prompt file {filename}: {e}")
        return "" 

def sendEmail(userdata) -> bool:
    # Here you would integrate with an actual email service
    email_content = f"""
        Thank you for calling HelloHealth. Here are the details of your appointment request, we look forward to seeing you!
        Date and Time: {userdata.appointment_info.preferred_appointment_date} {userdata.appointment_info.preferred_appointment_time}
        Physician: {userdata.appointment_info.referred_physician}
        Patient Name: {userdata.patient_name}
        Date of Birth: {userdata.date_of_birth}
        Insurance Payer: {userdata.insurance_payer_name}
        Insurance ID: {userdata.insurance_id}
        Reason for Visit: {userdata.reason_for_visit}
        Address: {userdata.address}
        Phone Number: {userdata.phone_number}
        Email: {userdata.email}"""
    print("Sending email with the following content:")
    print(email_content)
    return True

def checkAvaliability(date_str: str, time_str: str, doctor: str) -> bool:
    # Dummy implementation, in real life this would check a database or API
    # Return a random True/False to simulate availability
    return random.choice([True, False])