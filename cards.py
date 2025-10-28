from typing import Optional, Dict, Any, Union
from botbuilder.schema import Attachment
from config import settings
from urllib.parse import urljoin
import json

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def _as_adaptive_attachment(card: Dict[str, Any]) -> Attachment:
    return Attachment(
        content_type="application/vnd.microsoft.card.adaptive",
        content=card,
    )

def create_login_card(userid: str, username: Optional[str] = None) -> Attachment:
    """Creates a secure adaptive card for user login."""

    card = {
        "type": "AdaptiveCard",
        "body": [
            {
                "type": "Container",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "🔐 Secure Login",
                        "weight": "Bolder",
                        "size": "ExtraLarge",
                        "horizontalAlignment": "Center"
                    },
                    {
                        "type": "TextBlock",
                        "text": "Your credentials are encrypted and never stored in chat history",
                        "size": "Small",
                        "color": "Accent",
                        "horizontalAlignment": "Center",
                        "wrap": True
                    }
                ],
                "style": "emphasis"
            },
            {
                "type": "Container",
                "items": [
                    {
                        "type": "Input.Text",
                        "id": "username",
                        "label": "Username",
                        "placeholder": "Enter your username",
                        "isRequired": True,
                        "errorMessage": "Username is required",
                        **({"value": username} if username else {})
                    },
                    {
                        "type": "Input.Text",
                        "id": "password",
                        "label": "Password",
                        "placeholder": "Enter your password",
                        "style": "Password",  # This makes it a password field
                        "isRequired": True,
                        "errorMessage": "Password is required"
                    }
                ],
                "spacing": "Medium"
            },
            {
                "type": "TextBlock",
                "text": "⚠️ Never share your password with anyone. Our team will never ask for it in chat.",
                "size": "Small",
                "color": "Warning",
                "wrap": True,
                "spacing": "Medium"
            }
        ],
        "actions": [
            {
                "type": "Action.Submit",
                "title": "🔓 Login Securely",
                "data": {
                    "action": "login",
                    "userid": userid
                },
                "style": "positive"
            }
        ],
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.5"
    }

    return _as_adaptive_attachment(card)

