from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from botbuilder.integration.aiohttp import CloudAdapter, ConfigurationBotFrameworkAuthentication
from botbuilder.schema import Activity
from bot import MCPTeamsBot
from mcp_client import MCPClientManager
from intent_manager import IntentManager
from session_manager import session_manager
from config import settings
import requests
from botbuilder.core import TurnContext, MessageFactory
import logging
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# optional shared requests session (kept for compatibility)
req = requests.Session()

# create a single MCP client manager instance and reuse the shared session_manager
mcp_client = MCPClientManager(settings.mcp_server_url)
bot_instance: MCPTeamsBot | None = None

class DefaultConfig:
    """ Bot Configuration """
    PORT = 3978
    APP_ID = settings.microsoft_app_id
    APP_PASSWORD = settings.microsoft_app_password
    APP_TYPE = "SingleTenant"
    APP_TENANTID = getattr(settings, "microsoft_app_tenant_id", "")
    
CONFIG = DefaultConfig()

# --------------------------------------------
# Bot Adapter (CloudAdapter)
# --------------------------------------------
ADAPTER = CloudAdapter(
    ConfigurationBotFrameworkAuthentication(
        CONFIG
    )
)

@asynccontextmanager
async def lifespan(app):
    global bot_instance
    logger.info("Starting application and connecting to MCP server.")
    try:
        await mcp_client.connect()
        logger.info("Connected to MCP server.")
        intent = IntentManager(settings.openai_api_key, settings.openai_model)
        bot_instance = MCPTeamsBot(mcp_client, intent)
        logger.info("Bot instance initialized.")
        
        # Send welcome message if we have conversation references stored
        try:
            # Using the updated implementation that retrieves conversation references from session_manager
            await bot_instance.send_welcome_message()
            logger.info("Welcome message sent.")
        except Exception as e:
            logger.error(f"Failed to send welcome message: {e}")
            
        logger.info("Ready to serve requests.")
        yield
    finally:
        logger.info("Shutting down application.")
        try:
            await mcp_client.disconnect()
            logger.info("Disconnected from MCP server.")
        except Exception as e:
            logger.exception("Error during shutdown disconnect: %s", e)

# pass lifespan when creating the FastAPI app
app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root() -> dict:
    return {"message": "MCP Teams Bot is running."}

@app.post("/api/messages")
async def messages(req: Request) -> Response:
    """Main bot message handler."""
    if not bot_instance:
        return Response(status_code=503, content="Bot is not initialized.")

    body = await req.json()
    activity = Activity().deserialize(body)

    auth_header = req.headers.get("Authorization", "")

    # process_activity expects (activity, auth_header, callback)
    response = await ADAPTER.process_activity(auth_header, activity, bot_instance.on_turn)
    if response:
        return Response(status_code=response.status)
    return Response(status_code=201)

@app.post("/auth/callback")
async def auth_callback(request: Request) -> JSONResponse:
    """Handle authentication callback from external login flow."""
    payload = await request.json()
    user_id = payload.get("user_id")
    session_data = payload.get("session_data")

    if not user_id:
        return JSONResponse(status_code=400, content={"error": "user_id is required"})

    # persist session server-side
    session_manager.create_session(user_id, session_data)
    logger.info("User %s logged in via callback.", user_id)

    # notify bot instance if available
    if bot_instance:
        try:
            await bot_instance.handle_login_callback(user_id, session_data)
        except Exception:
            logger.exception("Error invoking bot handle_login_callback for user %s", user_id)

    return JSONResponse(status_code=200, content={"status": "ok"})

@app.get("/tools")
async def list_tools():
    """List available MCP tools"""
    try:
        tools = await mcp_client.list_tools()
        return JSONResponse(status_code=200, content={"tools": tools})
    except Exception as e:
        logger.exception("Error listing tools: %s", e)
        return JSONResponse(status_code=500, content={"error": str(e)})
    
@app.get("/tools/{tool_name}/schema")
async def get_tool_schema(tool_name: str):
    """Get input schema for a specific tool"""
    try:
        schema = await mcp_client.get_tool_schema(tool_name)
        if schema is None:
            return JSONResponse(status_code=404, content={"error": "Tool not found"})
        return JSONResponse(status_code=200, content={"schema": schema})
    except Exception as e:
        logger.exception("Error getting tool schema for %s: %s", tool_name, e)
        return JSONResponse(status_code=500, content={"error": str(e)})
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.bot_port)

