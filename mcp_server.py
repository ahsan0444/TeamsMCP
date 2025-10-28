from fastmcp import FastMCP
import requests
from typing import Optional, Dict, Any
import logging
import os
import warnings

import hmac
import hashlib

warnings.filterwarnings("ignore", message="Unverified HTTPS request")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("mcp").setLevel(logging.WARNING)

SESSION_STORE: Dict[str, Any] = {"session": None, "base_url": None}

SWITCH_LOGIN_KEY = "OliverV8Rising!"  # must match the Perl $hash_key

def generate_switch_login_key(target_site_id: str, source_user_id: str) -> str:
    """
    Generates a login key identical to Perl's:
    hmac_md5_hex($target_site_id.$source_user_id, $hash_key)
    """
    message = f"{target_site_id}{source_user_id}".encode("utf-8")
    secret = SWITCH_LOGIN_KEY.encode("utf-8")
    return hmac.new(secret, message, hashlib.md5).hexdigest()

mcp = FastMCP("omg-mcp")

@mcp.prompt()
def system_prompt() -> str:
    """Instructions for OMG project management agent"""
    script_dir = os.path.dirname(__file__)
    prompt_path = os.path.join(script_dir, "prompts", "system_instructions.md")
    try:
        with open(prompt_path, "r") as file:
            return file.read()
    except FileNotFoundError:
        logger.error(f"System instructions file not found at: {prompt_path}")
        return "You are an OMG project management assistant. Help users manage tasks and navigate the system." 

# Helper used by tools to fetch user/company info without calling a decorated tool directly

def _fetch_user_and_company_info(session, base_url: str) -> Dict[str, Any]:
    info_url = f"{base_url}/getUserAndCompanyInfo"
    try:
        if not session or not base_url:
            return {"ok": False, "message": "No authenticated session. Run the login tool first."}

        headers = {
            "x-requested-with": "XMLHttpRequest",
            "Content-Type": "application/json"
        }

        logging.info("Fetching user and company info from %s", info_url)

        resp = session.get(info_url, headers=headers, verify=False)

        logging.info("Response text: %s", resp.text)
        resp.raise_for_status()

        if not resp.text:
            return {"ok": False, "message": "Empty response received from server"}

        raw = resp.json()
        payload = raw.get("data", raw) if isinstance(raw, dict) else {}
        ok_flag = bool(payload.get("ok", True)) if isinstance(payload, dict) else True
        user = payload.get("user", {}) if isinstance(payload, dict) else {}
        company = payload.get("company", {}) if isinstance(payload, dict) else {}

        return {
            "ok": ok_flag,
            "status_code": resp.status_code,
            "user": user,
            "company": company,
        }

    except requests.exceptions.JSONDecodeError as e:
        return {"ok": False, "message": f"Invalid JSON response from server: {str(e)} (Response text: {resp.text})"}
    except requests.exceptions.RequestException as e:
        return {"ok": False, "message": f"Request failed: {str(e)}"}
    except Exception as e:
        return {"ok": False, "message": f"Failed to fetch info: {str(e)}"}


