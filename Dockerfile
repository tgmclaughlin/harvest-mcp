FROM python:3.13-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy project files
COPY pyproject.toml uv.lock server.py ./

# Install dependencies using uv sync
RUN uv sync

# Expose the port the server runs on
EXPOSE 8080

# Set environment variables
ENV MCP_PORT=8080

# Run the server
CMD ["uv", "run", "server.py"]