def create_task_creation_card(prefill: Optional[Dict[str, Any]] = None) -> Attachment:
    """Creates an adaptive card Attachment for task creation with date inputs (Input.Date).
    If prefill is provided, populate fields with given values; otherwise show defaults.
    """
    import datetime as _dt

    def _to_date_value(val: Optional[str]) -> Optional[str]:
        if not val:
            return None
        s = str(val).strip().lower()
        today = _dt.date.today()
        if s in {"today"}:
            return today.isoformat()
        if s in {"tomorrow"}:
            return (today + _dt.timedelta(days=1)).isoformat()
        if s in {"day after tomorrow"}:
            return (today + _dt.timedelta(days=2)).isoformat()
        if "two days" in s and "from now" in s:
            return (today + _dt.timedelta(days=2)).isoformat()
        # If ISO datetime provided, trim to YYYY-MM-DD
        if "T" in s and "-" in s:
            try:
                return s.split("T", 1)[0]
            except Exception:
                pass
        # If looks like YYYY-MM-DD, accept
        if len(s) == 10 and s.count("-") == 2:
            return s
        return None

    p = prefill or {}
    planning_parent_val = str(p.get("planningParentId") or getattr(settings, "project_id", "7334"))
    plan_type_val = str(p.get("plan_type") or getattr(settings, "default_plan_type", "9000"))
    title_val = p.get("text") or p.get("title") or ""
    description_val = p.get("description") or ""
    start_val = _to_date_value(p.get("start_date") or p.get("start"))
    end_val = _to_date_value(p.get("end_date") or p.get("end"))

    start_example = "2025-10-20"
    end_example = "2025-10-21"

    card = {
        "type": "AdaptiveCard",
        "body": [
            {"type": "TextBlock", "text": "Create Task", "weight": "Bolder", "size": "Large"},

            # planningParentId (project id) - prefilled from settings or prefill
            {
                "type": "Input.Text",
                "id": "planningParentId",
                "title": "Project (planningParentId)",
                "placeholder": "planningParentId (project id)",
                "value": planning_parent_val,
                "label": "Project ID"
            },

            # Plan type dropdown (3000/6000/9000)
            {
                "type": "Input.ChoiceSet",
                "id": "plan_type",
                "label": "Plan type",
                "style": "compact",
                "choices": [
                    {"title": "Task", "value": "3000"},
                    {"title": "Milestone", "value": "6000"},
                    {"title": "Subtask", "value": "9000"}
                ],
                "value": plan_type_val
            },

            {"type": "Input.Text", "id": "text", "placeholder": "Task title", "label": "Title", **({"value": title_val} if title_val else {})},
            {"type": "Input.Text", "id": "description", "placeholder": "Optional description", "isMultiline": True, "label": "Description", **({"value": description_val} if description_val else {})},

            # Date inputs (type=date) - backend will convert to required ISO timestamps
            {
                "type": "Input.Date",
                "id": "start_date",
                "label": "Start date (YYYY-MM-DD)",
                "placeholder": start_example,
                **({"value": start_val} if start_val else {})
            },
            {
                "type": "Input.Date",
                "id": "end_date",
                "label": "End date (YYYY-MM-DD)",
                "placeholder": end_example,
                **({"value": end_val} if end_val else {})
            },

            {
                "type": "Input.ChoiceSet",
                "id": "priority",
                "label": "Priority (informational)",
                "style": "compact",
                "choices": [
                    {"title": "Low", "value": "low"},
                    {"title": "Medium", "value": "medium"},
                    {"title": "High", "value": "high"},
                ],
                "value": "medium"
            }
        ],
        "actions": [
            {"type": "Action.Submit", "title": "Create", "data": {"action": "create_task"}}
        ],
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.5"
    }
    return _as_adaptive_attachment(card)

def success_card(message: str) -> Attachment:
    card = {
        "type": "AdaptiveCard",
        "body": [
            {"type": "TextBlock", "text": message, "weight": "Bolder", "color": "Good"}
        ],
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.5"
    }
    return _as_adaptive_attachment(card)

def error_card(message: str) -> Attachment:
    card = {
        "type": "AdaptiveCard",
        "body": [
            {"type": "TextBlock", "text": message, "weight": "Bolder", "color": "Attention"}
        ],
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.5"
    }
    return _as_adaptive_attachment(card)


def _normalize_data_inline(data: Any) -> Union[dict, list, str, None]:
    """
    Recursively normalize inline tool data into a clean, consistent structure.
    - Unwraps single-item lists
    - Parses JSON strings when possible
    - Unwraps single-key dicts
    - Handles deeply nested combinations
    - Returns primitives as-is
    """

    # 1️⃣ Handle single-item lists
    if isinstance(data, list):
        if len(data) == 1:
            return _normalize_data_inline(data[0])
        return [_normalize_data_inline(item) for item in data]

    # 2️⃣ Handle JSON strings
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
            return _normalize_data_inline(parsed)
        except (json.JSONDecodeError, TypeError):
            return data  # Not valid JSON, return as-is

    # 3️⃣ Handle dicts
    if isinstance(data, dict):
        # If dict has a single key, unwrap its value recursively
        if len(data) == 1:
            inner_val = next(iter(data.values()))
            return _normalize_data_inline(inner_val)

        # Otherwise, normalize all nested values
        return {k: _normalize_data_inline(v) for k, v in data.items()}

    # 4️⃣ Return all other types as-is (int, float, None, etc.)
    return data

