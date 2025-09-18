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

from utils import load_prompt, sendEmail, to_epoch, getAvaliability, verify_phone, verify_email

load_dotenv(".env.local")

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
    email: str | None = None
    appointment_info: AppointmentInfo = AppointmentInfo()

class SchedulingAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=load_prompt('scheduling_prompt.yaml'))
    
    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions="""
                Thank them for the info and now find out their preferred appointment date and time.
            """,
        )

    @function_tool()
    async def record_has_referral(self, context: RunContext[PatientInfo], has_referral: bool):
        """Record the referred physician's name."""
        # store referral info in the nested appointment_info
        context.userdata.appointment_info.has_referral = has_referral
        return self._handoff_if_done()
    
    @function_tool()
    async def record_physician(self, context: RunContext[PatientInfo], physician: str):
        """Record the referred physician's name."""
        # TODO validate physician name against known list
        context.userdata.appointment_info.physician = physician
        return self._handoff_if_done()

    @function_tool()
    async def record_appointment_date(self, context: RunContext[PatientInfo], appointment_date: str):
        """Record the user's preferred appointment date."""
        context.userdata.appointment_info.appointment_date = appointment_date
        return self._handoff_if_done()

    @function_tool()
    async def record_appointment_time(self, context: RunContext[PatientInfo], appointment_time: str):
        """Record the user's preferred appointment time."""
        context.userdata.appointment_info.appointment_time = appointment_time
        return self._handoff_if_done()
    
    def _handoff_if_done(self):
        ai = self.session.userdata.appointment_info

        if ai.appointment_date is not None and ai.appointment_time is not None:
            # If user indicated they have a referral, ensure we have the referring physician
            if ai.has_referral is True and ai.physician is None:
                return "You mentioned you have a referral, please provide the referring physician's name."
            # Prompt the user to confirm before scheduling
            return "Information collected. Please confirm that these details are correct to schedule the appointment."
        else:
            return (
                "Information recorded. Continue gathering missing details. "
                "Insist it is necessary; do not proceed until all required information is collected. "
                "Don't say goodbye; stay on the line until they hang up."
            )
    
    @function_tool()
    async def confirm_and_end(self, context: RunContext[PatientInfo], confirmed: bool):
        """When the user confirms all details, check avaliability and sendemail."""
        if confirmed:
            print("Final collected patient info:", self.session.userdata) # Debugging line
            ai = self.session.userdata.appointment_info
            success, err = await self._finalize_and_close()
            if success:
                return "We have scheduled your appointment. Thank you for choosing HelloHealth. Goodbye!"
            if err == "time_unavailable":
                return self._provideOtherTimes()
            return "Sorry, there was an error scheduling your appointment. Please call again later."
        else:
            return "Here are the details you provided. Please let me know what details need to be updated, or confirm if they are correct."

    async def _finalize_and_close(self) -> tuple[bool, str | None]:
        """Perform availability check, send notification, reply, and close the session.

        Returns (success, error_code) where error_code may be 'time_unavailable' or 'email_failed'.
        """
        ai = self.session.userdata.appointment_info

        # 1) Check availability
        try:
            available = getAvaliability(ai.appointment_time, ai.physician)
            print(f"Availability check returned: {available}")
        except Exception:
            available = False

        if not available:
            return False, "time_unavailable"

        # 2) Send email / perform scheduling
        try:
            emailed = sendEmail(self.session.userdata)
        except Exception:
            emailed = False

        if not emailed:
            return False, "email_failed"

        # 3) Send final spoken/text reply before closing
        try:
            await self.session.generate_reply(
                instructions=(
                    "Thank you — your appointment request has been scheduled. "
                    "We'll follow up with confirmation by email. Goodbye!"
                )
            )
        except Exception:
            pass

        # 4) Close the session
        try:
            await self.session.close()
        except Exception:
            pass

        return True, None
    
    def _provideOtherTimes(self):
        return """Sorry, that time is not available. Here are some other available times near it.
         Please select one. Generate a list of 3 available times within 2 days of the requested date and time."""

    @function_tool()
    async def accepted_alternative(self, context: RunContext[PatientInfo], accepted_alternative: bool):
        """When the user accepts an alternative time, finalize the appointment."""
        if accepted_alternative:
            success, err = await self._finalize_and_close()
            if success:
                return "We have scheduled your appointment. Thank you for choosing HelloHealth. Goodbye!"
            return "Sorry, there was an error scheduling your appointment. Please call again later."
        else:
            return self._provideOtherTimes()


class IntakeAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=load_prompt('intake_prompt.yaml'))


    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions="""
                Introduce yourself as HelloHealth appointment scheduling assistant.
                And that you need some patient information to schedule their appointment.",
            """
        )

    @function_tool()
    async def record_name(self, context: RunContext[PatientInfo], name: str):
        """Use this tool to record the user's name."""
        context.userdata.patient_name = name
        return self._handoff_if_done()

    @function_tool()
    async def record_date_of_birth(self, context: RunContext[PatientInfo], date_of_birth: str):
        """Record the user's date of birth."""
        context.userdata.date_of_birth = date_of_birth
        return self._handoff_if_done()

    @function_tool()
    async def record_insurance_payer_name(self, context: RunContext[PatientInfo], insurance_payer_name: str):
        """Record the user's insurance payer name."""
        context.userdata.insurance_payer_name = insurance_payer_name
        return self._handoff_if_done()

    @function_tool()
    async def record_insurance_id(self, context: RunContext[PatientInfo], insurance_id: str):
        """Record the user's insurance ID or policy number."""
        context.userdata.insurance_id = insurance_id
        return self._handoff_if_done()

    @function_tool()
    async def record_reason_for_visit(self, context: RunContext[PatientInfo], reason_for_visit: str):
        """Record the reason for the user's visit."""
        context.userdata.reason_for_visit = reason_for_visit
        return self._handoff_if_done()

    @function_tool()
    async def record_address(self, context: RunContext[PatientInfo], address: str):
        """Record the user's address."""
        context.userdata.address = address
        return self._handoff_if_done()

    @function_tool()
    async def record_phone_number(self, context: RunContext[PatientInfo], phone_number: str):
        """Record the user's phone number."""
        parsed = verify_phone(phone_number)
        print(parsed)
        if parsed:
            context.userdata.phone_number = parsed
        else:
            return "The phone number provided seems invalid. Please provide a valid phone number including area code."
        return self._handoff_if_done()

    @function_tool()
    async def record_email(self, context: RunContext[PatientInfo], email: str):
        """Record the user's email address."""
        if verify_email(email):
            context.userdata.email = email
        else:
            return "The email address provided seems invalid. Please provide a valid email address."
        return self._handoff_if_done()

    def _handoff_if_done(self):
        def all_info_collected(userdata: PatientInfo) -> bool:
            return all([
                userdata.patient_name is not None,
                userdata.date_of_birth is not None,
                userdata.insurance_payer_name is not None,
                userdata.insurance_id is not None,
                userdata.reason_for_visit is not None,
                userdata.address is not None,
                userdata.phone_number is not None,
                userdata.email is not None,
            ])
        print("Current collected info:", self.session.userdata) # Debugging line
        if all_info_collected(self.session.userdata):
            return "All information collected. Confirm all user details before scheduling the appointment. Spell out the spelling of the full legal name."
        else:
            return """ Information recorded. Continue gathering missing details.
             Insist it is neccesary, do not proceed until all required information is collected.
             Email is not required but highly reccomended. 
             Don't say goodbye, stay on the line until they hang up."""

    @function_tool()
    async def confirm_and_end(self, context: RunContext[PatientInfo], confirm: bool):
        """When the user confirms all details, forward to SchedulingAgent."""
        if confirm:
            print("Final collected patient info:", self.session.userdata) # Debugging line
            return SchedulingAgent()
        else:
            return "Okay, please let me know what details need to be updated."

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
        agent=SchedulingAgent(),
        room_input_options=RoomInputOptions(
            # For telephony applications, use `BVCTelephony` instead for best results
            noise_cancellation=noise_cancellation.BVC(), 
        ),
    )
if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))