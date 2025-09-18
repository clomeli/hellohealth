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

from utils import load_prompt

load_dotenv(".env.local")

@dataclass 
class AppointmentInfo:
    referred_physician: str | None = None
    preferred_appointment_date: str | None = None
    preferred_appointment_time: str | None = None

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
                Thank them for the info and now find out their preferred appointment date and time.",
            """
        )
    
    @function_tool()
    async def record_referred_physician(self, context: RunContext[PatientInfo], referred_physician: str):
        """Record the referred physician's name."""
        context.userdata.referred_physician = referred_physician
        return self._handoff_if_done()

    @function_tool()
    async def record_preferred_appointment_date(self, context: RunContext[PatientInfo], preferred_appointment_date: str):
        """Record the user's preferred appointment date."""
        context.userdata.preferred_appointment_date = preferred_appointment_date
        return self._handoff_if_done()

    @function_tool()
    async def record_preferred_appointment_time(self, context: RunContext[PatientInfo], preferred_appointment_time: str):
        """Record the user's preferred appointment time."""
        context.userdata.preferred_appointment_time = preferred_appointment_time
        return self._handoff_if_done()
    
    def _handoff_if_done(self):
        def all_info_collected(userdata: PatientInfo) -> bool:
            return all([
                userdata.appointment_info.preferred_appointment_date is not None,
                userdata.appointment_info.preferred_appointment_time is not None,
            ])
        print("Current collected info:", self.session.userdata) # Debugging line
        if all_info_collected(self.session.userdata):
            return "All information collected. Confirm all user details before scheduling the appointment."
        else:
            return "Information recorded. Continue gathering missing details. Insist it is neccesary, do not proceed until all required information is collected. Don't say goodbye, stay on the line until they hang up."
    
    @function_tool()
    async def confirm_and_end(self, context: RunContext[PatientInfo], confirm: bool):
        """When the user confirms all details, forward to SchedulingAgent."""
        if confirm:
            print("Final collected patient info:", self.session.userdata) # Debugging line
            return "I will now schedule your appointment. Thank you for choosing HelloHealth. Goodbye!"
        else:
            return "Okay, please let me know what details need to be updated."

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
        context.userdata.phone_number = phone_number
        return self._handoff_if_done()

    @function_tool()
    async def record_email(self, context: RunContext[PatientInfo], email: str):
        """Record the user's email address."""
        context.userdata.email = email
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
        agent=IntakeAgent(),
        room_input_options=RoomInputOptions(
            # For telephony applications, use `BVCTelephony` instead for best results
            noise_cancellation=noise_cancellation.BVC(), 
        ),
    )
if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))