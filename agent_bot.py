from botbuilder.core import ActivityHandler, TurnContext, MessageFactory, CardFactory
from botbuilder.schema import ChannelAccount, Attachment, ActivityTypes
from agents import Agent, Runner
import json
from config import settings
import cards
from session_manager import SessionManager
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class AgentTeamsBot(ActivityHandler):
    def __init__(self, agent: Agent, session_manager: SessionManager):
        self.agent = agent
        self.session_manager = session_manager
        self.config = settings.TOOL_CONFIG

    async def on_message_activity(self, turn_context: TurnContext):
        user_id = turn_context.activity.from_property.id

        if turn_context.activity.value:
            await self._handle_card_submission(turn_context, user_id)
        else:
            await self._handle_user_message(turn_context, user_id)

    async def _handle_user_message(self, turn_context: TurnContext, user_id: str):
        user_text = turn_context.activity.text.strip()

        if not user_text:
            return

        await turn_context.send_activity(MessageFactory.text("Thinking..."))

        self.session_manager.add_to_history(user_id, "user", user_text)

        conversation_history = self.session_manager.get_conversation_history(user_id)

        try:
            result = Runner.run_streamed(
                self.agent,
                input=conversation_history
            )

            response_text = ""
            tool_results = {}
            last_tool_name = None

            async for event in result.stream_events():
                logger.info(f"Event type: {event.type}")

                if event.type == "run_item_stream_event":
                    if event.item.type == "tool_call_item":
                        tool_name = event.item.raw_item.name
                        last_tool_name = tool_name
                        logger.info(f"Tool called: {tool_name}")
                        await turn_context.send_activity(MessageFactory.text(f"Using {tool_name}..."))

                    elif event.item.type == "tool_call_output_item":
                        tool_output = event.item.output
                        logger.info(f"Tool output received: {tool_output}")

                        if last_tool_name:
                            tool_results[last_tool_name] = tool_output

                            tool_config = self.config.get(last_tool_name, {})
                            result_card_factory_name = tool_config.get("result_card_factory")

                            if result_card_factory_name:
                                try:
                                    result_card_factory = getattr(cards, result_card_factory_name)

                                    if isinstance(tool_output, str):
                                        try:
                                            tool_output_data = json.loads(tool_output)
                                        except json.JSONDecodeError:
                                            tool_output_data = tool_output
                                    else:
                                        tool_output_data = tool_output

                                    card_attachment = result_card_factory(tool_output_data)
                                    await turn_context.send_activity(MessageFactory.attachment(card_attachment))

                                    if last_tool_name == "login" and isinstance(tool_output_data, dict):
                                        if tool_output_data.get("ok"):
                                            user_info = tool_output_data.get("user")
                                            company_info = tool_output_data.get("company")
                                            self.session_manager.set_authenticated(user_id, True, user_info, company_info)
                                            logger.info(f"User {user_id} authenticated successfully")

                                    elif last_tool_name == "get_available_sites" and isinstance(tool_output_data, dict):
                                        sites = tool_output_data.get("sites", [])
                                        self.session_manager.set_accessible_sites(user_id, sites)
                                        logger.info(f"Stored {len(sites)} accessible sites for user {user_id}")

                                    elif last_tool_name == "logout":
                                        self.session_manager.delete_session(user_id)
                                        logger.info(f"User {user_id} logged out")

                                except AttributeError:
                                    logger.error(f"Card factory {result_card_factory_name} not found")
                                except Exception as e:
                                    logger.error(f"Error creating result card: {e}")

                    elif event.item.type == "message_output_item":
                        if hasattr(event.item.raw_item, 'content') and event.item.raw_item.content:
                            content = event.item.raw_item.content[0]
                            if hasattr(content, 'text'):
                                response_text = content.text
                                logger.info(f"Agent response: {response_text}")

            if response_text:
                self.session_manager.add_to_history(user_id, "assistant", response_text)
                await turn_context.send_activity(MessageFactory.text(response_text))

        except Exception as e:
            logger.error(f"Error in agent execution: {e}", exc_info=True)
            await turn_context.send_activity(
                MessageFactory.text(f"Sorry, I encountered an error: {str(e)}")
            )

    async def _handle_card_submission(self, turn_context: TurnContext, user_id: str):
        value = turn_context.activity.value
        action = value.get("action")

        logger.info(f"Card submission received. Action: {action}, Data: {value}")

        try:
            if action == "login":
                await self._handle_login_submission(turn_context, user_id, value)
            elif action == "create_task":
                await self._handle_create_task_submission(turn_context, user_id, value)
            elif action == "switch_site":
                await self._handle_switch_site_submission(turn_context, user_id, value)
            else:
                await turn_context.send_activity(
                    MessageFactory.text(f"Unknown action: {action}")
                )
        except Exception as e:
            logger.error(f"Error handling card submission: {e}", exc_info=True)
            error_attachment = cards.error_card(f"Failed to process: {str(e)}")
            await turn_context.send_activity(MessageFactory.attachment(error_attachment))

    async def _handle_login_submission(self, turn_context: TurnContext, user_id: str, value: dict):
        username = value.get("username", "").strip()
        password = value.get("password", "").strip()

        if not username or not password:
            error_attachment = cards.error_card("Username and password are required")
            await turn_context.send_activity(MessageFactory.attachment(error_attachment))
            return

        login_message = f"Please log me in with username: {username}"
        self.session_manager.add_to_history(user_id, "user", login_message)

        conversation_history = self.session_manager.get_conversation_history(user_id)
        conversation_history.append({
            "role": "user",
            "content": f"Use the login tool with username='{username}' and password='{password}'"
        })

        await turn_context.send_activity(MessageFactory.text("Logging in..."))

        result = Runner.run_streamed(self.agent, input=conversation_history)

        async for event in result.stream_events():
            if event.type == "run_item_stream_event" and event.item.type == "tool_call_output_item":
                tool_output = event.item.output

                if isinstance(tool_output, str):
                    try:
                        tool_output = json.loads(tool_output)
                    except:
                        pass

                if isinstance(tool_output, dict) and tool_output.get("ok"):
                    user_info = tool_output.get("user")
                    company_info = tool_output.get("company")
                    self.session_manager.set_authenticated(user_id, True, user_info, company_info)

                    card_attachment = cards.create_company_info_card(tool_output)
                    await turn_context.send_activity(MessageFactory.attachment(card_attachment))
                else:
                    error_attachment = cards.error_card("Login failed. Please check your credentials.")
                    await turn_context.send_activity(MessageFactory.attachment(error_attachment))

    async def _handle_create_task_submission(self, turn_context: TurnContext, user_id: str, value: dict):
        planning_parent_id = value.get("planningParentId", "").strip()
        plan_type = value.get("plan_type", "9000")
        title = value.get("text", "").strip()
        description = value.get("description", "").strip()
        start_date = value.get("start_date", "").strip()
        end_date = value.get("end_date", "").strip()

        if not title:
            error_attachment = cards.error_card("Task title is required")
            await turn_context.send_activity(MessageFactory.attachment(error_attachment))
            return

        if not planning_parent_id:
            error_attachment = cards.error_card("Project ID (planningParentId) is required")
            await turn_context.send_activity(MessageFactory.attachment(error_attachment))
            return

        task_payload = {
            "planningParentId": planning_parent_id,
            "plan_type": plan_type,
            "text": title
        }

        if description:
            task_payload["description"] = description

        if start_date:
            task_payload["start_date"] = self._convert_date_to_iso(start_date)

        if end_date:
            task_payload["end_date"] = self._convert_date_to_iso(end_date)

        create_message = f"Create a task with payload: {json.dumps(task_payload)}"
        self.session_manager.add_to_history(user_id, "user", create_message)

        conversation_history = self.session_manager.get_conversation_history(user_id)
        conversation_history.append({
            "role": "user",
            "content": f"Use the create_task tool with this payload: {json.dumps(task_payload)}"
        })

        await turn_context.send_activity(MessageFactory.text("Creating task..."))

        result = Runner.run_streamed(self.agent, input=conversation_history)

        async for event in result.stream_events():
            if event.type == "run_item_stream_event" and event.item.type == "tool_call_output_item":
                tool_output = event.item.output

                if isinstance(tool_output, str):
                    try:
                        tool_output = json.loads(tool_output)
                    except:
                        pass

                card_attachment = cards.create_task_result_card(tool_output)
                await turn_context.send_activity(MessageFactory.attachment(card_attachment))

    async def _handle_switch_site_submission(self, turn_context: TurnContext, user_id: str, value: dict):
        target_site_id = value.get("target_site_id", "").strip()

        if not target_site_id:
            error_attachment = cards.error_card("Please select a site")
            await turn_context.send_activity(MessageFactory.attachment(error_attachment))
            return

        accessible_sites = self.session_manager.get_accessible_sites(user_id)
        user_info = self.session_manager.get_user_info(user_id)
        company_info = self.session_manager.get_company_info(user_id)

        if not accessible_sites or not user_info or not company_info:
            error_attachment = cards.error_card("Session data not found. Please fetch available sites first.")
            await turn_context.send_activity(MessageFactory.attachment(error_attachment))
            return

        target_site = next((site for site in accessible_sites if str(site.get("id")) == target_site_id), None)

        if not target_site:
            error_attachment = cards.error_card("Selected site not found")
            await turn_context.send_activity(MessageFactory.attachment(error_attachment))
            return

        source_user_id = str(user_info.get("id"))
        source_site_id = str(company_info.get("site_id"))
        login_key = target_site.get("login_key", "")

        switch_message = f"Switch to site {target_site.get('site_name')}"
        self.session_manager.add_to_history(user_id, "user", switch_message)

        conversation_history = self.session_manager.get_conversation_history(user_id)
        conversation_history.append({
            "role": "user",
            "content": f"Use the switch_site tool with target_site_id='{target_site_id}', source_user_id='{source_user_id}', source_site_id='{source_site_id}', login_key='{login_key}'"
        })

        await turn_context.send_activity(MessageFactory.text("Switching site..."))

        result = Runner.run_streamed(self.agent, input=conversation_history)

        async for event in result.stream_events():
            if event.type == "run_item_stream_event" and event.item.type == "tool_call_output_item":
                tool_output = event.item.output

                if isinstance(tool_output, str):
                    try:
                        tool_output = json.loads(tool_output)
                    except:
                        pass

                if isinstance(tool_output, dict) and tool_output.get("ok"):
                    updated_user_info = tool_output.get("user")
                    updated_company_info = tool_output.get("company")
                    self.session_manager.set_authenticated(user_id, True, updated_user_info, updated_company_info)

                    card_attachment = cards.create_company_info_card(tool_output)
                    await turn_context.send_activity(MessageFactory.attachment(card_attachment))
                else:
                    error_attachment = cards.error_card("Site switch failed")
                    await turn_context.send_activity(MessageFactory.attachment(error_attachment))

    def _convert_date_to_iso(self, date_str: str) -> str:
        """Convert date string to ISO format timestamp."""
        try:
            if "T" in date_str:
                return date_str

            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            return date_obj.strftime("%Y-%m-%d 00:00:00")
        except:
            return date_str

    async def on_members_added_activity(self, members_added: ChannelAccount, turn_context: TurnContext):
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                welcome_text = "Hello! I'm your OMG project management assistant. I can help you manage tasks, switch sites, and navigate the system. How can I help you today?"
                await turn_context.send_activity(MessageFactory.text(welcome_text))
