from typing import Optional, Dict, Any
from botbuilder.schema import Attachment
from config import settings
from utils import pick_base_url, absolutize_url, normalize_data

def _as_adaptive_attachment(card: Dict[str, Any]) -> Attachment:
    return Attachment(
        content_type="application/vnd.microsoft.card.adaptive",
        content=card,
    )

def create_login_card(userid: str, username: Optional[str] = None) -> Attachment:
    """Creates an adaptive card Attachment for user login."""
    
    card = {
        "type": "AdaptiveCard",
        "body": [
            {
                "type": "TextBlock",
                "text": "Please log in to continue",
                "weight": "Bolder",
                "size": "ExtraLarge"
            },
            {
                "type": "Input.Text",
                "id": "username",
                "placeholder": "Enter username",
                "label": "Username",
                **({"value": username} if username else {})
            },
            {
                "type": "Input.Text",
                "id": "password",
                "placeholder": "Enter password",
                "label": "Password",
                "isPassword": True
            }
        ],
        "actions": [
            {
                "type": "Action.Submit",
                "title": "Log In",
                "data": {
                    "action": "login",
                    "userid": userid
                }
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


def create_company_info_card(tool_result):
    data_container = normalize_data(tool_result)
    payload_company = (data_container.get("company") if isinstance(data_container, dict) else {}) or {}
    payload_user = (data_container.get("user") if isinstance(data_container, dict) else {}) or {}

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
    base = pick_base_url()
    site_url = payload_company.get("site_url")
    link = base.rstrip("/") if base else absolutize_url(site_url, None)

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

def create_switch_site_card(tool_result: list, user_id: str, source_site_id: str) -> Attachment:
    """Creates an adaptive card for switching sites."""
    sites = tool_result

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
                    "user_id": user_id,
                    "source_site_id": source_site_id
                }
            }
        ],
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.5"
    }

    return _as_adaptive_attachment(card)