@mcp.tool(description="Authenticates the user and stores session, user, and company info in memory.")
def login(
    username: str,
    password: str,
    base_url: str = "http://britvic.omg.sbox.oliver.solutions",
    utcOffset: str = "+5",
    localeCode: str = "en-GB",
    timezone: str = "Asia/Karachi",
    timezoneName: Optional[str] = None
) -> Dict[str, Any]:
    """
    Authenticates the user and stores session, user, and company info in memory.
    """
    timezoneName = timezoneName or timezone
    session = requests.Session()
    login_url = f"{base_url}/login"

    payload = {
        "username": username,
        "password": password,
        "utcOffset": utcOffset,
        "localeCode": localeCode,
        "timezone": timezone,
        "timezoneName": timezoneName
    }

    resp = session.post(login_url, data=payload, allow_redirects=True, verify=False)

    # Save session and base URL
    SESSION_STORE["session"] = session
    SESSION_STORE["base_url"] = base_url

    # Fetch and store user/company info via helper (do NOT call a decorated tool here)
    user_company_info = _fetch_user_and_company_info(session, base_url)
    
    if user_company_info.get("ok"):
        SESSION_STORE["user"] = user_company_info.get("user")
        SESSION_STORE["company"] = user_company_info.get("company")
        return {
            "ok": True,
            "login_status": resp.status_code,
            "session_cookie": session.cookies.get("session_id"),
            # "session": session,
            "user": SESSION_STORE.get("user"),
            "company": SESSION_STORE.get("company")
        }

    return {
        "ok": True,
        "login_status": resp.status_code,
        "session_cookie": session.cookies.get("session_id"),
        # "session": session,
        "message": "Login succeeded, but user/company info could not be fetched.",
        "user_company_info": user_company_info
    }


