# hellohealth — LiveKit Appointment Scheduling Agent

This repository contains a LiveKit-powered voice agent that collects patient intake information and schedules appointments. It includes validation helpers (email, phone, address via Smarty), a simulated scheduling workflow, and an email notification integration (SendGrid).

This README explains how to run the agent locally, required environment variables, the extra validation features implemented, how the emailing API is wired, and debugging tips.

**Repository layout**

- `agent.py` — Main LiveKit agents: `IntakeAgent` and `SchedulingAgent` with @function_tool tools for each patient field.
- `utils.py` — Validation and helper utilities (email/phone/address validation, prompt loader, physicians CSV loader, availability helpers, and email send helper).
- `prompts/` — YAML prompt files used for agent instructions.
- `fakedata/physicians.csv` — Fake physicians availability data used for testing.
- `emails.txt` — Destination addresses for appointment notification emails (one per line).
- `pyproject.toml` / `requirements.txt` — Project dependencies.

**Quick overview**

- The flow starts with `IntakeAgent` collecting patient details (name, DOB, insurance, reason for visit, address, phone, email preference). When intake is complete the flow transfers to `SchedulingAgent`, which collects preferred appointment date/time and referral info, checks availability, and sends a confirmation email.
- Utilities in `utils.py` provide robust validation:
	- Email validation using `email_validator` (async wrapper).
	- Phone parsing & formatting using `phonenumbers` (async wrapper).
	- Address validation using Smarty (SmartyStreets) SDK via an async wrapper that runs the blocking SDK in an executor to avoid blocking the event loop.
	- Physician lookup and fake availability loaded from `fakedata/physicians.csv`.
	- Email notification using SendGrid (currently implemented as a helper that calls SendGrid's blocking client; see notes below for async options).

Requirements

- Python 3.10+
- Install dependencies with your preferred tool. Example (pip):

```bash
python -m pip install -r livekit-hellohealth/requirements.txt
```

Or using the `pyproject.toml` in a modern environment:

```bash
pip install -e .
```

Environment variables

- `SMARTY_AUTH_ID` and `SMARTY_AUTH_TOKEN` — Credentials for Smarty (SmartyStreets) address validation.
- `SENDGRID_API_KEY` — API key used by the SendGrid client to send emails.
- Optionally: other secrets for LiveKit / OpenAI / TTS services used in `agent.py` depending on your deployment.

How to run the agent locally

1. Ensure a LiveKit deployment or use a compatible development environment for LiveKit workers.
2. Populate a `.env.local` (or export env vars) with the required keys listed above.
3. Run pip install -r requirements.txt
3. Start the agent from the repo root:

```bash
python livekit-hellohealth/agent.py

Notes:
- The `entrypoint` in `agent.py` builds an `AgentSession` and calls `session.start(...)`. In production you will run this worker with the LiveKit worker options or deploy as part of your LiveKit worker pool.

Validation features (details)

- Email validation (`verify_email`) — Uses `email_validator` to ensure a syntactically valid address. The function is async-friendly and logs failures.
- Phone validation (`verify_phone`) — Uses `phonenumbers` to parse and return international-format phone numbers when valid. Returns `None` when invalid.
- Address validation (`get_valid_addresses`) — Uses `smartystreets_python_sdk` (SmartyStreets). Because the official SDK call is blocking, the function runs it in the default asyncio threadpool via `asyncio.get_running_loop().run_in_executor(...)`. It returns up to 3 formatted candidate addresses.
	- If the Smarty credentials are missing or the lookup fails, the function logs and returns an empty list; the agent asks the user to re-enter the address.
- Physician validation (`verify_physician`) — Loads `fakedata/physicians.csv` and attempts to match a normalized doctor name. Returns a canonical name when matched or a list of valid names otherwise.
- Availability helper (`get_avaliability`) — Uses the loaded physician schedule to check if a requested time is available; it will round to the nearest 30-minute slot or return the closest match for a specific physician.

Emailing API

- `send_email_sendgrid(to_email, subject, content)` — Helper that constructs a `sendgrid.helpers.mail.Mail` and sends it with `SendGridAPIClient` using `SENDGRID_API_KEY` env var. This helper is currently synchronous (blocking).
- `send_email(userdata)` — Async wrapper used by the agents. It prepares a multi-line email body (converted to HTML) and iterates the addresses loaded from `emails.txt`, calling `send_email_sendgrid` for each address. The function returns `True` on success and `False` on any failure.

Notes & recommended improvements

- Non-blocking email sends: the current SendGrid helper is blocking. For heavy production use, either run the SendGrid calls in an executor (like the Smarty wrapper) or use an async HTTP client to call SendGrid's REST API directly to avoid blocking the event loop.
- Smarty concurrency: if you expect high concurrency for address lookups, consider calling Smarty with an async HTTP client (no SDK), or use a dedicated threadpool sized to expected load.
- Credentials: store sensitive keys in a secure secrets manager or environment rather than committing them to disk. `.env.local` is shown for local development convenience only.

Debugging tips

- Breakpoints: add `breakpoint()` in Python 3.7+ or `import pdb; pdb.set_trace()` for interactive debugging while running locally.
- Logging: the code uses the module-level `logger` — increase verbosity by setting `logging.basicConfig(level=logging.DEBUG)` when needed.

Development checklist

- [ ] Verify env vars are set: `SMARTY_AUTH_ID`, `SMARTY_AUTH_TOKEN`, `SENDGRID_API_KEY`.
- [ ] Populate `fakedata/physicians.csv` with sample availability in HH:MM slots.
- [ ] Populate `emails.txt` with one or more recipient addresses.
- [ ] Run the agent and exercise the intake + scheduling flows.
