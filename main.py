from botbuilder.core import TurnContext
from botbuilder.integration.aiohttp import CloudAdapter, ConfigurationBotFrameworkAuthentication
from botbuilder.schema import Activity
from aiohttp import web
from agent_bot import AgentTeamsBot
from agents import Agent
from agents.mcp import MCPServerStdio
from config import settings
from session_manager import SessionManager
import asyncio
import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def main():
    class DefaultConfig:
        PORT = settings.bot_port
        APP_ID = settings.microsoft_app_id
        APP_PASSWORD = settings.microsoft_app_password
        APP_TENANTID = settings.microsoft_app_tenant_id
        APP_TYPE = "SingleTenant"

    CONFIG = DefaultConfig()

    logger.info("Initializing bot with config:")
    logger.info(f"  Port: {CONFIG.PORT}")
    logger.info(f"  App ID: {CONFIG.APP_ID}")
    logger.info(f"  Tenant ID: {CONFIG.APP_TENANTID}")

    adapter = CloudAdapter(
        ConfigurationBotFrameworkAuthentication(CONFIG)
    )

    async def on_error(context: TurnContext, error: Exception):
        logger.error(f"Error caught by adapter: {error}", exc_info=True)
        await context.send_activity("Sorry, something went wrong. Please try again.")

    adapter.on_turn_error = on_error

    logger.info("Starting MCP server...")

    bot_app_dir = os.path.dirname(os.path.abspath(__file__))
    mcp_server_path = os.path.join(bot_app_dir, "mcp_server.py")

    logger.info(f"MCP server path: {mcp_server_path}")

    async with MCPServerStdio(
        name="OMG MCP Server",
        params={
            "command": "python",
            "args": [mcp_server_path]
        },
    ) as mcp_server:
        logger.info("MCP server connected successfully")

        try:
            logger.info("Fetching system prompt from MCP server...")
            prompt_result = await mcp_server.get_prompt("system_prompt")
            instructions = prompt_result.messages[0].content.text
            logger.info(f"System prompt loaded ({len(instructions)} characters)")
        except Exception as e:
            logger.error(f"Failed to load system prompt: {e}")
            instructions = "You are an OMG project management assistant. Help users manage tasks and navigate the system."

        logger.info("Creating agent...")
        agent = Agent(
            name="OMG Assistant",
            instructions=instructions,
            mcp_servers=[mcp_server],
        )
        logger.info("Agent created successfully")

        session_manager = SessionManager()
        logger.info("Session manager initialized")

        bot = AgentTeamsBot(agent, session_manager)
        logger.info("Bot initialized successfully")

        async def messages(req: web.Request) -> web.Response:
            if "application/json" not in req.headers.get("Content-Type", ""):
                logger.warning("Received request with invalid content type")
                return web.Response(status=415)

            try:
                body = await req.json()
            except Exception as e:
                logger.error(f"Failed to parse request body: {e}")
                return web.Response(status=400)

            activity = Activity().deserialize(body)
            auth_header = req.headers.get("Authorization", "")

            logger.info(f"Incoming activity type: {activity.type}")
            if activity.text:
                logger.info(f"From: {activity.from_property.id}, Text: {activity.text}")

            try:
                await adapter.process_activity(auth_header, activity, bot.on_turn)
                return web.Response(status=200)
            except Exception as exception:
                logger.error(f"Error processing activity: {exception}", exc_info=True)
                raise exception

        app = web.Application()
        app.router.add_post("/api/messages", messages)

        logger.info(f"Starting web server on http://localhost:{settings.bot_port}")

        try:
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", settings.bot_port)
            await site.start()

            logger.info(f"Bot is running on http://localhost:{settings.bot_port}")
            logger.info("Bot is ready to receive messages")
            logger.info(f"Active sessions: {session_manager.get_session_count()}")

            await asyncio.Event().wait()

        except Exception as e:
            logger.error(f"Error starting web server: {e}", exc_info=True)
            raise
        finally:
            logger.info("Shutting down...")
            await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)

