"""
Japanese Worker for AI Voice Agent - Testing Purpose

Run with:
    PYTHONPATH=. uv run app/agents/worker.py dev
"""

import asyncio
import logging
import time
from datetime import datetime

from livekit import rtc
from livekit.agents import AutoSubscribe, JobContext, cli, mcp
from livekit.agents.voice import Agent, AgentSession
from livekit.agents.worker import WorkerOptions
from livekit.plugins import deepgram, elevenlabs, openai

from app.agents.prompt import BASE_INSTRUCTIONS
from app.core.logger import logger
from app.core.settings import settings
from app.db import SessionLocal
from app.db.schema import AiCallIntent
from app.services import user_service
from app.services.ai_call_log_service import AiCallLogService

# Suppress verbose debug logs from OpenAI and httpx
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("openai._base_client").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def log_timing(label: str, start_time: float) -> float:
    """Log elapsed time since start_time and return current time for chaining."""
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    logger.info(f"⏱️  [{label}] took {elapsed_ms:.1f}ms")
    return time.perf_counter()


JAPANESE_VOICE_ID = "j210dv0vWm7fCknyQpbA"

# 🔥 PRE-WARM MCP SERVER (LOAD ONCE)
MCP_SERVER = mcp.MCPServerHTTP(
    url=settings.MCP_SERVER_URL,
    timeout=10.0,  # INCREASED from 1.0s - give tools time to execute
)


async def wait_for_room_disconnect(room: rtc.Room):
    while room.connection_state != rtc.ConnectionState.CONN_DISCONNECTED:
        await asyncio.sleep(0.2)


class Appointment(Agent):
    def __init__(
        self,
        initial_context: str = "",
        user_name: str | None = None,
        caller_phone: str | None = None,
    ) -> None:
        current_date = datetime.now().strftime("%Y-%m-%d %A")
        instructions = BASE_INSTRUCTIONS.format(
            current_date=current_date,
            caller_phone=caller_phone or "unknown",
            caller_name=user_name or "not yet provided",
        )

        # Append the pre-fetched context
        instructions += f"\n\n{initial_context}"

        super().__init__(
            instructions=instructions,
        )
        # Track filler task for cancellation
        self._filler_task: asyncio.Task | None = None
        self._filler_index = 0
        self._user_name = user_name

    async def on_enter(self) -> None:
        logger.info("Agent (JP) entered connection.")