def create_company_info_card(tool_result):
    data_container = _normalize_data_inline(tool_result)
    if isinstance(data_container, dict):
        # If real data is under "text", unwrap it
        payload = (
            data_container.get("text")
            if isinstance(data_container.get("text"), dict)
            else data_container
        )
    else:
        payload = data_container
            
    payload_company = (payload.get("company") if isinstance(payload, dict) else {}) or {}
    payload_user = (payload.get("user") if isinstance(payload, dict) else {}) or {}

    company_card = {
        "type": "AdaptiveCard",
        "body": [
            {
                "type": "TextBlock",
                "text": "Company Information",
                "weight": "Bolder",
                "size": "Large"
            }
        ],
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.5"
    }

    # Company details
    if payload_company:
        company_section = {
            "type": "Container",
            "items": [
                {
                    "type": "FactSet",
                    "facts": [
                        {"title": "Site Name", "value": payload_company.get("site_name", "Unknown")},
                        {"title": "Site URL", "value": payload_company.get("site_url", "Unknown")},
                        {"title": "Site ID", "value": str(payload_company.get("site_id", "Unknown"))}
                    ]
                }
            ]
        }
        company_card["body"].append(company_section)

    # User details
    if payload_user:
        user_section = {
            "type": "Container",
            "items": [
                {
                    "type": "TextBlock",
                    "text": "User Information",
                    "weight": "Bolder"
                },
                {
                    "type": "FactSet",
                    "facts": [
                        {"title": "Name", "value": payload_user.get("name", "Unknown")},
                        {"title": "ID", "value": str(payload_user.get("id", "Unknown"))},
                        {"title": "Email", "value": payload_user.get("email") or "Unknown"}
                    ]
                }
            ],
            "separator": True
        }
        company_card["body"].append(user_section)

    # Open Site link
    base = settings.login_base_url or settings.mcp_server_url
    site_url = payload_company.get("site_url")
    link = None
    if site_url:
        if not site_url.startswith(("http://", "https://")):
            #  if base:
            #     link = urljoin(base, site_url)
            #  else:
            link = site_url # cannot absolutize
        else:
            link = site_url
    elif base:
        link = base.rstrip("/")

    if link:
        company_card.setdefault("actions", []).append({
            "type": "Action.OpenUrl",
            "title": "Open site 🔗",
            "url": link
        })

    return Attachment(
        content_type="application/vnd.microsoft.card.adaptive",
        content=company_card
    )

def create_switch_site_card(tool_result):
    """Creates an adaptive card for switching sites."""
    
    data_container = _normalize_data_inline(tool_result)
    if isinstance(data_container, dict):
        # If real data is under "text", unwrap it
        payload = (
            data_container.get("text")
            if isinstance(data_container.get("text"), dict)
            else data_container
        )
    else:
        payload = data_container
    
    sites = payload.get("sites", [])
    
    if not sites:
        card = {
            "type": "AdaptiveCard",
            "body": [
                {
                    "type": "TextBlock",
                    "text": "Switch Site",
                    "weight": "Bolder",
                    "size": "Large"
                },
                {
                    "type": "TextBlock",
                    "text": "No other sites available to switch to.",
                    "wrap": True
                }
            ],
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.5"
        }
        return _as_adaptive_attachment(card)
    
    # Generate choices for the dropdown
    choices = [
        {
            "title": f"{site.get('site_name', 'Unknown Site')} ({site.get('site_customer_name', 'Unknown Customer')})",
            "value": str(site.get('id'))
        }
        for site in sites
    ]

    card = {
        "type": "AdaptiveCard",
        "body": [
            {
                "type": "TextBlock",
                "text": "Switch to another site",
                "weight": "Bolder",
                "size": "Large"
            },
            {
                "type": "TextBlock",
                "text": "Select a site from the list below to switch your active session.",
                "wrap": True
            },
            {
                "type": "Input.ChoiceSet",
                "id": "target_site_id",
                "label": "Available Sites",
                "choices": choices,
                "placeholder": "Select a site",
                "value": choices[0]["value"] if choices else None
            }
        ],
        "actions": [
            {
                "type": "Action.Submit",
                "title": "Switch",
                "data": {
                    "action": "switch_site",
                }
            }
        ],
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.5"
    }

    return _as_adaptive_attachment(card)