@mcp.tool(description="Creates a new task using the stored authenticated session.")
def create_task(
    task_payload: Dict[str, Any],
    create_url: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Creates a new task using the stored authenticated session.
    """
    session = SESSION_STORE.get("session")
    base_url = SESSION_STORE.get("base_url")

    if not session or not base_url:
        return {"ok": False, "message": "No authenticated session. Run the login tool first."}

    create_url = create_url or f"{base_url}/_createGanttTask"
    headers = headers or {
        "x-requested-with": "XMLHttpRequest",
        "Content-Type": "application/json"
    }

    try:
        resp = session.post(create_url, headers=headers, json=task_payload, verify=False)
        content_type = resp.headers.get("Content-Type", "")

        try:
            data = resp.json() if "application/json" in content_type else resp.text
        except Exception:
            data = resp.text

        # Determine success from response
        is_success = resp.status_code in (200, 201, 202)

        # If data is dict, check for success indicators
        if isinstance(data, dict):
            inner = data.get('data', {})
            if isinstance(inner, dict):
                # Check if backend indicates success
                if inner.get('success') == 0 and (inner.get('error') == 0 or inner.get('error') is None):
                    is_success = True

        return {
            "ok": is_success,
            "status_code": resp.status_code,
            "response": data
        }
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        return {
            "ok": False,
            "status_code": 500,
            "message": f"Failed to create task: {str(e)}"
        }

@mcp.tool(description="Fetches the logged-in user's and company's information from destination edpoint and stores it in memory.")
def get_user_and_company_info() -> Dict[str, Any]:
    """
    Fetches the logged-in user's and company's information from the backend.
    """
    session = SESSION_STORE.get("session")
    base_url = SESSION_STORE.get("base_url")

    logger.info("Fetching user and company info from %s", base_url)
    
    if not session or not base_url:
        return {"ok": False, "message": "No authenticated session. Run the login tool first."}

    result = _fetch_user_and_company_info(session, base_url)
    
    if result.get("ok"):
        SESSION_STORE["user_info"] = result.get("user")
        SESSION_STORE["company_info"] = result.get("company")
    return result


@mcp.tool(description="Fetches a list of available sites that the current user can switch to.")
def get_available_sites() -> Dict[str, Any]:
    """
    Fetches a list of available sites that the current user can switch to.
    Requires an active session.
    """
    session = SESSION_STORE.get("session")
    base_url = SESSION_STORE.get("base_url")

    if not session or not base_url:
        return {"ok": False, "message": "No authenticated session. Run the login tool first."}

    sites_url = f"{base_url}/getUserAccessibleSites"
    headers = {"x-requested-with": "XMLHttpRequest"}

    try:
        resp = session.get(sites_url, headers=headers, verify=False)
        resp.raise_for_status()
        
        if not resp.text:
            return {"ok": False, "message": "Empty response from server when fetching sites."}

        raw = resp.json()
        payload = raw.get("data", raw)
        
        if not payload or "accessible_sites" not in payload:
            return {"ok": False, "message": "No sites available or unexpected response format."}
        
        SESSION_STORE["accessible_sites"] = payload["accessible_sites"]

        return {
            "ok": True,
            "sites": payload["accessible_sites"],
        }

    except requests.exceptions.RequestException as e:
        return {"ok": False, "message": f"Request to fetch sites failed: {e}"}
    except Exception as e:
        return {"ok": False, "message": f"An unexpected error occurred: {e}"}


@mcp.tool(description="Switches the user's active session to a different site.")
def switch_site(
    target_site_id: str,
    source_user_id: str,
    source_site_id: str,
    utc_offset: str = "-300",
    locale_code: str = "en-US",
    timezone: str = "Asia/Karachi",
    timezone_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Switches the user's active session to a different site using the provided parameters.
    A successful switch will automatically refetch and update the user and company info.
    """
    session = SESSION_STORE.get("session")
    base_url = SESSION_STORE.get("base_url")

    if not session or not base_url:
        return {"ok": False, "message": "No authenticated session. Run the login tool first."}

    # Generate login key using helper function
    login_key = generate_switch_login_key(target_site_id, source_user_id)

    switch_url = f"{base_url}/switch"

    payload = {
        "tsid": target_site_id,
        "suid": source_user_id,
        "ssid": source_site_id,
        "lk": login_key,
        "offset": utc_offset,
        "code": locale_code,
        "tz": timezone,
        "tzn": timezone_name or timezone,
    }

    try:
        resp = session.get(switch_url, params=payload, allow_redirects=True, verify=False)
        resp.raise_for_status()

        if resp.status_code == 200:
            updated_info = _refetch_and_store_user_data(session, base_url)
            if updated_info.get("ok"):
                return {
                    "ok": True,
                    "message": "Site switch successful. Your session has been updated.",
                    "user": updated_info.get("user"),
                    "company": updated_info.get("company"),
                }
            else:
                return {
                    "ok": False,
                    "message": "Site switch may have succeeded, but failed to refetch user data.",
                    "details": updated_info.get("message"),
                }

        return {
            "ok": False,
            "status_code": resp.status_code,
            "message": "Site switch failed with an unexpected status code.",
        }

    except requests.exceptions.RequestException as e:
        return {"ok": False, "message": f"Site switch request failed: {e}"}
    except Exception as e:
        return {"ok": False, "message": f"An unexpected error occurred during site switch: {e}"}

def _refetch_and_store_user_data(session: requests.Session, base_url: str) -> Dict[str, Any]:
    """
    Helper to refetch and update user and company info in the session store.
    """
    user_company_info = _fetch_user_and_company_info(session, base_url)
    if user_company_info.get("ok"):
        SESSION_STORE["user"] = user_company_info.get("user")
        SESSION_STORE["company"] = user_company_info.get("company")
    return user_company_info



@mcp.tool(description="Logs out the current user, calls backend /logout if available, and clears the stored session and user/company info.")
def logout() -> Dict[str, Any]:
    """
    Logs out the current user, calls backend /logout if available,
    and clears the stored session and user/company info.
    """
    session = SESSION_STORE.get("session")
    base_url = SESSION_STORE.get("base_url")

    if not session or not base_url:
        _clear_session()
        return {"ok": True, "message": "No active session found. Already logged out."}

    logout_url = f"{base_url}/logout"
    try:
        resp = session.get(logout_url, allow_redirects=True, verify=False)
    except Exception as e:
        resp = None

    _clear_session()

    return {
        "ok": True,
        "status_code": getattr(resp, "status_code", None),
        "message": "Successfully logged out and cleared session."
    }


def _clear_session():
    """Helper to clear all stored session data."""
    SESSION_STORE.clear()
    SESSION_STORE.update({"session": None, "base_url": None})


if __name__ == "__main__":
    mcp.run(transport="stdio")
