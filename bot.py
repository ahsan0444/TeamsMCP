from botbuilder.core import ActivityHandler, TurnContext, MessageFactory, BotAdapter
from botbuilder.schema import Activity, ActivityTypes, Attachment, ConversationReference
from typing import Any, Dict, List, Optional, Union
import logging
import json
import asyncio
import inspect
import datetime
from datetime import timezone, timedelta
from intent_manager import IntentManager
from mcp_client import MCPClientManager
from session_manager import session_manager
from cards import create_login_card, success_card, error_card, create_task_creation_card
import cards as cards_module
from config import settings
from utils import pick_base_url, absolutize_url, normalize_data, find_task_in_payload

logger = logging.getLogger(__name__)


class MCPTeamsBot(ActivityHandler):
    def __init__(self, mcp_manager: MCPClientManager, intent_manager: IntentManager):
        # Inject the MCP client manager and centralized intent manager
        self.mcp_manager = mcp_manager
        self.session_manager = session_manager
        self.intent = intent_manager
        super().__init__()

    async def send_welcome_message(self):
        """Send a welcome message to all stored conversations."""
        conversation_references = self.session_manager.get_all_conversation_references()
        if not conversation_references:
            logger.info("No conversation references found to send welcome message")
            return
            
        for user_id, conv_ref in conversation_references.items():
            try:
                from main import ADAPTER
                await ADAPTER.continue_conversation(
                    conv_ref,
                    self._welcome_message_activity,
                    settings.microsoft_app_id
                )
                logger.info(f"Sent welcome message to user {user_id}")
            except Exception as e:
                logger.error(f"Failed to send welcome message to {user_id}: {e}")
        
    async def _welcome_message_activity(self, turn_context: TurnContext):
        """Creates and sends the welcome message."""
        welcome_card = {
            "type": "AdaptiveCard",
            "body": [
                {
                    "type": "TextBlock",
                    "text": "👋 Welcome to the MCP Teams Bot!",
                    "weight": "Bolder",
                    "size": "Large"
                },
                {
                    "type": "TextBlock",
                    "text": "I can help you manage tasks and access information from the MCP system.",
                    "wrap": True
                },
                {
                    "type": "TextBlock",
                    "text": "Try asking me to:",
                    "wrap": True
                },
                {
                    "type": "FactSet",
                    "facts": [
                        {"title": "•", "value": "List available tools"},
                        {"title": "•", "value": "Create a task"},
                        {"title": "•", "value": "Show my active session"},
                        {"title": "•", "value": "Get company information"}
                    ]
                }
            ],
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.5"
        }
        
        await turn_context.send_activity(
            MessageFactory.attachment(Attachment(
                content_type="application/vnd.microsoft.card.adaptive",
                content=welcome_card
            ))
        )

    async def _typing_loop(self, turn_context: TurnContext, stop_event: asyncio.Event, interval: float = 2.0):
        try:
            while not stop_event.is_set():
                # Create a proper typing activity with all required fields
                typing_activity = Activity(
                    type=ActivityTypes.typing
                    # recipient_id=turn_context.activity.from_property.id,
                    # from_property=turn_context.activity.recipient,
                    # conversation=turn_context.activity.conversation,
                    # channel_id=turn_context.activity.channel_id,
                    # service_url=turn_context.activity.service_url
                )
                await turn_context.send_activity(typing_activity)
                await asyncio.sleep(interval)
        except Exception as e:
            logger.debug(f"Typing loop stopped or failed: {e}")

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        """Handle incoming messages from users."""
        user_id = turn_context.activity.from_property.id
        session = self.session_manager.get_session(user_id)
        message_text = turn_context.activity.text.strip() if turn_context.activity.text else ""

        # Ensure MCP client has active user context for elicitation
        try:
            self.mcp_manager.set_active_user(user_id)
        except Exception:
            pass

        # Store conversation reference for proactive messages
        conversation_reference = TurnContext.get_conversation_reference(turn_context.activity)
        self.session_manager.store_conversation_reference(user_id, conversation_reference)

        # If user is replying to an elicitation prompt, resolve it and ack
        if self.session_manager.has_pending_elicitation(user_id):
            self.session_manager.resolve_elicitation(user_id, message_text)
            await turn_context.send_activity(MessageFactory.text("Thanks — I sent your response to the server."))
            return

        # Start typing indicator loop while processing this turn
        stop_event = asyncio.Event()
        typing_task = asyncio.create_task(self._typing_loop(turn_context, stop_event))

        try:
            # Handle adaptive card submissions
            if hasattr(turn_context.activity, "value") and turn_context.activity.value:
                logger.info("Processing adaptive card submission from user %s", user_id)
                await self._handle_adaptive_card_submission(turn_context, user_id, session)
                return

            # Handle text commands
            logger.info("Processing message from user %s: %s", user_id, message_text)
            logger.info("Current session for user %s: %s", user_id, session)

            # Refactored: Use a mapping for direct commands to tool names
            command_map = {
                "show session": "show_session",
                "clear session": "logout",
                "login form": "login",
                "login": "login",
                "logout": "logout",
                "list tools": "list_tools",
                "switch site": "get_available_sites",
                "get sites": "get_available_sites",
                "create task": "create_task",
                "company info": "get_user_and_company_info",
            }

            # Check if the message is a known command
            if message_text.lower() in command_map:
                tool_name = command_map[message_text.lower()]
                await self._unified_tool_handler(
                    turn_context=turn_context,
                    user_id=user_id,
                    session=session,
                    tool_name=tool_name,
                    payload={},
                    context_data={}
                )
                return

            # If not a direct command, proceed with AI-based intent detection
            await self._handle_text_commands(turn_context, user_id, session, message_text)
        except Exception as e:
            logger.exception("Error processing message: %s", e)
            await turn_context.send_activity(
                MessageFactory.attachment(error_card(str(e)))
            )
        finally:
            # Stop typing indicator
            stop_event.set()
            try:
                await typing_task
            except Exception:
                pass

    async def _handle_adaptive_card_submission(self, turn_context: TurnContext, user_id: str, session: Optional[str]) -> None:
        """Handle submissions from adaptive cards."""
        submitted_data = turn_context.activity.value
        action = submitted_data.get("action")
        logger.info(f"Adaptive card submission action: {action}, data: {submitted_data}")
        
        
        # Login form submission
        if action == "login":
            await self._handle_login_submission(turn_context, user_id, submitted_data)
            return
        
        # Task creation form submission
        if action == "create_task":
            await self._handle_task_creation(turn_context, user_id, session, submitted_data)
            return
            
        # Handle other tool actions via TOOL_CONFIG
        if action:
            # map action -> tool (use same key by default)
            tool_name = action if action in settings.TOOL_CONFIG else None
            # allow explicit action -> tool mapping via TOOL_CONFIG alias
            if not tool_name:
                # try scanning TOOL_CONFIG for matching card_factory name
                for tname, cfg in settings.TOOL_CONFIG.items():
                    if cfg.get("card_factory") == action or tname == action:
                        tool_name = tname
                        break

            if tool_name:
                logger.info(f"Processing tool action '{tool_name}' for user {user_id}")
                await self._unified_tool_handler(
                    turn_context=turn_context,
                    user_id=user_id,
                    session=session,
                    tool_name=tool_name,
                    payload=submitted_data,
                    context_data={}
                )
                return
                
            
    async def _handle_login_submission(self, turn_context: TurnContext, user_id: str, submitted_data: dict) -> None:
        """Handle login form submission."""
        username = submitted_data.get("username")
        password = submitted_data.get("password")
        if not username or not password:
            await turn_context.send_activity(
                MessageFactory.attachment(error_card("Please enter both username and password."))
            )
            return

        await turn_context.send_activity("🔐 Logging you in...")

        input_data = {"username": username, "password": password}
        
        try:
            login_result = await self.mcp_manager.call_tool("login", input_data)
            logger.info("Login result: %s", login_result)
            
            # Check for successful login
            if isinstance(login_result, dict) and login_result.get("ok"):
                # Store the session data
                self.session_manager.create_session(user_id, login_result)
                logger.info("Session created for user %s", user_id)
                
                # Try to fetch user and company info to verify session is working
                try:
                    user_company_info = await self.mcp_manager.call_tool("get_user_and_company_info")
                    logger.info("User company info: %s", user_company_info)
                    
                    # Store additional user info if successful
                    if isinstance(user_company_info, dict) and user_company_info.get("ok"):
                        self.session_manager.update_session_info(user_id, user_company_info)
                        
                    await turn_context.send_activity(
                        MessageFactory.attachment(success_card("✅ Login successful! You can now create tasks."))
                    )
                except Exception as e:
                    logger.error("Failed to fetch user info after login: %s", e)
                    # Login was successful but user info fetch failed - still consider it a success
                    await turn_context.send_activity(
                        MessageFactory.attachment(success_card("✅ Login successful! You can now create tasks."))
                    )
            else:
                # Login failed
                msg = login_result.get("message") if isinstance(login_result, dict) else str(login_result)
                logger.error("Login failed for user %s: %s", user_id, msg)
                await turn_context.send_activity(
                    MessageFactory.attachment(error_card(f"❌ Login failed: {msg}"))
                )
                
        except Exception as e:
            logger.exception("Error during login process for user %s: %s", user_id, e)
            await turn_context.send_activity(
                MessageFactory.attachment(error_card(f"❌ Login failed: {str(e)}"))
            )


    async def _fetch_user_and_company_info(self, turn_context: TurnContext, user_id: str) -> None:
        """Fetch user and company info after successful login and store in session."""
        try:
            user_company_info = await self.mcp_manager.call_tool("get_user_and_company_info")
            if isinstance(user_company_info, dict) and user_company_info.get("ok"):
                self.session_manager.update_session_info(user_id, user_company_info)
                logger.info("Updated session with user and company info")
        except Exception as e:
            logger.error("Failed to fetch user and company info: %s", e)
            
    async def _handle_text_commands(self, turn_context: TurnContext, user_id: str, session: Optional[str], message_text: str) -> None:
        """Handle free-text messages via AI-driven tool selection or fallback response."""
        tools_list = await self.mcp_manager.list_tools()
        ctx = self.session_manager.get_session_info(user_id) or {}
        ai_decision = await self.intent.decide_tool_or_reply(tools_list, message_text, ctx, user_id=user_id)

        if isinstance(ai_decision, dict) and ai_decision.get("tool_call"):
            tool = ai_decision["tool_call"].get("name")
            payload = ai_decision["tool_call"].get("input", {})

            # If the AI decides to call a tool that should show a card for user confirmation/input,
            # we intercept it here before it goes to the unified_tool_handler.
            await self._unified_tool_handler(
                turn_context=turn_context,
                user_id=user_id,
                session=session,
                tool_name=tool,
                payload=payload,
                context_data={"ai_decision": ai_decision}
            )
            return

        # If no tool call was decided, send the AI's conversational response.
        reply = ai_decision.get("response") if isinstance(ai_decision, dict) else None
        if not reply:
            reply = "I'm your MCP assistant. Ask me to use tools or just chat."
        await turn_context.send_activity(MessageFactory.text(reply))
    async def _handle_task_creation(self, turn_context: TurnContext, user_id: str, session: Optional[str], submitted_data: Dict[str, Any]) -> None:
        """Handle task creation form submission."""
        # ensure user is authenticated
        
        logger.info(f"Handling task creation for user {user_id} with submitted data: {submitted_data}")
        if not session:
            await turn_context.send_activity(
                MessageFactory.attachment(create_login_card(user_id))
            )
            return

        # gather submitted fields (card uses MCP naming where possible)
        planning_parent = submitted_data.get("planningParentId") or str(getattr(settings, "project_id", 7334))
        plan_type = submitted_data.get("plan_type") or getattr(settings, "default_plan_type", "9000")

        start_val = submitted_data.get("start_date")
        end_val = submitted_data.get("end_date")

        # Helper to convert date-or-iso to required ISO datetime with Z (milliseconds)
        def to_iso_utc(dt_str: str, default_hour: int, default_minute: int) -> str:
            if not dt_str:
                return None
            # If already ISO datetime (contains 'T'), accept as-is (normalize Z)
            if "T" in dt_str:
                # ensure Z suffix for UTC if present as +00:00
                try:
                    if dt_str.endswith("+00:00"):
                        return dt_str.replace("+00:00", "Z")
                    return dt_str
                except Exception:
                    pass
            # Expecting YYYY-MM-DD input from Input.Date
            try:
                y, m, d = [int(x) for x in dt_str.split("-")]
                dt = datetime.datetime(y, m, d, default_hour, default_minute, 0, 0, tzinfo=timezone.utc)
                return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
            except Exception:
                # fallback: return raw string
                return dt_str

        # If user provided date-only values, convert to ISO with sensible defaults:
        # default start time = 04:00 UTC, default end time = 12:30 UTC (can be adjusted)
        start_iso = to_iso_utc(start_val, 4, 0) if start_val else None
        end_iso = to_iso_utc(end_val, 12, 30) if end_val else None

        # If neither start nor end provided, create defaults relative to now (start rounded to hour, +8h end)
        if not start_iso and not end_iso:
            now = datetime.datetime.now(timezone.utc)
            start_dt = (now.replace(minute=0, second=0, microsecond=0))
            end_dt = start_dt + timedelta(hours=8)
            start_iso = start_dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
            end_iso = end_dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        elif start_iso and not end_iso:
            # default end: start + 8 hours
            try:
                parsed = datetime.datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
                end_dt = parsed + timedelta(hours=8)
                end_iso = end_dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
            except Exception:
                end_iso = start_iso
        elif end_iso and not start_iso:
            # default start: end - 8 hours
            try:
                parsed = datetime.datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
                start_dt = parsed - timedelta(hours=8)
                start_iso = start_dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
            except Exception:
                start_iso = end_iso

        text_field = submitted_data.get("text") or submitted_data.get("title") or "New task"
        description = submitted_data.get("description") or ""

        # Build the exact task_payload structure expected by the MCP create_task endpoint
        task_payload = {
            "planningParentId": str(planning_parent),
            "plan_type": str(plan_type),
            "start_date": start_iso,
            "end_date": end_iso,
            "text": text_field,
        }
        
        logger.info(f"Constructed task payload for user {user_id}: {task_payload}")
        
        
        if description:
            task_payload["description"] = description

        await turn_context.send_activity("⏳ Creating task...")

        # Use config wrapper name if present (defaults in config.py)
        wrapper = getattr(settings, "tool_param_wrapper", {}).get("create_task", "task_payload")
        call_input = {wrapper: task_payload} if wrapper and isinstance(task_payload, dict) else task_payload

        create_result = await self.mcp_manager.call_tool("create_task", call_input)
        
        logger.info(f"Task creation result for user {user_id}: {create_result}")

        if isinstance(create_result, dict) and create_result.get("ok"):
            await turn_context.send_activity(
                MessageFactory.attachment(success_card("✅ Task created successfully."))
            )
            # send a concise, user-friendly summary card (if URL present show Open link)
            summary_attachment = self._make_task_summary_attachment(create_result)
            if summary_attachment:
                await turn_context.send_activity(MessageFactory.attachment(summary_attachment))
            else:
                summary = self._format_task_result(create_result)
                await turn_context.send_activity(MessageFactory.text(summary))
        else:
            # prefer 'message' or 'response' fields
            msg = None
            if isinstance(create_result, dict):
                msg = create_result.get("message") or create_result.get("response")
            if not msg:
                msg = str(create_result)
            await turn_context.send_activity(
                MessageFactory.attachment(error_card(f"❌ Failed to create task: {msg}"))
            )

    async def _unified_tool_handler(self, turn_context: TurnContext, user_id: str, session: Optional[str], 
                             tool_name: str, payload: Dict[str, Any], context_data: Optional[Dict[str, Any]] = None) -> None:
        """
        Unified handler for all tool actions, centralizing common logic for tool processing.
        
        Args:
            turn_context: The turn context
            user_id: The user ID
            session: The user's session token
            tool_name: The name of the tool to execute
            payload: The payload for the tool
            context_data: Optional additional context data
        """
        try:
            # Check if tool is configured
            tool_config = settings.TOOL_CONFIG.get(tool_name, {})
            
            # For login tool, if no payload is provided, show the login card
            if tool_name == "login" and not payload:
                await turn_context.send_activity(MessageFactory.attachment(create_login_card(user_id)))
                return

            # Ensure user is logged in if required by the tool
            if tool_config.get("requires_login", True) and not session:
                # If login is required and the user is not logged in, show the login card
                await turn_context.send_activity(
                    MessageFactory.attachment(create_login_card(user_id))
                )
                return
                
            # Validate required fields
            required_fields = tool_config.get("required_fields", [])
            missing_fields = [field for field in required_fields if field not in payload]
            if missing_fields:
                await turn_context.send_activity(
                    MessageFactory.attachment(error_card(f"Missing required fields: {', '.join(missing_fields)}"))
                )
                return
                
            # Apply default values
            defaults = tool_config.get("defaults", {})
            for key, value in defaults.items():
                if key not in payload:
                    payload[key] = value
                    
            # Apply parameter wrapper if configured
            param_wrapper = tool_config.get("param_wrapper")
            call_input = {param_wrapper: payload} if param_wrapper and isinstance(payload, dict) else payload
            
            # Call the tool
            await turn_context.send_activity(f"🔧 Running {tool_config.get('display_name', tool_name)}...")
            result = await self.mcp_manager.call_tool(tool_name, call_input)
            
            # If login tool and ok -> create session
            if tool_config.get("auto_create_session") and isinstance(result, dict) and result.get("ok"):
                self.session_manager.create_session(user_id, result)
                await turn_context.send_activity(MessageFactory.attachment(success_card("✅ Login successful.")))
                # try to fetch user info to populate session
                await self._fetch_user_and_company_info(turn_context, user_id)
                return
            
            # Handle result
            if result and isinstance(result, dict) and result.get("ok") is False:
                # Error case
                error_message = result.get("message") or result.get("response") or str(result)
                await turn_context.send_activity(
                    MessageFactory.attachment(error_card(f"❌ Error: {error_message}"))
                )
                return
                
            # Check for result card factory
            result_card_factory = tool_config.get("result_card_factory")
            if result_card_factory:
                # Get the card factory function
                card_factory_fn = getattr(cards_module, result_card_factory, None)
                if card_factory_fn and callable(card_factory_fn):
                    # Special handling for get_available_sites to pass the raw result
                    if tool_name == "get_available_sites":
                        sites = result.get("accessible_sites", [])
                        card = card_factory_fn(sites=sites, user_id=user_id)
                        await turn_context.send_activity(MessageFactory.attachment(card))
                        return

                    # Inspect the card factory for required arguments
                    sig = inspect.signature(card_factory_fn)
                    params = sig.parameters
                    
                    # Prepare the arguments to pass
                    factory_args = {}
                    if "tool_result" in params:
                        factory_args["tool_result"] = result
                    if "user_id" in params:
                        factory_args["user_id"] = user_id
                    if "source_site_id" in params:
                        session_info = self.session_manager.get_session_info(user_id)
                        if session_info and "company" in session_info:
                            factory_args["source_site_id"] = session_info["company"].get("site_id")
                    
                    # Create and send the card
                    card = card_factory_fn(**factory_args)
                    await turn_context.send_activity(MessageFactory.attachment(card))
                    return
                    
            # Fallback to generic summary card or text response
            if isinstance(result, dict):
                # Try to create a summary card
                summary_attachment = self._make_task_summary_attachment(result)
                if summary_attachment:
                    await turn_context.send_activity(MessageFactory.attachment(summary_attachment))
                    return
                    
            # Final fallback to text response
            summary = str(result) if result is not None else "Command completed successfully."
            await turn_context.send_activity(MessageFactory.text(summary))
            
        except Exception as e:
            logger.exception("Error in unified tool handler: %s", e)
            await turn_context.send_activity(
                MessageFactory.attachment(error_card(str(e)))
            )
            
    def _format_task_result(self, result: Any) -> str:
        """Extract task info and return a friendly summary including a redirect icon/link if available."""
        raw_result = result
        logger.info(f"Raw task creation response: {raw_result}")
        result = normalize_data(result)
        task = find_task_in_payload(result)
        if not task:
            try:
                snippet = json.dumps(raw_result, indent=2, default=str)
                logger.warning(f"Task creation response could not be parsed: {snippet}")
                return f"✅ Task created.\n\nRaw response:\n{snippet}"
            except Exception:
                return "✅ Task created. (response received)"
        
        tid = task.get("id") or task.get("task_id") or "unknown"
        title = task.get("text") or task.get("title") or "Untitled"
        plan_type = task.get("plan_type") or task.get("type") or ""
        planning_number = task.get("planning_number")
        item_url = task.get("item_url") or task.get("itemUrl") or ""
        created_by = task.get("created_by_name") or task.get("owner_name") or ""
        start = task.get("start_date") or task.get("start") or ""
        end = task.get("end_date") or task.get("end") or ""

        base = pick_base_url()
        url = absolutize_url(item_url, base)

        parts = [f"✅ Task created: {title} (ID: {tid})"]
        if planning_number:
            parts.append(f"Planning #: {planning_number}")
        if plan_type:
            parts.append(f"Type: {plan_type}")
        if created_by:
            parts.append(f"Created by: {created_by}")
        if start or end:
            parts.append(f"Start: {start}  End: {end}")
        if url:
            # include a redirect icon + link for user convenience
            parts.append(f"🔗 Open task: {url}")

        return "\n".join(parts)

    def _make_task_summary_attachment(self, result: Any) -> Optional[Attachment]:
        """Build an adaptive card attachment with a friendly summary and Open link when available."""
        result = normalize_data(result)
        task = find_task_in_payload(result)
        if not task:
            return None

        
        tid = task.get("id") or task.get("task_id") or "unknown"
        title = task.get("text") or task.get("title") or "Untitled"
        plan_type = task.get("plan_type") or task.get("type") or ""
        planning_number = task.get("planning_number")
        item_url = task.get("item_url") or task.get("itemUrl") or ""
        created_by = task.get("created_by_name") or task.get("owner_name") or ""
        start = task.get("start_date") or task.get("start") or ""
        end = task.get("end_date") or task.get("end") or ""

        base = pick_base_url()
        url = absolutize_url(item_url, base)

        # Build adaptive card
        card = {
            "type": "AdaptiveCard",
            "body": [
                {"type": "TextBlock", "text": f"✅ Task created: {title}", "weight": "Bolder", "size": "Medium", "wrap": True},
                {"type": "TextBlock", "text": f"ID: {tid}" + (f"  •  Planning #: {planning_number}" if planning_number else ""), "wrap": True},
                {"type": "ColumnSet", "columns": [
                    {"type": "Column", "width": "stretch", "items": [
                        {"type": "TextBlock", "text": f"Type: {plan_type}", "wrap": True},
                        {"type": "TextBlock", "text": f"Created by: {created_by}", "wrap": True}
                    ]},
                    {"type": "Column", "width": "auto", "items": [
                        {"type": "TextBlock", "text": f"Start: {start}", "wrap": True},
                        {"type": "TextBlock", "text": f"End: {end}", "wrap": True}
                    ]}
                ]},
            ],
            "actions": [],
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.5"
        }

        if url:
            card["actions"].append({
                "type": "Action.OpenUrl",
                "title": "Open task 🔗",
                "url": url
            })

        return Attachment(content_type="application/vnd.microsoft.card.adaptive", content=card)