async def entrypoint(ctx: JobContext) -> None:
    # ===== TIMING: ENTRYPOINT START =====
    print("🚀 [DEBUG] ENTRYPOINT CALLED - PRINT TO STDOUT")
    # entrypoint_start = time.perf_counter()
    # logger.info("🚀 [TIMING] Entrypoint started (Japanese)")

    # Wait a moment for room connection to stabilize
    await asyncio.sleep(1.0)

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    # _ = log_timing("Room Connect", entrypoint_start)

    transcript_messages: list[dict] = []
    call_log_id: str | None = None

    # Interruption state tracking
    was_interrupted = False

    # -------------------------------------------------
    # Detect caller phone (SIP)
    # -------------------------------------------------
    # sip_start = time.perf_counter()
    caller_phone = None

    # First, check existing participants
    for participant in ctx.room.remote_participants.values():
        if participant.identity.startswith("sip-"):
            caller_phone = participant.identity.replace("sip-", "")
            break

    # If not found, wait for participant to connect
    if not caller_phone:

        async def wait_for_sip_participant():
            nonlocal caller_phone
            timeout = 10
            start = datetime.utcnow()

            while (datetime.utcnow() - start).total_seconds() < timeout:
                for participant in ctx.room.remote_participants.values():
                    if participant.identity.startswith("sip-"):
                        caller_phone = participant.identity.replace("sip-", "")
                        return
                await asyncio.sleep(0.1)

            # logger.warning("Timeout waiting for SIP participant")

        await wait_for_sip_participant()

    # _ = log_timing("SIP Participant Detection", sip_start)
    # logger.info(f"📞 [TIMING] Caller phone: {caller_phone or 'unknown'}")
    # logger.info(f"📞 [DEBUG] Detected caller_phone value: '{caller_phone}'")

    # -------------------------------------------------
    # Fetch user
    # -------------------------------------------------
    # user_lookup_start = time.perf_counter()
    user = None
    user_context = "User Context: New User"
    # greeting = "Thank you for calling Earth San Barber Shop. May I have your name please?"
    greeting = "お電話ありがとうございます。Earth Sanでございます。お名前を伺ってもよろしいでしょうか？"

    try:
        async with SessionLocal() as db:
            # Fetch user if phone number is available
            if caller_phone:
                logger.info(f"👤 [DEBUG] Looking up user with phone: '{caller_phone}'")
                user = await user_service.get_user_by_phone(caller_phone, db)
                if user:
                    logger.info(f"✅ [DEBUG] User FOUND: {user.full_name} (ID: {user.id})")

                    user_context = (
                        f"USER INFORMATION:\n"
                        f"Status: Registered Customer\n"
                        f"Name: {user.full_name}\n"
                        f"User ID: {user.id}\n"
                        f"Phone: {caller_phone}"
                    )
                    # greeting = f"Hello {user.full_name}! Thank you for calling Earth San Barber Shop. How can I help you today?"
                    greeting = f"{user.full_name}様、お電話ありがとうございます。Earth Sanでございます。"
                    logger.info(f"👋 [DEBUG] Set greeting for registered user: '{greeting}'")
                else:
                    logger.warning(f"❌ [DEBUG] User NOT FOUND with phone: '{caller_phone}'")
                    # New user - just include services
                    user_context = f"USER INFORMATION:\nStatus: New Customer\nPhone: {caller_phone}"
                    logger.info("👋 [DEBUG] Set greeting for new user")
            else:
                logger.warning("⚠️  [DEBUG] No caller_phone available, cannot lookup user")
    except Exception:
        logger.exception("User lookup failed")

    # _ = log_timing("User Lookup", user_lookup_start)
    # logger.info(f"👤 [TIMING] User found: {user.full_name if user else 'New User'}")

    # -------------------------------------------------
    # Create AI Call Log
    # -------------------------------------------------
    # call_log_start = time.perf_counter()
    async with SessionLocal() as db:
        call_log_id = await AiCallLogService.create(
            db=db,
            phone_number=caller_phone or "unknown",
            user_id=user.id if user else None,
            intent=AiCallIntent.INQUIRY,
        )
    # _ = log_timing("Call Log Creation", call_log_start)

    # -------------------------------------------------
    # Audio / AI pipeline - OPTIMIZED FOR JAPANESE
    # -------------------------------------------------
    # pipeline_start = time.perf_counter()

    # Deepgram STT with Japanese language support
    stt = deepgram.STT(
        api_key=settings.DEEPGRAM_API_KEY,
        model="nova-2",  # Nova-2 is robust for Japanese
        language="ja",  # Japanese language
        interim_results=True,
        endpointing_ms=300,  # Matches default/standard for reliable endpointing
        smart_format=True,
    )

    # OpenAI LLM
    llm = openai.LLM(
        api_key=settings.OPENAI_API_KEY,
        model="gpt-4o",
        temperature=0.4,
        tool_choice="auto",
        max_completion_tokens=150,
    )

    # ElevenLabs TTS - Optimized for streaming with low latency
    tts = elevenlabs.TTS(
        api_key=settings.ELEVEN_LABS_API_KEY,
        model="eleven_multilingual_v2_5",  # Multilingual model for Japanese
        voice_id=JAPANESE_VOICE_ID,
        encoding="mp3_44100_128",  # Ensure this matches your room settings
        chunk_length_schedule=[50, 50, 90, 150],  # Experimental: Send smaller audio chunks first
    )

    # VAD - DISABLED as per instruction (use Deepgram endpointing)
    # vad = silero.VAD.load(...)

    # Create Contexts
    # _ = log_timing("Pipeline Init (STT/LLM/TTS/VAD)", pipeline_start)

    # -------------------------------------------------
    # VoicePipelineAgent Initialization
    # -------------------------------------------------
    # session_start = time.perf_counter()
    session = AgentSession(
        stt=stt,
        llm=llm,
        tts=tts,
        # vad=vad,
        # Restoring MCP tools
        mcp_servers=[MCP_SERVER],
        allow_interruptions=True,
        min_endpointing_delay=0.1,  # 300ms delay before processing speech end
        preemptive_generation=True,  # Stream LLM output to TTS immediately
        min_interruption_duration=0.5,  # Prevent self-interruption from agent's own speech
        min_interruption_words=1,  # Require at least 1 word to interrupt
    )

    # session = AgentSession(llm=openai.realtime.RealtimeModel(model="gpt-realtime"))
    # _ = log_timing("Session Creation", session_start)

    # -------------------------------------------------
    # FILLER STATE for immediate acknowledgment
    # -------------------------------------------------
    filler_index = 0
    filler_task: asyncio.Task | None = None
    user_name_for_filler = user.full_name if user else None

    # FILLER PHRASES - Japanese polite forms
    # -------------------------------------------------
    FILLER_PHRASES_WITH_NAME = [
        "{name}様、ありがとうございます。少々お待ちください",  # Thank you {name}, one moment
        "{name}様、お待たせして申し訳ございません。確認いたします",  # Sorry to keep you waiting {name}, check
        "ありがとうございます、{name}様。少しお時間いただきます",  # Thank you {name}, need a moment
    ]

    FILLER_PHRASES_ANONYMOUS = [
        "ありがとうございます。少々お待ちください",  # Thank you, one moment
        "お待たせして申し訳ございません。確認いたします",  # Sorry, check
        "かしこまりました。少しお時間いただきます",  # Understood, need a moment
    ]

    async def play_filler_immediately():
        """Play acknowledgment filler immediately when user stops speaking."""
        nonlocal filler_index
        try:
            # NO DELAY - play immediately!
            if user_name_for_filler:
                phrases = FILLER_PHRASES_WITH_NAME
                filler = phrases[filler_index % len(phrases)].format(name=user_name_for_filler)
            else:
                phrases = FILLER_PHRASES_ANONYMOUS
                filler = phrases[filler_index % len(phrases)]

            filler_index += 1
            # CRITICAL FIX: allow_interruptions=False prevents the agent from hearing its own filler
            # and pausing the LLM stream (Self-Interruption Bug).
            await session.say(filler, allow_interruptions=False)
            logger.info(f"⚡ [TIMING] Playing filler (Uninterruptible): '{filler}'")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"Filler playback error (non-fatal): {e}")

    # -------------------------------------------------
    # EVENT HANDLERS
    # -------------------------------------------------
    @session.on("user_started_speaking")
    def on_user_started_speaking(ev):
        """User started speaking - they may be interrupting"""
        print("⚡ [DEBUG] USER STARTED SPEAKING")
        nonlocal was_interrupted, filler_task
        was_interrupted = True
        # Cancel any playing filler or greeting when user starts speaking
        if filler_task and not filler_task.done():
            filler_task.cancel()

    @session.on("user_stopped_speaking")
    def on_user_stopped_speaking(ev):
        """User finished speaking - Realtime handles response natively"""
        print("⚡ [DEBUG] USER STOPPED SPEAKING")
        # DISABLED FOR OPENAI REALTIME: Realtime API handles acknowledgment natively
        # nonlocal filler_task
        # logger.info("🟢 [TIMING] USER STOPPED SPEAKING - Playing immediate acknowledgment")
        # filler_task = asyncio.create_task(play_filler_immediately())

    @session.on("user_input_transcribed")
    def on_user_input(ev):
        nonlocal filler_task
        try:
            text = (ev.transcript or "").strip()

            # ONLY process final transcripts
            if not ev.is_final:
                return

            if not text:
                return

            # Log only final user transcripts
            # logger.info(f"🎤 [USER] '{text}'")

            transcript_messages.append(
                {
                    "role": "user",
                    "content": text,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

            if call_log_id:
                asyncio.create_task(
                    AiCallLogService.append_message_async(
                        log_id=call_log_id,
                        role="user",
                        content=str(text),
                    )
                )

            # 🔥 FORCE COMMIT: Don't wait for VAD - process immediately!
            # This fixes the "speech scheduling paused" / no reply issue
            session.commit_user_turn(
                transcript_timeout=0.0,
                stt_flush_duration=0.0,
            )
            # logger.info("⚡ [TIMING] Turn committed - triggering LLM")
        except Exception as e:
            logger.error(f"Error in user input handler: {e}")

    @session.on("conversation_item_added")
    def on_conversation_item(ev):
        msg = ev.item
        if msg.role != "assistant":
            return

        text = " ".join(msg.content).strip()
        if not text:
            return

        # logger.info(f"🤖 [AGENT] '{text}'")

        transcript_messages.append(
            {
                "role": "assistant",
                "content": text,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

        if call_log_id:
            asyncio.create_task(
                AiCallLogService.append_message_async(
                    log_id=call_log_id,
                    role="assistant",
                    content=str(text),
                )
            )

    @session.on("agent_started_speaking")
    def on_agent_started_speaking(ev):
        nonlocal filler_task
        # logger.info("🔊 [TIMING] AGENT SPEAKING")
        if filler_task and not filler_task.done():
            filler_task.cancel()

    # -------------------------------------------------
    # Start Agent
    # -------------------------------------------------
    # agent_start = time.perf_counter()
    agent = Appointment(
        initial_context=user_context,
        caller_phone=caller_phone,
        user_name=user.full_name if user else None,
    )
    # _ = log_timing("Agent Creation", agent_start)

    # session_start_time = time.perf_counter()
    await session.start(room=ctx.room, agent=agent)
    # _ = log_timing("Session Start", session_start_time)

    # FIRE AND FORGET greeting
    async def play_greeting():
        try:
            # Disable audio input during greeting to prevent echoes
            session.input.set_audio_enabled(False)
            # logger.info("🔇 [TIMING] Audio input disabled for greeting")

            # Wait for audio to be fully ready
            await asyncio.sleep(1.0)
            await session.say(greeting, allow_interruptions=True)
            # logger.info("✅ [TIMING] Greeting finished playing")

            # Re-enable audio input to listen for user speech
            session.input.set_audio_enabled(True)
            logger.info("🔊 [TIMING] Audio input re-enabled - ready to listen")
        except Exception as e:
            logger.warning(f"Greeting playback error: {e}")
            # Ensure audio input is re-enabled even if greeting fails
            session.input.set_audio_enabled(True)

    # logger.debug(f"DEBUG {ctx.room.local_participant}")
    # logger.debug(f"DEBUG {ctx.room.remote_participants}")

    asyncio.create_task(play_greeting())
    # logger.info("🎤 [TIMING] Greeting triggered")

    # ===== TIMING: TOTAL INITIALIZATION =====
    # total_init_ms = (time.perf_counter() - entrypoint_start) * 1000
    # logger.info(f"🏁 [TIMING] Total initialization completed in {total_init_ms:.1f}ms")

    # -------------------------------------------------
    # Wait for call end
    # -------------------------------------------------
    await wait_for_room_disconnect(ctx.room)
    await asyncio.sleep(0.3)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, agent_name="Barber-Agent-JP"))
