import asyncio
from datetime import datetime

from livekit.agents import JobContext, cli, mcp
from livekit.agents.llm import ChatContext, ChatMessage
from livekit.agents.voice import Agent, AgentSession
from livekit.agents.worker import WorkerOptions
from livekit.plugins import assemblyai, elevenlabs, google

from app.agents.prompt import BASE_INSTRUCTIONS
from app.core.logger import logger
from app.core.settings import settings

JAPANESE_VOICE_ID = "j210dv0vWm7fCknyQpbA"

# Filler phrases for natural conversation flow
FILLER_PHRASES = [
    "はい、少々お待ちください",  # "Yes, one moment please"
    "かしこまりました、確認いたします",  # "Understood, let me check"
]


class Appointment(Agent):
    def __init__(self) -> None:
        current_date = datetime.now().strftime("%Y-%m-%d %A")
        instructions = BASE_INSTRUCTIONS.format(current_date=current_date)
        super().__init__(
            instructions=instructions,
            mcp_servers=[
                mcp.MCPServerHTTP(
                    url=settings.MCP_SERVER_URL,
                )
            ],
        )
        # Track filler task for cancellation
        self._filler_task: asyncio.Task | None = None
        self._filler_index = 0

    async def on_enter(self) -> None:
        pass

    async def on_user_turn_completed(
        self,
        turn_ctx: ChatContext,
        new_message: ChatMessage,
    ) -> None:
        """
        Triggered when user finishes speaking.
        Start filler audio immediately to reduce perceived latency.
        The filler will be interrupted automatically when the real response starts.
        """
        # Cancel any previous filler task
        if self._filler_task and not self._filler_task.done():
            self._filler_task.cancel()

        # Start new filler task
        self._filler_task = asyncio.create_task(self._play_filler())

    async def _play_filler(self) -> None:
        """
        Play acknowledgment filler - gets interrupted by real LLM response.
        Small delay to avoid playing for instant responses.
        """
        try:
            # Small delay to avoid playing filler for quick responses
            await asyncio.sleep(0.3)

            # Get next filler phrase (rotate through phrases)
            filler = FILLER_PHRASES[self._filler_index % len(FILLER_PHRASES)]
            self._filler_index += 1

            logger.info(f"🎤 Playing filler: {filler}")
            await self.session.say(filler)
        except asyncio.CancelledError:
            logger.debug("Filler cancelled - real response started")
        except Exception as e:
            logger.warning(f"Filler playback error (non-fatal): {e}")


async def entrypoint(ctx: JobContext) -> None:
    logger.info("Agents Starting in room: %s", ctx.room)
    await ctx.connect()

    stt = assemblyai.STT(model="universal-streaming-multilingual")
    llm_plugin = google.LLM(model="gemini-2.5-flash")
    tts = elevenlabs.TTS(
        model="eleven_multilingual_v2",
        api_key=settings.ELEVEN_LABS_API_KEY,
        # voice_id=JAPANESE_VOICE_ID,
    )

    session = AgentSession(
        stt=stt,
        llm=llm_plugin,
        tts=tts,
    )

    await session.start(room=ctx.room, agent=Appointment())


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, agent_name="Barber-Agent"))
