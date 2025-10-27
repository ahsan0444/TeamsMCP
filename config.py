import os
from typing import Optional, Dict, Any
from pydantic_settings import BaseSettings
from pydantic import Field, validator


class Settings(BaseSettings):
    mcp_server_url: str = Field(default="http://localhost:5001/mcp", env="MCP_SERVER_URL")
    base_url: str = Field(default="http://britvic.omg.sbox.oliver.solutions", env="BASE_URL")
    login_base_url: str = Field(default="http://britvic.omg.sbox.oliver.solutions", env="LOGIN_BASE_URL")
    bot_port: int = Field(default=8000, env="BOT_PORT")

    microsoft_app_id: str = Field(..., env="MICROSOFT_APP_ID")
    microsoft_app_password: str = Field(..., env="MICROSOFT_APP_PASSWORD")
    microsoft_app_tenant_id: str = Field(..., env="MICROSOFT_APP_TENANT_ID")

    openai_api_key: str = Field(..., env="OPENAI_API_KEY")

    app_base_url: Optional[str] = Field(None, env="APP_BASE_URL")

    project_id: str = "7334"
    default_plan_type: str = "9000"

    TOOL_CONFIG: Dict[str, Dict[str, Any]] = {
        "login": {
            "requires_card": True,
            "card_factory": "create_login_card",
            "result_card_factory": "create_company_info_card"
        },
        "get_user_and_company_info": {
            "requires_card": False,
            "card_factory": None,
            "result_card_factory": "create_company_info_card"
        },
        "get_available_sites": {
            "requires_card": False,
            "card_factory": None,
            "result_card_factory": "create_switch_site_card"
        },
        "switch_site": {
            "requires_card": False,
            "card_factory": None,
            "result_card_factory": "create_company_info_card"
        },
        "create_task": {
            "requires_card": True,
            "card_factory": "create_task_creation_card",
            "result_card_factory": "create_task_result_card"
        },
        "logout": {
            "requires_card": False,
            "card_factory": None,
            "result_card_factory": None
        }
    }

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