def create_task_result_card(tool_result, company_info=None):
    """Create a card showing task creation results with proper URLs."""
    
    # Extract base_url from company_info if provided, otherwise use fallback
    if company_info and company_info.get('site_url'):
        base_url = company_info['site_url']
    else:
        base_url = settings.login_base_url or 'http://britvic.omg.sbox.oliver.solutions'
    
    # Use the same normalization approach as create_company_info_card
    data_container = _normalize_data_inline(tool_result)
    
    if isinstance(data_container, dict):
        # If real data is under "text", unwrap it
        payload = (
            data_container.get("text")
            if isinstance(data_container.get("text"), dict)
            else data_container
        )
    else:
        payload = data_container

    # Extract data using the normalized payload
    # response_data = payload.get('response', {})
    inner_data = payload.get('response', {})

    # FIXED: Handle both error: 0 and error: None as success
    error_value = inner_data.get('error')
    success_value = inner_data.get('success')

    # Success if error is 0 or None, and success is 0
    is_success = (
        tool_result.get('ok') == True and 
        tool_result.get('status_code') == 200
    ) or (
        error_value == 0 and 
        success_value == 1
    )
    
    task_data = inner_data.get('data', {})

    # Also check if tool_result itself indicates success
    if not is_success and task_data and task_data.get('id'):
        is_success = True

    if is_success and task_data:
        # Success card logic (existing code)
        item_url = task_data.get('item_url', '')
        full_url = f"{base_url.rstrip('/')}{item_url}" if item_url.startswith('/') else item_url

        # Determine the type display name
        type_display = task_data.get('type', 'Task')
        plan_type = task_data.get('plan_type') or task_data.get('planning_type')
        if plan_type == 6000 or plan_type == '6000':
            type_display = 'Milestone'
        elif plan_type == 9000 or plan_type == '9000':
            type_display = 'Subtask'

        card = {
            "type": "AdaptiveCard",
            "body": [
                {
                    "type": "TextBlock",
                    "text": f"✅ {type_display} Created Successfully",
                    "weight": "Bolder",
                    "size": "Large",
                    "color": "Good"
                },
                {
                    "type": "FactSet",
                    "facts": [
                        {"title": "ID", "value": str(task_data.get('id', 'N/A'))},
                        {"title": "Title", "value": task_data.get('text', 'N/A')},
                        {"title": "Type", "value": type_display},
                        {"title": "Planning Number", "value": str(task_data.get('planning_number', 'N/A'))},
                        {"title": "Created By", "value": task_data.get('created_by_name', 'N/A')},
                        {"title": "Start Date", "value": task_data.get('start_date', 'N/A')},
                        {"title": "End Date", "value": task_data.get('end_date', 'N/A')}
                    ]
                }
            ],
            "actions": [
                {
                    "type": "Action.OpenUrl",
                    "title": f"View {type_display} 🔗",
                    "url": full_url
                }
            ],
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.5"
        }
    else:
        # Error handling (existing logic)
        error_message = "Unknown error"
        if error_value and error_value != 0:
            error_message = f"API error: {error_value}"
        elif not tool_result.get('ok'):
            error_message = tool_result.get('message', 'Operation failed')

        # Add more debug info
        card = {
            "type": "AdaptiveCard",
            "body": [
                {
                    "type": "TextBlock",
                    "text": "❌ Task Creation Failed",
                    "weight": "Bolder",
                    "size": "Large",
                    "color": "Attention"
                },
                {
                    "type": "TextBlock",
                    "text": f"Error: {error_message}",
                    "wrap": True
                }
            ],
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.5"
        }

    return _as_adaptive_attachment(card)