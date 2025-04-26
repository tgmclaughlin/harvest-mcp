import os
import httpx
import json
import logging
import re
from typing import Dict, Any, Optional, List, Union
from urllib.parse import urlencode
from mcp.server.fastmcp import FastMCP, Context
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("harvest-mcp")

load_dotenv()

class Config:
    """Centralized configuration for the application."""
    PORT = int(os.environ.get("MCP_PORT", 8080))
    BASE_URL = "https://api.harvestapp.com/api/v2"
    DEFAULT_HEADERS = {
        "User-Agent": "Harvest MCP Server",
        "Content-Type": "application/json",
    }
    HARVEST_ACCOUNT_ID = os.environ.get("HARVEST_ACCOUNT_ID")
    HARVEST_TOKEN = os.environ.get("HARVEST_TOKEN")

def mask_sensitive_data(text: str) -> str:
    """Mask sensitive data like tokens and credentials in strings."""
    if not text:
        return text

    text = re.sub(r'(Bearer\s+)[^\s"]+', r'\1[REDACTED]', text)
    text = re.sub(r'(Authorization["\s]*:)[^,}\n]+', r'\1 [REDACTED]', text)
    text = re.sub(r'(token|TOKEN|Token)["\s]*:?["\s]*[^,}\s"]+', r'\1: [REDACTED]', text)

    return text

def build_query_string(params: Dict[str, Any]) -> str:
    """Build a URL query string from a dictionary of parameters.

    Args:
        params: Dictionary of query parameters

    Returns:
        A URL-encoded query string
    """
    filtered_params = {k: v for k, v in params.items() if v is not None}

    for key, value in filtered_params.items():
        if isinstance(value, bool):
            filtered_params[key] = str(value).lower()

    if not filtered_params:
        return ""

    return urlencode(filtered_params)

logger.info("Checking required environment variables...")
logger.info(f"HARVEST_ACCOUNT_ID is {'set' if Config.HARVEST_ACCOUNT_ID else 'NOT SET'}")
logger.info(f"HARVEST_TOKEN is {'set' if Config.HARVEST_TOKEN else 'NOT SET'}")

mcp = FastMCP(
    "Harvest Time Tracker",
    description="MCP server for interacting with Harvest time tracking API"
)

class HarvestAPIError(Exception):
    """Custom exception for Harvest API errors."""
    def __init__(self, status_code: int, message: str, endpoint: str):
        self.status_code = status_code
        self.message = message
        self.endpoint = endpoint
        super().__init__(f"Harvest API error: {status_code} - {message}")

