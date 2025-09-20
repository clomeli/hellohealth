from dotenv import load_dotenv
from dataclasses import dataclass

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, function_tool, RunContext
from livekit.plugins import (
    openai,
    cartesia,
    deepgram,
    noise_cancellation,
    silero,
)
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit.agents.beta.workflows import GetEmailTask

from utils import load_prompt, send_email, get_avaliability, verify_phone, verify_email, verify_physician, to_date_string, to_time_string

load_dotenv(".env.local")
import logging

# Module logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

@dataclass 
class AppointmentInfo:
    has_referral: bool | None = None
    physician: str | None = None
    appointment_date: str | None = None
    appointment_time: str | None = None

@dataclass
class PatientInfo:
    patient_name: str | None = None
    date_of_birth: str | None = None
    insurance_payer_name: str | None = None
    insurance_id: str | None = None 
    reason_for_visit: str | None = None
    address: str | None = None
    phone_number: str | None = None
    provide_email: bool | None = None
    email: str | None = None
    appointment_info: AppointmentInfo = AppointmentInfo()

class SchedulingAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=load_prompt('scheduling_prompt.yaml'))
    
    async def on_enter(self) -> None:
        try:
            await self.session.generate_reply(
                instructions=(
                    "Thank you for the information. I will collect your preferred "
                    "appointment date and time now."
                ),
            )
        except Exception:
            logger.exception("Failed to send on_enter reply")

    @function_tool()
    async def record_has_referral(self, context: RunContext[PatientInfo], has_referral: bool):
        """Record whether the patient has a referral."""
        # store referral info in the nested appointment_info
        context.userdata.appointment_info.has_referral = has_referral
        return await self._handoff_if_done(context)
    
    @function_tool()
    async def record_physician(self, context: RunContext[PatientInfo], physician: str):
        """Record the physician name after validating against our provider list."""
        try:
            success, valid_names = verify_physician(physician)
        except Exception:
            logger.exception("verify_physician failed")
            return "Sorry — I couldn't validate the physician right now. Please try again or continue without a referral."

        if success and valid_names:
            context.userdata.appointment_info.physician = valid_names[0]
            return await self._handoff_if_done(context)

        choices = ", ".join(valid_names) if valid_names else ""
        return (
            f"The physician name provided does not match our records. Valid names are: {choices}. "
            "Please provide a valid physician name or say 'continue without a referral'."
        )

    @function_tool()
    async def record_appointment_date(self, context: RunContext[PatientInfo], appointment_date: str):
        """Record the user's preferred appointment date."""
        try:
            formatted_date = to_date_string(appointment_date)
        except Exception:
            logger.exception("Invalid appointment date: %s", appointment_date)
            return "The date provided seems invalid. Please provide a valid date for your appointment."

        context.userdata.appointment_info.appointment_date = formatted_date
        return await self._handoff_if_done(context)

    @function_tool()
    async def record_appointment_time(self, context: RunContext[PatientInfo], appointment_time: str):
        """Record the user's preferred appointment time."""
        logger.info("Raw appointment time input: %s", appointment_time)
        try:
            formatted_time = to_time_string(appointment_time)
        except Exception:
            logger.exception("Invalid appointment time: %s", appointment_time)
            return "The time provided seems invalid. Please provide a valid time for your appointment."
        logger.info("formatted appointment time input: %s", formatted_time)
        context.userdata.appointment_info.appointment_time = formatted_time
        return await self._handoff_if_done(context)
    
    async def _handoff_if_done(self, context: RunContext[PatientInfo]) -> str:
        """Check whether we have enough appointment info and return the next prompt.

        This function returns a short instruction string that the agent will speak.
        It does not perform any side effects.
        """
        ai = self.session.userdata.appointment_info

        if ai.appointment_date and ai.appointment_time and ai.has_referral is not None:
            if ai.has_referral is True and not ai.physician:
                return "You mentioned you have a referral — please provide the referring physician's name."
            return await self.confirm_and_end(context, False)
        return (
            "Information recorded. Continue gathering the missing details. "
            "Please do not end the call until we finish collecting the required information."
        )
    
    @function_tool()
    async def confirm_and_end(self, context: RunContext[PatientInfo], confirmed: bool):
        """When the user confirms all details, check avaliability and send_email."""
        logger.info("User confirmed: %s", confirmed)
        if confirmed:
            logger.info("Final collected patient info: %s", self.session.userdata)

            try:
                success = await self._finalize_datetime_and_send_email()
            except Exception:
                logger.exception("_finalize_datetime_and_send_email failed")
                success = False

            if success:
                ai = self.session.userdata.appointment_info
                try:
                    await self.session.generate_reply(
                            instructions=(
                                "Tell them it was scheduled successfully."
                                "Tell them If an email was provided, a confirmation has been sent. "
                                "Thank them for choosing HelloHealth. Goodbye!"
                            )
                        )
                except Exception:
                    logger.exception("Failed to notify user of final confirmation")

                try:
                    await self.session.aclose()
                except Exception:
                    logger.exception("Failed to close session cleanly")

                return "Goodbye!"
            return "Sorry — there was an error scheduling your appointment. Please call again later."
        else:
            return "Here are the details you provided. Please let me know what details need to be updated, or confirm if they are correct."

    async def _finalize_datetime_and_send_email(self) -> bool:
        """Perform availability check, send notification, reply, and close the session..
        """
        ai = self.session.userdata.appointment_info

        try:
            physician, available_time = await get_avaliability(ai.appointment_time, ai.physician)
        except Exception:
            logger.exception("get_avaliability failed")
            return False

        if not physician or not available_time:
            logger.info("No availability for %s at %s", ai.physician, ai.appointment_time)
            return False
        ai.physician = physician

        if ai.appointment_time != available_time:
            ai.appointment_time = available_time
            try:
                await self.session.generate_reply(
                    instructions=(
                        f"Your preferred time is unavailable. The nearest available time with {physician} is {available_time}; "
                        "I will book that instead."
                    )
                )
            except Exception:
                logger.exception("Failed to notify user of adjusted time")

        try:
            emailed = await send_email(self.session.userdata)
        except Exception:
            logger.exception("send_email failed")
            emailed = False

        if not emailed:
            logger.warning("Email scheduling failed for user: %s", self.session.userdata)
            return False

        return True

class IntakeAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=load_prompt('intake_prompt.yaml'))


    async def on_enter(self) -> None:
        try:
            await self.session.generate_reply(
                instructions=(
                    "Introduce yourself as the HelloHealth appointment scheduling assistant "
                    "and explain that you need some patient information to schedule an appointment."
                ),
            )
        except Exception:
            logger.exception("Failed to send on_enter reply for IntakeAgent")

    @function_tool()
    async def record_name(self, context: RunContext[PatientInfo], name: str):
        """Use this tool to record the user's name."""
        context.userdata.patient_name = name
        return await self._handoff_if_done(context)

    @function_tool()
    async def record_date_of_birth(self, context: RunContext[PatientInfo], date_of_birth: str):
        """Record the user's date of birth."""
        context.userdata.date_of_birth = date_of_birth
        return await self._handoff_if_done(context)

    @function_tool()
    async def record_insurance_payer_name(self, context: RunContext[PatientInfo], insurance_payer_name: str):
        """Record the user's insurance payer name."""
        context.userdata.insurance_payer_name = insurance_payer_name
        return await self._handoff_if_done(context)

    @function_tool()
    async def record_insurance_id(self, context: RunContext[PatientInfo], insurance_id: str):
        """Record the user's insurance ID or policy number."""
        context.userdata.insurance_id = insurance_id
        return await self._handoff_if_done(context)

    @function_tool()
    async def record_reason_for_visit(self, context: RunContext[PatientInfo], reason_for_visit: str):
        """Record the reason for the user's visit."""
        context.userdata.reason_for_visit = reason_for_visit
        return await self._handoff_if_done(context)

    @function_tool()
    async def record_address(self, context: RunContext[PatientInfo], address: str):
        """Record the user's address."""
        context.userdata.address = address
        return await self._handoff_if_done(context)

    @function_tool()
    async def record_phone_number(self, context: RunContext[PatientInfo], phone_number: str):
        """Record the user's phone number."""
        try:
            parsed = verify_phone(phone_number)
        except Exception:
            logger.exception("verify_phone failed for: %s", phone_number)
            return "I couldn't validate that phone number right now. Please try again."

        logger.info("Parsed phone number: %s", parsed)
        if parsed:
            context.userdata.phone_number = parsed
        else:
            return "The phone number provided seems invalid. Please provide a valid phone number including area code."
        return await self._handoff_if_done(context)

    @function_tool()
    async def record_email(self, context: RunContext[PatientInfo], email: str):
        """Record the user's email address."""
        try:
            valid = verify_email(email)
        except Exception:
            logger.exception("verify_email failed for: %s", email)
            return "I couldn't validate that email address right now. Please try again."

        if valid:
            context.userdata.email = email
        else:
            return "The email address provided seems invalid. Please provide a valid email address."
        return await self._handoff_if_done(context)

    async def _handoff_if_done(self, context: RunContext[PatientInfo]):
        def all_info_collected(userdata: PatientInfo) -> bool:
            return all([
                userdata.patient_name is not None,
                userdata.date_of_birth is not None,
                userdata.insurance_payer_name is not None,
                userdata.insurance_id is not None,
                userdata.reason_for_visit is not None,
                userdata.address is not None,
                userdata.phone_number is not None,
            ])
        logger.info("Current collected info: %s", self.session.userdata)
        if all_info_collected(self.session.userdata):
            if provided_email is None:
                return (
                    "All required information has been collected. Do you want to provide an email address to receive a confirmation? "
                    "You can say 'yes' to provide an email or 'no' to continue without one."
                )
            if provided_email is True and self.session.userdata.email is None:
                return (
                    "You indicated you want to provide an email address. Please provide your email address now."
                )
            return await self.confirm_and_end(context, False)
                

        return (
            "Information recorded. Continue gathering the missing details. "
            "Please do not end the call until all required information is collected. Providing an email is optional but recommended."
        )

    @function_tool()
    async def confirm_and_end(self, context: RunContext[PatientInfo], confirm: bool):
        """When the user confirms all details, forward to SchedulingAgent."""
        if confirm:
            logger.info("Final collected patient info: %s", self.session.userdata)
            try:
                await self.session.generate_reply(
                    instructions=(
                        "Thank you for providing your information. If you would like, "
                        "please provide an email address to receive a confirmation."
                    ),
                )
            except Exception:
                logger.exception("Failed to send confirmation prompt before handoff")

            return SchedulingAgent()
        else:
            return "Here are the details you provided. Please let me know what details need to be updated, or confirm if they are correct."

async def entrypoint(ctx: agents.JobContext):
    session = AgentSession[PatientInfo](
        userdata=PatientInfo(),
        stt=deepgram.STT(model="nova-3", language="multi"),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=cartesia.TTS(model="sonic-2", voice="f786b574-daa5-4673-aa0c-cbe3e8534c02"),
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
    )

    await session.start(
        room=ctx.room,
        agent=IntakeAgent(),
        room_input_options=RoomInputOptions(
            # For telephony applications, use `BVCTelephony` instead for best results
            noise_cancellation=noise_cancellation.BVC(), 
        ),
    )
if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))