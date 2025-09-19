import os
import yaml

import dateparser
import time
import random
import csv
from typing import Dict, List
import re

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

def to_date_string(date_str: str) -> str:
    dt = dateparser.parse(date_str)
    # Format however you want
    return dt.strftime("%m-%d-%Y")

def to_time_string(date_str: str) -> str:
    dt = dateparser.parse(date_str)
    # Format however you want
    return dt.strftime("%H:%M")

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
    print("Preparing to send email...")
    email_content = f"""
        Thank you for calling HelloHealth. Here are the details of your appointment request, we look forward to seeing you!
        Date and Time: {userdata.appointment_info.appointment_date} {userdata.appointment_info.appointment_time}
        Physician: {userdata.appointment_info.physician}
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

# Regex to strip "Dr." if present, AI Gened function not throughly vetted
def normalize_name(name: str) -> str:
    pattern = r"^(?:Dr\.?\s+)?([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)"
    match = re.match(pattern, name.strip())
    return match.group(1) if match else name.strip()

def verify_doctor(doctor: str) -> tuple[bool, list[str] | None]:
    doctor_info = load_doctors("fakedata/doctors.csv")
    cleaned_name = normalize_name(doctor)
    for doc in doctor_info.keys():
        if cleaned_name.lower() in doc.lower():
            return True, [doc]
    return False, doctor_info.keys()

from datetime import datetime


def getAvaliability(datetime_str: str, physician: str) -> tuple[str | None, str | None]:
    print("Requested availability for", physician, "at", time_str)
    doctor_info = load_doctors("fakedata/doctors.csv")
    time_str = datetime_str.split(" ")[1]  # Extract time part
    if physician is not None:
        if time_str in doctor_info[physician]:
            return physician, datetime_str
        else:
            return physician, datetime_str.split(" ")[0] + nearest_time(time_str, doctor_info[physician])
    else:
        time = round_to_nearest_half_hour(time_str)
        for doc, times in doctor_info.items():
            if time in times:
                return doc, datetime_str.split(" ")[0] + time
    return None, None

# AI Gened function not throughly vetted
def nearest_time(target: str, times: list[str]) -> str:
    # Parse target into minutes
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
    t = datetime.strptime(time_str, "%H:%M")
    minutes = t.hour * 60 + t.minute
    rounded = round(minutes / 30) * 30
    new_hour, new_minute = divmod(rounded, 60)
    rounded_time = t.replace(hour=new_hour % 24, minute=new_minute)
    return rounded_time.strftime("%H:%M")

def load_doctors(csv_file: str) -> Dict[str, List[str]]:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_path = os.path.join(script_dir, "fakedata", "doctors.csv")
    schedule = {}
    with open(csv_file, newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:  # skip empty lines
                continue
            doctor = row[0].strip()
            times = [t.strip() for t in row[1:] if t.strip()]
            schedule[doctor] = times
    return schedule