async def harvest_request(
        endpoint: str,
        method: str = "GET",
        data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Make an authenticated request to the Harvest API.

    Args:
        endpoint: The API endpoint to call
        method: HTTP method (GET, POST, PATCH, DELETE)
        data: Optional data to send with the request

    Returns:
        The JSON response from the API

    Raises:
        ValueError: If required environment variables are missing or method is invalid
        HarvestAPIError: If the API returns an error response
    """
    account_id = Config.HARVEST_ACCOUNT_ID
    token = Config.HARVEST_TOKEN

    if not account_id or not token:
        raise ValueError("HARVEST_ACCOUNT_ID and HARVEST_TOKEN environment variables must be set")

    headers = {
        **Config.DEFAULT_HEADERS,
        "Harvest-Account-ID": account_id,
        "Authorization": f"Bearer {token}"
    }

    url = f"{Config.BASE_URL}/{endpoint}"

    logger.info(f"Making {method} request to {url}")

    async with httpx.AsyncClient() as client:
        try:
            if method == "GET":
                response = await client.get(url, headers=headers)
            elif method == "POST":
                response = await client.post(url, headers=headers, json=data)
            elif method == "PATCH":
                response = await client.patch(url, headers=headers, json=data)
            elif method == "DELETE":
                response = await client.delete(url, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            if response.status_code >= 400:
                error_message = f"Harvest API error: {response.status_code} - {response.text}"
                safe_headers = {k: '[REDACTED]' if k.lower() in ['authorization', 'harvest-account-id'] else v
                               for k, v in headers.items()}

                logger.error(f"Request to {url} failed with status {response.status_code}")
                logger.error(f"Request headers (sanitized): {safe_headers}")

                raise HarvestAPIError(response.status_code, response.text, endpoint)

            return response.json()
        except httpx.RequestError as e:
            logger.error(f"Request error for {url}: {str(e)}")
            raise HarvestAPIError(0, f"Connection error: {str(e)}", endpoint)


@mcp.tool()
async def get_current_user() -> Dict[str, Any]:
    """Get information about the current authenticated user.

    Returns detailed information about the authenticated Harvest user,
    including name, email, role, and other account details.
    """
    user_data = await harvest_request("users/me")
    logger.info(f"Retrieved user data for {user_data.get('first_name')} {user_data.get('last_name')}")
    return user_data


@mcp.tool()
async def list_time_entries(from_date: str = None, to_date: str = None) -> Dict[str, Any]:
    """List time entries from Harvest.

    Args:
        from_date: Start date in YYYY-MM-DD format (optional)
        to_date: End date in YYYY-MM-DD format (optional)

    Returns:
        A dictionary containing time entries

    Raises:
        HarvestAPIError: If the API returns an error response
    """
    params = {}
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date

    endpoint = "time_entries"
    query_string = build_query_string(params)
    if query_string:
        endpoint = f"{endpoint}?{query_string}"

    time_entries = await harvest_request(endpoint)
    logger.info(f"Retrieved {len(time_entries.get('time_entries', []))} time entries")
    return time_entries


@mcp.tool()
async def get_time_entry(time_entry_id: str) -> Dict[str, Any]:
    """Retrieve a time entry by ID.

    Retrieves the time entry with the given ID. Returns a time entry object and a 200 OK
    response code if a valid identifier was provided.

    Args:
        time_entry_id: The ID of the time entry to retrieve

    Returns:
        A dictionary containing the time entry details
    """
    endpoint = f"time_entries/{time_entry_id}"
    time_entry = await harvest_request(endpoint)
    logger.info(f"Retrieved time entry {time_entry_id}")
    return time_entry


@mcp.tool()
async def create_time_entry(
    project_id: int,
    task_id: int,
    spent_date: str,
    user_id: int = None,
    hours: float = None,
    notes: str = None,
    external_reference: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Create a time entry via duration.

    Creates a new time entry object. Returns a time entry object and a 201 Created
    response code if the call succeeded.

    You should only use this method to create time entries when your account is configured
    to track time via duration. You can verify this by visiting the Settings page in your
    Harvest account or by checking if wants_timestamp_timers is false in the Company API.

    Args:
        project_id: The ID of the project to associate with the time entry.
        task_id: The ID of the task to associate with the time entry.
        spent_date: The ISO 8601 formatted date the time entry was spent (YYYY-MM-DD).
        user_id: The ID of the user to associate with the time entry. Defaults to the
                currently authenticated user's ID.
        hours: The current amount of time tracked. If provided, the time entry will be
              created with the specified hours and is_running will be set to false.
              If not provided, hours will be set to 0.0 and is_running will be set to true.
        notes: Any notes to be associated with the time entry.
        external_reference: An object containing the id, group_id, account_id, and
                          permalink of the external reference.

    Returns:
        A dictionary containing the created time entry details
    """
    data = {
        "project_id": project_id,
        "task_id": task_id,
        "spent_date": spent_date
    }

    if user_id is not None:
        data["user_id"] = user_id
    if hours is not None:
        data["hours"] = hours
    if notes is not None:
        data["notes"] = notes
    if external_reference is not None:
        data["external_reference"] = external_reference

    time_entry = await harvest_request("time_entries", method="POST", data=data)
    logger.info(f"Created time entry for project {project_id}, task {task_id} on {spent_date}")
    return time_entry


@mcp.tool()
async def update_time_entry(
    time_entry_id: str,
    project_id: int = None,
    task_id: int = None,
    spent_date: str = None,
    started_time: str = None,
    ended_time: str = None,
    hours: float = None,
    notes: str = None,
    external_reference: Dict[str, Any] = None,
    is_running: bool = None
) -> Dict[str, Any]:
    """Update a time entry.

    Updates the specific time entry by setting the values of the parameters passed.
    Any parameters not provided will be left unchanged. Returns a time entry object
    and a 200 OK response code if the call succeeded.

    Args:
        time_entry_id: The ID of the time entry to update.
        project_id: The ID of the project to associate with the time entry.
        task_id: The ID of the task to associate with the time entry.
        spent_date: The ISO 8601 formatted date the time entry was spent (YYYY-MM-DD).
        started_time: The time the entry started. Example: "8:00am".
        ended_time: The time the entry ended.
        hours: The current amount of time tracked.
        notes: Any notes to be associated with the time entry.
        external_reference: An object containing the id, group_id, account_id, and
                          permalink of the external reference.
        is_running: Whether the time entry is currently running. Set to false to stop a running timer.

    Returns:
        A dictionary containing the updated time entry details
    """
    data = {}

    if project_id is not None:
        data["project_id"] = project_id
    if task_id is not None:
        data["task_id"] = task_id
    if spent_date is not None:
        data["spent_date"] = spent_date
    if started_time is not None:
        data["started_time"] = started_time
    if ended_time is not None:
        data["ended_time"] = ended_time
    if hours is not None:
        data["hours"] = hours
    if notes is not None:
        data["notes"] = notes
    if external_reference is not None:
        data["external_reference"] = external_reference
    if is_running is not None:
        data["is_running"] = is_running

    endpoint = f"time_entries/{time_entry_id}"
    time_entry = await harvest_request(endpoint, method="PATCH", data=data)
    logger.info(f"Updated time entry {time_entry_id}")
    return time_entry


@mcp.tool()
async def delete_time_entry(time_entry_id: str) -> Dict[str, Any]:
    """Delete a time entry.

    Delete a time entry. Deleting a time entry is only possible if it's not closed
    and the associated project and task haven't been archived. However, Admins can
    delete closed entries. Returns a 200 OK response code if the call succeeded.

    Args:
        time_entry_id: The ID of the time entry to delete.

    Returns:
        An empty dictionary if successful
    """
    endpoint = f"time_entries/{time_entry_id}"
    result = await harvest_request(endpoint, method="DELETE")
    logger.info(f"Deleted time entry {time_entry_id}")
    return result


@mcp.tool()
async def list_projects(
    is_active: bool = None,
    client_id: int = None,
    updated_since: str = None,
    per_page: int = None
) -> Dict[str, Any]:
    """List all projects.

    Returns a list of your projects. The projects are returned sorted by creation date,
    with the most recently created projects appearing first.

    The response contains an object with a projects property that contains an array of
    up to per_page projects. Each entry in the array is a separate project object.
    If no more projects are available, the resulting array will be empty.

    Args:
        is_active: Pass true to only return active projects and false to return inactive projects.
        client_id: Only return projects belonging to the client with the given ID.
        updated_since: Only return projects that have been updated since the given date and time.
        per_page: The number of records to return per page. Can range between 1 and 2000. (Default: 2000)

    Returns:
        A dictionary containing the projects and pagination information

    Raises:
        HarvestAPIError: If the API returns an error response
    """
    params = {
        "is_active": is_active,
        "client_id": client_id,
        "updated_since": updated_since,
        "per_page": per_page
    }

    endpoint = "projects"
    query_string = build_query_string(params)
    if query_string:
        endpoint = f"{endpoint}?{query_string}"

    projects = await harvest_request(endpoint)
    logger.info(f"Retrieved {len(projects.get('projects', []))} projects")
    return projects


@mcp.tool()
async def list_tasks(
    is_active: bool = None,
    updated_since: str = None,
    per_page: int = None
) -> Dict[str, Any]:
    """List all tasks.

    Returns a list of your tasks. The tasks are returned sorted by creation date,
    with the most recently created tasks appearing first.

    The response contains an object with a tasks property that contains an array of
    up to per_page tasks. Each entry in the array is a separate task object.
    If no more tasks are available, the resulting array will be empty.

    Args:
        is_active: Pass true to only return active tasks and false to return inactive tasks.
        updated_since: Only return tasks that have been updated since the given date and time.
        per_page: The number of records to return per page. Can range between 1 and 2000. (Default: 2000)

    Returns:
        A dictionary containing the tasks and pagination information

    Raises:
        HarvestAPIError: If the API returns an error response
    """
    params = {
        "is_active": is_active,
        "updated_since": updated_since,
        "per_page": per_page
    }

    endpoint = "tasks"
    query_string = build_query_string(params)
    if query_string:
        endpoint = f"{endpoint}?{query_string}"

    tasks = await harvest_request(endpoint)
    logger.info(f"Retrieved {len(tasks.get('tasks', []))} tasks")
    return tasks


@mcp.tool()
async def create_time_entry_via_start_end(
    project_id: int,
    task_id: int,
    spent_date: str,
    user_id: int = None,
    started_time: str = None,
    ended_time: str = None,
    notes: str = None,
    external_reference: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Create a time entry via start and end time.

    Creates a new time entry object. Returns a time entry object and a 201 Created
    response code if the call succeeded.

    You should only use this method to create time entries when your account is configured
    to track time via start and end time. You can verify this by visiting the Settings page
    in your Harvest account or by checking if wants_timestamp_timers is true in the Company API.

    Args:
        project_id: The ID of the project to associate with the time entry.
        task_id: The ID of the task to associate with the time entry.
        spent_date: The ISO 8601 formatted date the time entry was spent (YYYY-MM-DD).
        user_id: The ID of the user to associate with the time entry. Defaults to the
                currently authenticated user's ID.
        started_time: The time the entry started. Defaults to the current time. Example: "8:00am".
        ended_time: The time the entry ended. If provided, is_running will be set to false.
                  If not provided, is_running will be set to true.
        notes: Any notes to be associated with the time entry.
        external_reference: An object containing the id, group_id, account_id, and
                          permalink of the external reference.

    Returns:
        A dictionary containing the created time entry details
    """
    data = {
        "project_id": project_id,
        "task_id": task_id,
        "spent_date": spent_date
    }

    if user_id is not None:
        data["user_id"] = user_id
    if started_time is not None:
        data["started_time"] = started_time
    if ended_time is not None:
        data["ended_time"] = ended_time
    if notes is not None:
        data["notes"] = notes
    if external_reference is not None:
        data["external_reference"] = external_reference

    time_entry = await harvest_request("time_entries", method="POST", data=data)
    logger.info(f"Created time entry for project {project_id}, task {task_id} on {spent_date} with start/end time")
    return time_entry


@mcp.tool()
async def delete_time_entry_external_reference(time_entry_id: str) -> Dict[str, Any]:
    """Delete a time entry's external reference.

    Delete a time entry's external reference. Returns a 200 OK response code if the call succeeded.

    Args:
        time_entry_id: The ID of the time entry whose external reference should be deleted.

    Returns:
        An empty dictionary if successful
    """
    endpoint = f"time_entries/{time_entry_id}/external_reference"
    result = await harvest_request(endpoint, method="DELETE")
    logger.info(f"Deleted external reference for time entry {time_entry_id}")
    return result


@mcp.tool()
async def restart_time_entry(time_entry_id: str) -> Dict[str, Any]:
    """Restart a stopped time entry.

    Restarting a time entry is only possible if it isn't currently running.
    Returns a 200 OK response code if the call succeeded.

    Args:
        time_entry_id: The ID of the time entry to restart.

    Returns:
        A dictionary containing the restarted time entry details
    """
    endpoint = f"time_entries/{time_entry_id}/restart"
    time_entry = await harvest_request(endpoint, method="PATCH")
    logger.info(f"Restarted time entry {time_entry_id}")
    return time_entry


@mcp.tool()
async def stop_time_entry(time_entry_id: str) -> Dict[str, Any]:
    """Stop a running time entry.

    Stopping a time entry is only possible if it's currently running.
    Returns a 200 OK response code if the call succeeded.

    Args:
        time_entry_id: The ID of the time entry to stop.

    Returns:
        A dictionary containing the stopped time entry details
    """
    endpoint = f"time_entries/{time_entry_id}/stop"
    time_entry = await harvest_request(endpoint, method="PATCH")
    logger.info(f"Stopped time entry {time_entry_id}")
    return time_entry


if __name__ == "__main__":
    logger.info(f"Starting Harvest MCP Server...")
    mcp.run()