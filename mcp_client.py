import logging
import json
import asyncio
from typing import Any, Dict, Optional, List

from fastmcp import Client
from fastmcp.client.elicitation import ElicitResult
from session_manager import session_manager

logger = logging.getLogger(__name__)


class MCPClientManager:
    """
    Manages a fastmcp.Client using its async context manager API and supports elicitation.
    """

    def __init__(self, mcp_url: str, elicitation_timeout: int = 300):
        self.mcp_url = mcp_url
        self._client_cm: Optional[Client] = None
        self._client: Optional[Any] = None
        self.is_connected = False
        self.elicitation_timeout = elicitation_timeout
        # active user id to bind elicitation and context
        self._active_user_id: Optional[str] = None

    def set_active_user(self, user_id: str) -> None:
        """Record the active user id for context-aware operations."""
        self._active_user_id = user_id
        try:
            session_manager.set_active_user(user_id)
        except Exception:
            pass

    async def connect(self) -> None:
        if self.is_connected:
            return

        # pass our elicitation handler into the Client so the server can ask the user for structured input
        self._client_cm = Client(self.mcp_url, elicitation_handler=self._elicitation_handler)
        try:
            self._client = await self._client_cm.__aenter__()
            self.is_connected = True
            logger.info("MCP client connected to %s", self.mcp_url)
        except Exception:
            try:
                if self._client_cm is not None:
                    await self._client_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._client_cm = None
            self._client = None
            self.is_connected = False
            logger.exception("Failed to connect MCP client")
            raise

    async def disconnect(self) -> None:
        if not self.is_connected:
            return

        try:
            if self._client_cm is not None:
                await self._client_cm.__aexit__(None, None, None)
                logger.info("MCP client disconnected from %s", self.mcp_url)
        except Exception:
            logger.exception("Error while disconnecting MCP client")
            raise
        finally:
            self._client_cm = None
            self._client = None
            self.is_connected = False

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.disconnect()

    async def _ensure_connected(self) -> None:
        if not self.is_connected:
            await self.connect()

    async def list_tools(self) -> List[dict]:
        """Get list of available tools from MCP server, including name and description"""
        try:
            async with self._client:
                response = await self._client.list_tools()
                tools = response if isinstance(response, list) else []
                result = []
                for t in tools:
                    if isinstance(t, dict):
                        name = t.get("name") or t.get("id") or str(t)
                        description = t.get("description") or t.get("desc") or ""
                    else:
                        name = getattr(t, "name", None) or str(t)
                        description = getattr(t, "description", None) or getattr(t, "desc", None) or ""
                    result.append({"name": name, "description": description})
                return result
        except Exception as e:
            logger.error(f"Failed to list tools: {e}")
            raise
    
    async def get_tool_schema(self, tool_name: str) -> Optional[Dict]:
        """Get the input schema for a specific tool"""
        try:
            async with self._client:
                tools_response = await self._client.list_tools()
                tools = tools_response if isinstance(tools_response, list) else []
                for tool in tools:
                    if hasattr(tool, 'name') and tool.name == tool_name:
                        return tool.inputSchema if hasattr(tool, 'inputSchema') else None
                return None
        except Exception as e:
            logger.error(f"Failed to get tool schema: {e}")
            return None
    # async def list_tools(self) -> List[str]:
    #     try:
    #         await self._ensure_connected()
    #         fetch = getattr(self._client, "list_tools", None) or getattr(self._client, "get_tools", None)
    #         if fetch is None:
    #             logger.error("Client does not expose list_tools or get_tools")
    #             return []

    #         response = await fetch()
    #         tools = response if isinstance(response, list) else []

    #         normalized: List[str] = []
    #         for t in tools:
    #             if isinstance(t, dict):
    #                 name = t.get("name") or t.get("id") or str(t)
    #             else:
    #                 name = getattr(t, "name", None) or str(t)
    #             normalized.append(name)
    #         return normalized
    #     except Exception as e:
    #         logger.exception("Failed to list tools: %s", e)
    #         raise

    # async def get_tool_schema(self, tool_name: str) -> Optional[Dict[str, Any]]:
    #     try:
    #         await self._ensure_connected()
    #         fetch = getattr(self._client, "list_tools", None) or getattr(self._client, "get_tools", None)
    #         if fetch is None:
    #             logger.error("Client does not expose list_tools or get_tools")
    #             return None

    #         response = await fetch()
    #         tools = response if isinstance(response, list) else []

    #         for t in tools:
    #             if isinstance(t, dict):
    #                 name = t.get("name") or t.get("id")
    #                 schema = t.get("inputSchema") or t.get("schema")
    #             else:
    #                 name = getattr(t, "name", None)
    #                 schema = getattr(t, "inputSchema", None) or getattr(t, "schema", None)

    #             if name == tool_name:
    #                 return schema
    #         return None
    #     except Exception as e:
    #         logger.exception("Failed to get tool schema: %s", e)
    #         return None

    def _normalize_call_result(self, res: Any) -> Any:
        if res is None:
            return None

        if isinstance(res, (dict, list, str, int, float, bool)):
            return res

        for attr in ("structured_content", "data", "result"):
            if hasattr(res, attr):
                val = getattr(res, attr)
                if isinstance(val, (dict, list, str, int, float, bool)):
                    return val
                try:
                    return json.loads(json.dumps(val))
                except Exception:
                    return val

        if hasattr(res, "content"):
            content = getattr(res, "content")
            if isinstance(content, (list, tuple)):
                texts = []
                for item in content:
                    txt = getattr(item, "text", None) or getattr(item, "value", None) or str(item)
                    if txt is not None:
                        texts.append(txt)
                joined = "".join(texts)
                try:
                    return json.loads(joined)
                except Exception:
                    return {"text": joined}
            try:
                return json.loads(content)
            except Exception:
                return content

        try:
            s = str(res)
            return json.loads(s)
        except Exception:
            return res

    async def call_tool(self, tool_name: str, input: Optional[Dict[str, Any]] = None) -> Any:
        try:
            await self._ensure_connected()

            if not hasattr(self._client, "call_tool"):
                raise RuntimeError("Client does not expose call_tool")

            if input is None:
                raw = await self._client.call_tool(tool_name)
            else:
                raw = await self._client.call_tool(tool_name, input)

            result = self._normalize_call_result(raw)
            logger.debug("call_tool %s -> %r", tool_name, result)
            return result
        except Exception as e:
            logger.exception("Failed to call tool %s: %s", tool_name, e)
            raise

    # ----------------- elicitation handler used by fastmcp -----------------
    async def _elicitation_handler(self, message: str, response_type: type, params, context):
        """
        Called by fastmcp when server requests additional structured input.
        Best-effort: we will pick an active user and create a pending elicitation request.
        """
        logger.info("Server elicitation requested: %s", message)

        # Prefer explicitly tracked active user
        user_id = self._active_user_id or session_manager.get_active_user()
        if not user_id:
            try:
                # common locations
                user_id = getattr(context, "user_id", None) or getattr(params, "requester", None)
            except Exception:
                user_id = None

        if not user_id:
            # fallback to any active session
            user_id = session_manager.get_any_active_user()

        if not user_id:
            logger.warning("No active user found for elicitation; declining.")
            return ElicitResult(action="decline")

        # create a future and notify the bot to prompt the user
        fut = session_manager.create_elicitation_request(user_id)

        # The bot will notice the pending elicitation and should proactively ask the user.
        # Here we wait for the user's reply (or timeout).
        try:
            value = await asyncio.wait_for(fut, timeout=self.elicitation_timeout)
        except asyncio.TimeoutError:
            logger.warning("Elicitation timed out for user %s", user_id)
            session_manager.cancel_elicitation(user_id)
            return ElicitResult(action="decline")

        # If FASTMCP provided a dataclass type, attempt to construct it
        if response_type:
            try:
                if isinstance(value, dict):
                    return response_type(**value)
                else:
                    # wrap value into expected field name if possible
                    return response_type(value=value)
            except Exception:
                # return explicit accept with raw content if we can't build dataclass
                return ElicitResult(action="accept", content=value)

        # no specific response type required
        return value