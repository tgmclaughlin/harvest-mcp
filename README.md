# Harvest MCP Server
For interacting with the Harvest time tracking API.

<img width="1728" alt="image" src="https://github.com/user-attachments/assets/48fd5805-bf07-4852-b56c-daf8b92ace40" />

## Features

This MCP server provides the following tools for interacting with Harvest:

### User Information
- `get_current_user`: Retrieve information about the authenticated user

### Time Entries
- `list_time_entries`: List time entries with optional date filtering
- `get_time_entry`: Retrieve a specific time entry by ID
- `create_time_entry`: Create a new time entry via duration
- `create_time_entry_via_start_end`: Create a time entry with start/end times
- `update_time_entry`: Update an existing time entry
- `delete_time_entry`: Delete a time entry
- `delete_time_entry_external_reference`: Delete a time entry's external reference
- `restart_time_entry`: Restart a stopped time entry
- `stop_time_entry`: Stop a running time entry

### Projects and Tasks
- `list_projects`: List all projects with optional filtering
- `list_tasks`: List all tasks with optional filtering

## Setup Instructions

### Prerequisites
- Docker
- Harvest account with API credentials

### Installation

#### For Claude Desktop Users

If you're using Claude Desktop, you only need to add the following configuration to your MCP config file:

```json
"harvest": {
  "command": "docker",
  "args": [
    "run",
    "-i",
    "--rm",
    "-e",
    "HARVEST_ACCOUNT_ID",
    "-e",
    "HARVEST_TOKEN",
    "tommcl/harvest-mcp"
  ],
  "env": {
    "HARVEST_ACCOUNT_ID": "YOUR_ACCOUNT_ID",
    "HARVEST_TOKEN": "YOUR_API_TOKEN"
  }
}
```

> **Note**: You need to have Docker Desktop installed and running.
>
> **Credentials**: You can obtain your Personal Access Token (PAT) and Account ID from the [Harvest Developer Tools page](https://id.getharvest.com/developers).

#### Option 1: Pull from Docker Hub (For Other MCP Clients)

1. Pull the Docker image directly from Docker Hub:
   ```bash
   docker pull tommcl/harvest-mcp
   ```

#### Option 2: Build Locally (For Development)

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/harvest-mcp.git
   cd harvest-mcp
   ```

2. Build the Docker image:
   ```bash
   docker build -t mcp/harvest .
   ```

   Then use "mcp/harvest" instead of "tommcl/harvest-mcp" in your MCP config.

   > **Note**: Replace the example credentials with your actual Harvest API credentials. You can obtain your Personal Access Token (PAT) and Account ID from the [Harvest Developer Tools page](https://id.getharvest.com/developers).

## Usage
Test it out using Claude Desktop.

## License

[MIT License](LICENSE)
