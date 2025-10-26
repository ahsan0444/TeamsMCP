from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import Dict, Any

class Settings(BaseSettings):
    microsoft_app_id: str = ""
    microsoft_app_password: str = ""
    mcp_server_url: str = "http://localhost:5001/mcp"
    login_base_url: str = ""
    bot_port: int = 8000

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4-turbo"

    # Per-tool configuration: card factory name (in cards.py), wrapper param name,
    # required fields for validation, and default values.
    # Add new tools here — no bot code changes needed.
    TOOL_CONFIG: Dict[str, Any] = {
        "login": {
            "display_name": "Login",
            "card_factory": "create_login_card",
            "param_wrapper": None,
            "required_fields": ["username", "password"],
            "defaults": {},
            "auto_create_session": True,
            "requires_login": False,
            "triggers": ["login", "login to mcp", "signin", "sign in"],
            "purpose": "To log in to the MCP system. Use this tool if the user wants to authenticate."
        },
        "create_task": {
            "display_name": "Create Task",
            "card_factory": "create_task_creation_card",
            "param_wrapper": "task_payload",
            "required_fields": ["planningParentId", "plan_type", "start_date", "end_date", "text"],
            "defaults": {
                "planningParentId": str(7334),
                "plan_type": "9000"
            },
            "auto_create_session": False,
            "requires_login": True
        },
        "get_user_and_company_info": {
            "display_name": "Get User and Company Info",
            "card_factory": None,
            "param_wrapper": None,
            "required_fields": [],
            "result_card_factory": "create_company_info_card",
            "requires_login": True
        },
        "get_available_sites": {
            "display_name": "Get Available Sites",
            "card_factory": None, # No input card, directly called
            "param_wrapper": None,
            "required_fields": [],
            "result_card_factory": "create_switch_site_card", # Shows a card with the list of sites
            "requires_login": True
        },
        "switch_site": {
            "display_name": "Switch Site",
            "card_factory": "create_switch_site_card", # This card is shown by get_available_sites
            "param_wrapper": None,
            "required_fields": ["target_site_id"],
            "result_card_factory": "create_company_info_card", # Show updated info on success
            "requires_login": True
        }
    }

    # Backwards-compatible maps (optional)
    tool_card_map: Dict[str, str] = {"create_task": "create_task_creation_card"}
    tool_param_wrapper: Dict[str, str] = {"create_task": "task_payload"}

    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="allow",
    )

settings = Settings()

