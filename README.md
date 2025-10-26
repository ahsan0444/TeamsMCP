# MCP Teams Bot

This project is a Microsoft Teams bot that integrates with a backend system (MCP) to provide functionalities like user authentication, task creation, and information retrieval through a conversational interface. The bot uses natural language understanding to interpret user commands and interacts with the MCP system via a set of defined tools.

## Features

- **Conversational AI:** Uses a Large Language Model (LLM) via OpenAI to understand user messages and decide on actions.
- **Tool-Based Functionality:** A set of tools are available for the bot to use, suchas:
    - `login`: Authenticate users.
    - `create_task`: Create tasks in the backend system.
    - `get_user_and_company_info`: Fetch user and company details.
    - `logout`: Log out the user.
- **Adaptive Cards:** Rich, interactive cards are used for login forms, task creation, and displaying information in Teams.
- **Session Management:** Manages user sessions and authentication state.
- **Pre-filled Cards:** Intelligently pre-fills login and task creation cards based on user input to streamline workflows.

## Architecture

The project consists of three main components:

1.  **Teams Bot (`main.py`, `bot.py`):**
    - A FastAPI server that exposes the `/api/messages` endpoint for the Microsoft Bot Framework.
    - The `MCPTeamsBot` class handles the bot's logic, processing incoming messages, handling adaptive card submissions, and managing conversation flow.

2.  **MCP Server (`mcp_server.py`):**
    - A mock/proxy server built with `fastmcp` that simulates the real MCP backend.
    - It exposes tools that the bot can call, such as `login`, `create_task`, etc.
    - It maintains a simple in-memory session store.

3.  **Intent Manager (`intent_manager.py`):**
    - This component is the AI brain of the bot.
    - It uses an LLM to analyze user messages and decide whether to have a conversation or to call one of the available MCP tools.
    - It's responsible for entity extraction from the user's text to pre-fill cards and tool payloads.

## Prerequisites

- Python 3.10
- `uv` package manager (or `pip`)

## Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd TeamsMCP
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows, use `.venv\Scripts\activate`
    ```

3.  **Install dependencies:**
    The project uses `uv` for dependency management. You can install dependencies from `pyproject.toml`.
    ```bash
    pip install uv
    uv pip install -e .
    ```
    Alternatively, if you prefer using `pip` directly:
    ```bash
    pip install -e .
    ```

4.  **Configure Environment Variables:**
    Create a `.env` file in the project root and add the following variables.

    ```env
    MICROSOFT_APP_ID="your-microsoft-app-id"
    MICROSOFT_APP_PASSWORD="your-microsoft-app-password"
    MICROSOFT_APP_TENANT_ID="your-tenant-id"

    # OpenAI API Key for the Intent Manager
    OPENAI_API_KEY="your-openai-api-key"
    OPENAI_MODEL="gpt-4-turbo" # Or another model of your choice

    # URL for the MCP Server
    MCP_SERVER_URL="http://localhost:5001/mcp"

    # Port for the bot server
    BOT_PORT=8000
    ```

## Running the Application

You need to run two services in separate terminals: the MCP Server and the Bot Server.

1.  **Run the MCP Server:**
    This server simulates the backend services.
    ```bash
    python mcp_server.py
    ```
    The MCP server will be running at `http://localhost:5001`.

2.  **Run the Bot Server:**
    This server runs the bot and connects to the Bot Framework.
    ```bash
    python main.py
    ```
    The bot server will be running at `http://localhost:8000`.

3.  **Expose your bot to the internet:**
    For Microsoft Teams to communicate with your bot, your local server needs to be accessible from the internet. Use a tool like `ngrok` to create a secure tunnel.
    ```bash
    ngrok http 8000
    ```
    Take the `https` URL provided by `ngrok` (e.g., `https://<unique-id>.ngrok.io`) and use it as the messaging endpoint in your bot's configuration in the Azure Bot portal (the full URL would be `https://<unique-id>.ngrok.io/api/messages`).

## Project Structure

```
├── .gitignore
├── .python-version   # Specifies Python version 3.10
├── README.md         # This file
├── bot.py            # Core bot logic, message handling, and command processing
├── cards.py          # Functions for creating Adaptive Cards
├── config.py         # Application configuration using Pydantic
├── intent_manager.py # AI decision layer for tool calling and conversational replies
├── main.py           # FastAPI entry point for the bot server
├── mcp_client.py     # Client for communicating with the MCP server
├── mcp_server.py     # Mock MCP server exposing tools
├── pyproject.toml    # Project metadata and dependencies
├── session_manager.py# Manages user sessions and state
├── utils.py          # Utility functions
└── uv.lock           # Dependency lock file for `uv`
```

## Usage

Once the bot is running and configured in Teams, you can interact with it through chat messages:

- **"login"**: Shows the login card.
- **"my username is example@user.com"**: Shows the login card with the username pre-filled.
- **"create a task to test integration"**: Shows the task creation card with the title pre-filled.
- **"list tools"**: Shows a list of available tools.
- **"show session"**: Displays your current session information.