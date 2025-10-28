# OMG Teams Bot with Agent & MCP Integration

An intelligent Microsoft Teams bot that uses OpenAI's Agents SDK and Model Context Protocol (MCP) to help users manage tasks and navigate the OMG project management system.

## Features

- **Intelligent Agent**: Uses OpenAI's Agents SDK to analyze user intent and decide when to use MCP tools vs. general knowledge
- **MCP Tool Integration**: Connects to OMG backend via MCP tools for authentication, task management, and site switching
- **Adaptive Cards**: Interactive cards for login forms, task creation, site switching, and displaying results
- **In-Memory Session Management**: Maintains user authentication state and conversation history
- **Multi-Turn Conversations**: Context-aware interactions that remember previous messages

## Architecture

```
┌─────────────────┐
│  Microsoft      │
│  Teams Client   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Bot Framework  │
│  Adapter        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  AgentTeamsBot  │
│  - Event        │
│    Handling     │
│  - Card Forms   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐       ┌──────────────┐
│  OpenAI Agent   │◄─────►│ MCP Server   │
│  with Streaming │       │ - login      │
│                 │       │ - create_task│
│                 │       │ - get_info   │
│                 │       │ - switch_site│
└─────────────────┘       └──────┬───────┘
         │                        │
         ▼                        ▼
┌─────────────────┐       ┌──────────────┐
│ Session Manager │       │ OMG Backend  │
│ (In-Memory)     │       │              │
└─────────────────┘       └──────────────┘
```

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Environment Variables

All required environment variables are already configured in `.env`:

- `MICROSOFT_APP_ID`: Bot's Azure App Registration ID
- `MICROSOFT_APP_PASSWORD`: Bot's client secret
- `MICROSOFT_APP_TENANT_ID`: Azure AD tenant ID
- `OPENAI_API_KEY`: OpenAI API key for agent
- `BOT_PORT`: Port for bot server (default: 8000)
- `BASE_URL`: OMG backend URL
- `LOGIN_BASE_URL`: OMG login URL
- `APP_BASE_URL`: Public URL for ngrok/webhook

### 3. Run the Bot

```bash
cd bot_app
python main.py
```

The bot will:
1. Start the MCP server
2. Load system instructions from `prompts/system_instructions.md`
3. Initialize the OpenAI Agent with MCP tools
4. Start the web server on port 8000

### 4. Expose Bot to Internet (for Teams)

Use ngrok or similar to expose your local bot:

```bash
ngrok http 8000
```

Update `APP_BASE_URL` in `.env` with the ngrok URL.

### 5. Configure Bot in Azure

1. Go to Azure Portal → Bot Services → Your Bot
2. Update the Messaging endpoint to: `https://your-ngrok-url.ngrok-free.dev/api/messages`
3. Save changes

## Usage

### Authentication

**User**: "Log me in"

The bot will ask for credentials or show a login card. After successful login, it displays your current site and user information.

### Task Management

**User**: "Create a task called Website Redesign due tomorrow"

The agent will:
1. Extract task details from your message
2. Ask for missing information (like project ID)
3. Show a task creation card pre-filled with your details
4. After submission, display the created task with a link

### Site Switching

**User**: "What sites can I access?"

The agent fetches available sites and shows them in a dropdown card. You can select and switch to another site.

### General Queries

**User**: "How do I track project progress?"

The agent uses its general knowledge to provide helpful guidance when no MCP tool is needed.

## Project Structure

```
bot_app/
├── main.py                 # Application entry point
├── agent_bot.py            # Bot logic and event handling
├── mcp_server.py           # MCP tools for OMG backend
├── session_manager.py      # In-memory session management
├── cards.py                # Adaptive card factories
├── config.py               # Configuration and settings
└── prompts/
    └── system_instructions.md  # Agent behavior instructions
```

## Key Components

### AgentTeamsBot (`agent_bot.py`)

- Handles incoming messages and card submissions
- Streams events from OpenAI Agent
- Detects tool calls and shows appropriate adaptive cards
- Manages form submissions (login, create task, switch site)
- Updates session state based on tool results

### MCP Server (`mcp_server.py`)

Provides these tools to the agent:

- `login`: Authenticate users
- `get_user_and_company_info`: Fetch current user/site info
- `get_available_sites`: List accessible sites
- `switch_site`: Change active site
- `create_task`: Create tasks/milestones/subtasks
- `logout`: End session

### Session Manager (`session_manager.py`)

Maintains in-memory state:

- User authentication status
- User and company information
- Conversation history (last 30 messages)
- Accessible sites list

### Agent Instructions

The agent follows a decision tree:

1. **Analyze Intent**: What is the user asking for?
2. **Check Tool Relevance**: Do any MCP tools match?
3. **Use Tools or Knowledge**: Call tools if relevant, otherwise use general knowledge
4. **Maintain Context**: Remember conversation history for context-aware responses

## Adaptive Cards

The bot uses several card types:

- **Login Card**: Username/password form
- **Task Creation Card**: Form with project ID, title, dates, description
- **Switch Site Card**: Dropdown of available sites
- **Company Info Card**: Displays current user and site information
- **Task Result Card**: Shows created task details with link
- **Success/Error Cards**: Feedback for operations

## Conversation Flow Examples

### Creating a Task

1. User: "Create a task for the marketing campaign"
2. Agent: "I'll help you create that task. What's the project ID?"
3. User: "Project 7334"
4. Agent: [Shows pre-filled task creation card]
5. User: [Fills remaining details and submits]
6. Agent: [Shows task result card with link]

### Switching Sites

1. User: "Switch to London office"
2. Agent: [Calls get_available_sites tool]
3. Agent: [Shows site selection card]
4. User: [Selects site and submits]
5. Agent: [Shows updated company info card]

## Troubleshooting

### Bot doesn't respond

- Check bot is running: `python main.py`
- Verify ngrok is forwarding to port 8000
- Check Azure bot messaging endpoint is correct
- Review logs for errors

### MCP tools failing

- Ensure OMG backend URL is correct in `.env`
- Check user is authenticated before calling protected tools
- Review MCP server logs for connection issues

### Agent not using tools

- Check system instructions are loaded correctly
- Verify MCP server is connected
- Review agent logs to see decision making

## Development

### Adding New MCP Tools

1. Add tool function to `mcp_server.py` with `@mcp.tool()` decorator
2. Update `TOOL_CONFIG` in `config.py` to map tool to card factory
3. Create card factory in `cards.py` if needed
4. Update agent instructions if necessary

### Modifying Agent Behavior

Edit `bot_app/prompts/system_instructions.md` to change how the agent:
- Analyzes user intent
- Decides when to use tools
- Handles parameters
- Responds to users

## License

Proprietary - OMG Project Management System
