import json
import logging
import datetime
import re
from typing import Any, Dict, List, Optional
from openai import AsyncOpenAI
from config import settings
from operator import itemgetter
from langchain_openai.chat_models import ChatOpenAI
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import BaseModel, Field
from langchain_core.runnables import RunnableLambda, ConfigurableFieldSpec, RunnablePassthrough
from langchain_core.runnables.history import RunnableWithMessageHistory

logger = logging.getLogger(__name__)

class InMemoryHistory(BaseChatMessageHistory, BaseModel):
    messages: list[BaseMessage] = Field(default_factory=list)
    def add_messages(self, messages: list[BaseMessage]) -> None:
        self.messages.extend(messages)
    def clear(self) -> None:
        self.messages = []

_store: Dict[str, InMemoryHistory] = {}

def get_by_session_id(session_id: str) -> BaseChatMessageHistory:
    if session_id not in _store:
        _store[session_id] = InMemoryHistory()
    return _store[session_id]

class IntentManager:
    """
    Centralized AI decision layer that:
    - Interprets natural language input and decides whether to call a tool or reply conversationally
    - Composes a concise, user-friendly reply after a tool has been executed
    """

    def __init__(self, api_key: str, model: str):
        self.client = AsyncOpenAI(api_key=api_key)
        # Keep model configurable without exposing the name in logs/messages
        self._model = model or "default-model"
        # Simple per-user conversation memory (rolls recent messages)
        self._history: Dict[str, List[Dict[str, str]]] = {}
        # LangChain memory-backed chat for non-tool replies
        self._chat_prompt = ChatPromptTemplate.from_messages([
            ('system', 'You are a helpful assistant.'),
            MessagesPlaceholder(variable_name='history'),
            ('human', '{input}')
        ])
        self._chat_llm = ChatOpenAI(model=self._model, api_key=settings.openai_api_key, temperature=0.7)
        self._chat_chain = self._chat_prompt | self._chat_llm
        self._chat_with_history = RunnableWithMessageHistory(
            self._chat_chain,
            get_by_session_id,
            history_messages_key='history',
            input_messages_key='input'
        )

    # Legacy ConversationChain helper removed in favor of RunnableWithMessageHistory.

    async def decide_tool_or_reply(self, tools: List[Any], message: str, context: Dict[str, Any] | None = None, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Ask the LLM to decide whether a tool should be called.
        If tool should be called, the model must reply with JSON:
        {"tool_call": {"name":"<tool_name>", "input": { ... } } }
        Otherwise respond with JSON: {"response": "friendly textual reply"}
        Context may include user/company info to ground decisions and payloads.
        """
        # Extract available tool names
        tool_names: List[str] = []
        for t in tools:
            if isinstance(t, str):
                tool_names.append(t)
            elif isinstance(t, dict):
                tool_names.append(t.get("name") or t.get("id") or str(t))
            else:
                tool_names.append(getattr(t, "name", None) or str(t))
        tools_str = ", ".join([n for n in tool_names if n]) or "(none)"

        # Build per-tool hints from TOOL_CONFIG to guide field mapping and normalization
        tool_hints: Dict[str, Any] = {}
        for name in tool_names:
            cfg = settings.TOOL_CONFIG.get(name, {})
            if not cfg:
                continue
            hint: Dict[str, Any] = {
                "required_fields": cfg.get("required_fields", []),
                "defaults": cfg.get("defaults", {}),
            }
            if cfg.get("triggers") and cfg.get("purpose"):
                hint.update({
                    "triggers": cfg.get("triggers"),
                    "purpose": cfg.get("purpose"),
                })
            if name == "create_task":
                # Synonyms and normalization guidance for create_task
                hint.update({
                    "field_aliases": {
                        "text": ["title", "name"],
                        "planningParentId": ["project", "project_id"]
                    },
                    "value_maps": {
                        "plan_type": {
                            "task": "3000", "milestone": "6000", "subtask": "9000"
                        }
                    },
                    "date_formats": {
                        "start_date": "YYYY-MM-DD",
                        "end_date": "YYYY-MM-DD"
                    }
                })
            tool_hints[name] = hint

        schema_hints_str = json.dumps(tool_hints, default=str)
        ctx_str = ("\nContext: " + json.dumps(context, default=str)) if context else ""

        system = (
            "You are an assistant with access to tools. Your primary goal is to identify the user's intent and execute the appropriate tool. "
            "If a tool call is needed, RETURN ONLY a JSON object with the key 'tool_call', containing the tool's 'name' and 'input'. "
            "If no tool is suitable, RETURN ONLY a JSON object with the key 'response' for a conversational reply. "
            "Use the provided tool hints to map user phrases to the correct tool and its input fields. "
            "Always include all 'required_fields' and use the 'defaults' for any missing values. "
            "You are responsible for all field parsing and type conversion, including converting natural language dates (e.g., 'next Monday') to 'YYYY-MM-DD' format. "
            "If the user's intent is ambiguous, ask for clarification. If a command is incomplete, ask for the missing information. "
            "Do NOT add any explanatory text outside the JSON output."
        )

        prompt = (
            f"Available tools: {tools_str}\n\n"
            f"Tool hints: {schema_hints_str}\n\n"
            f"User message: {message}{ctx_str}\n\n"
            "Return JSON only."
        )

        # Build message list with memory
        messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
        
        

        if user_id:
            history = self._history.get(user_id, [])
            # include only the last 10 turns to keep prompts small
            messages.extend(history[-10:])
        messages.append({"role": "user", "content": prompt})

        logger.info(f"Prompt: {prompt}")
        logger.info(f"Messages: {messages}")
        
        try:
            resp = await self.client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=600,
                temperature=0.0,
            )
            
            text = resp.choices[0].message.content.strip()
            
            logger.info(f"Response: {text}")
            
            try:
                decision = json.loads(text)
                logger.info(f"Decision: {decision}")
            except Exception:
                # Try to extract JSON block
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end != -1 and end > start:
                    try:
                        decision = json.loads(text[start:end+1])
                    except Exception:
                        decision = {"response": text}
                else:
                    decision = {"response": text}
            # If no tool call is needed, use memory-backed chat to generate the reply
            # Skip re-generation if we already have a valid tool_call or a non-empty response
            if isinstance(decision, dict) and (decision.get("tool_call") or decision.get("response")):
                pass
            else:
                # No valid decision yet; fall back to memory-backed chat
                session = user_id or "default"
                ai_msg = self._chat_with_history.invoke({"input": message}, config={"configurable": {"session_id": session}})
                reply_text = getattr(ai_msg, "content", str(ai_msg))
                decision = {"response": reply_text}
            # Update memory with the user's raw message and a concise assistant summary
            if user_id:
                hist = self._history.setdefault(user_id, [])
                hist.append({"role": "user", "content": message})
                if isinstance(decision, dict) and decision.get("tool_call"):
                    tool = decision["tool_call"].get("name") or "(unknown tool)"
                    hist.append({"role": "assistant", "content": f"[tool_call] {tool}"})
                else:
                    reply = decision.get("response") if isinstance(decision, dict) else str(decision)
                    hist.append({"role": "assistant", "content": reply or ""})
                # Trim memory to last 20 entries
                if len(hist) > 20:
                    self._history[user_id] = hist[-20:]
            
            logger.info(f"Final Decision: {decision}")
            return decision
        except Exception as e:
            logger.exception("AI decision failed: %s", e)
            return {"response": "Sorry, I couldn't process your request right now."}

    async def compose_post_tool_reply(self, prior_decision: Dict[str, Any], tool: str, input_payload: Dict[str, Any], tool_result: Any, user_id: Optional[str] = None) -> str:
        """
        Provide the tool result to the model and ask it to produce the final message to the user.
        """
        system = "You are an assistant that helps compose a concise, user-friendly reply based on a tool execution result."
        user_msg = {
            "tool": tool,
            "input": input_payload,
            "result": tool_result,
            "prior_decision": prior_decision,
        }
        try:
            # Build message list with memory
            messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
            if user_id:
                history = self._history.get(user_id, [])
                messages.extend(history[-10:])
            messages.append({"role": "user", "content": json.dumps(user_msg, default=str)})

            resp = await self.client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=500,
                temperature=0.2,
            )
            reply = resp.choices[0].message.content.strip()
            # Add assistant reply to memory
            if user_id:
                hist = self._history.setdefault(user_id, [])
                hist.append({"role": "assistant", "content": reply})
                if len(hist) > 20:
                    self._history[user_id] = hist[-20:]
                # Also record a brief update in the LangChain message history
                try:
                    if user_id:
                        lc_hist = get_by_session_id(user_id)
                        lc_hist.add_messages([AIMessage(content=f"Update: Executed tool '{tool}'. Result noted.")])
                except Exception:
                    pass
            return reply
        except Exception as e:
            logger.exception("AI post-tool composition failed: %s", e)
            return f"Tool '{tool}' finished. Result: {tool_result}"