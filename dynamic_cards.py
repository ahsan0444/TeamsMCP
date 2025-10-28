from typing import Dict, Any, List, Optional
from botbuilder.schema import Attachment
import json


def _as_adaptive_attachment(card: Dict[str, Any]) -> Attachment:
    return Attachment(
        content_type="application/vnd.microsoft.card.adaptive",
        content=card,
    )


def create_dynamic_result_card(
    tool_name: str,
    tool_result: Any,
    success_indicator: Optional[str] = "ok"
) -> Attachment:
    """
    Creates a dynamic adaptive card based on tool result structure.
    Automatically formats data in a presentable way.

    Args:
        tool_name: Name of the tool that was called
        tool_result: The result returned from the tool
        success_indicator: Key to check for success (default: "ok")
    """

    # Parse if string
    if isinstance(tool_result, str):
        try:
            tool_result = json.loads(tool_result)
        except:
            pass

    # Determine success
    is_success = True
    if isinstance(tool_result, dict):
        is_success = tool_result.get(success_indicator, True)

    # Build card
    card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.5",
        "body": []
    }

    # Title
    title_text = f"{'✅' if is_success else '❌'} {_format_tool_name(tool_name)}"
    card["body"].append({
        "type": "TextBlock",
        "text": title_text,
        "weight": "Bolder",
        "size": "Large",
        "color": "Good" if is_success else "Attention"
    })

    # Extract and display data
    if isinstance(tool_result, dict):
        # Handle nested response structures
        display_data = _extract_display_data(tool_result)

        if display_data:
            # Create sections for different data types
            for section_title, section_data in display_data.items():
                card["body"].append(_create_data_section(section_title, section_data))

        # Add action buttons if URLs are present
        actions = _extract_action_buttons(tool_result)
        if actions:
            card["actions"] = actions

    elif isinstance(tool_result, list):
        # Handle list results
        card["body"].append(_create_list_section("Results", tool_result))

    else:
        # Simple text result
        card["body"].append({
            "type": "TextBlock",
            "text": str(tool_result),
            "wrap": True
        })

    return _as_adaptive_attachment(card)


def _format_tool_name(tool_name: str) -> str:
    """Convert tool_name to Title Case with spaces."""
    return tool_name.replace('_', ' ').title()


def _extract_display_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract meaningful data from nested structures.
    Returns a dict of section_name: section_data
    """
    result = {}

    # Common patterns
    if 'response' in data and isinstance(data['response'], dict):
        data = data['response']

    if 'data' in data and isinstance(data['data'], dict):
        data = data['data']

    # Look for nested data
    if 'data' in data and isinstance(data['data'], dict):
        inner_data = data['data']

        # User information
        if 'user' in inner_data:
            result['User Information'] = inner_data['user']

        # Company information
        if 'company' in inner_data:
            result['Company Information'] = inner_data['company']

        # Task/item data
        if isinstance(inner_data, dict) and any(k in inner_data for k in ['text', 'title', 'id', 'type']):
            result['Details'] = inner_data

    # Direct data
    elif isinstance(data, dict):
        # User info
        if 'user' in data:
            result['User Information'] = data['user']

        # Company info
        if 'company' in data:
            result['Company Information'] = data['company']

        # Sites list
        if 'sites' in data and isinstance(data['sites'], list):
            result['Available Sites'] = data['sites']

        # Generic data
        if not result:
            # Filter out meta keys
            meta_keys = {'ok', 'status_code', 'message', 'success', 'error'}
            filtered = {k: v for k, v in data.items() if k not in meta_keys and v is not None}
            if filtered:
                result['Information'] = filtered

    return result


def _create_data_section(title: str, data: Any) -> Dict[str, Any]:
    """Create a card section for displaying data."""

    section = {
        "type": "Container",
        "items": [],
        "separator": True
    }

    # Section title
    section["items"].append({
        "type": "TextBlock",
        "text": title,
        "weight": "Bolder",
        "size": "Medium"
    })

    if isinstance(data, dict):
        # Create FactSet for key-value pairs
        facts = []
        for key, value in data.items():
            if value is not None and not isinstance(value, (dict, list)):
                formatted_key = key.replace('_', ' ').title()
                facts.append({
                    "title": formatted_key,
                    "value": str(value)
                })

        if facts:
            section["items"].append({
                "type": "FactSet",
                "facts": facts
            })

    elif isinstance(data, list):
        # Display list items
        for item in data[:5]:  # Limit to 5 items
            if isinstance(item, dict):
                item_text = item.get('name') or item.get('title') or item.get('text') or str(item)
            else:
                item_text = str(item)

            section["items"].append({
                "type": "TextBlock",
                "text": f"• {item_text}",
                "wrap": True
            })

        if len(data) > 5:
            section["items"].append({
                "type": "TextBlock",
                "text": f"_...and {len(data) - 5} more_",
                "isSubtle": True
            })

    else:
        section["items"].append({
            "type": "TextBlock",
            "text": str(data),
            "wrap": True
        })

    return section


def _create_list_section(title: str, items: List[Any]) -> Dict[str, Any]:
    """Create a section for list data."""
    return _create_data_section(title, items)


def _extract_action_buttons(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract and create action buttons from data."""
    actions = []

    # Look for URL fields
    url_fields = ['url', 'item_url', 'link', 'site_url']

    def find_urls(d: Any, base_url: str = "") -> None:
        if isinstance(d, dict):
            for key, value in d.items():
                if key in url_fields and value:
                    url = str(value)
                    if url.startswith('/') and base_url:
                        url = base_url.rstrip('/') + url

                    actions.append({
                        "type": "Action.OpenUrl",
                        "title": f"Open {key.replace('_', ' ').title()} 🔗",
                        "url": url
                    })
                elif isinstance(value, dict):
                    find_urls(value, base_url)

    # Try to find base URL
    base_url = ""
    if 'base_url' in data:
        base_url = data['base_url']
    elif 'company' in data and isinstance(data['company'], dict):
        base_url = data['company'].get('site_url', '')

    find_urls(data, base_url)

    return actions[:3]  # Limit to 3 actions


def should_use_dynamic_card(tool_name: str) -> bool:
    """
    Determine if a tool should use dynamic card generation.
    Return False for tools that have specialized cards.
    """
    specialized_cards = {
        'login',  # Has custom login form
        'create_task_creation_card'  # Has custom task form
    }

    return tool_name not in specialized_cards