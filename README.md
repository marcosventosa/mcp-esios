# MCP ESIOS

A Python package that provides access to REE ESIOS API as MCP tools.

## Installation

Clone the repository:

```bash
git clone https://github.com/yourusername/mcp-esios.git
cd mcp-esios
```

Install the package in development mode:

```bash
pip install -e .
```

Or using uv:

```bash
uv pip install -e .
```

## Usage

### Environment Variables

You must set the `ESIOS_API_TOKEN` environment variable with your ESIOS API token:

```bash
export ESIOS_API_TOKEN=your_api_token_here
```

### Running with UV

```bash
# Run with UV package manager
uv run mcp-esios

# Increase verbosity
uv run mcp-esios -v

# Debug level verbosity
uv run mcp-esios -vv
```

### Docker

Build the Docker image:

```bash
docker build -t mcp-esios .
```

Run the container:

```bash
# Run with environment variable for the API token
docker run -e ESIOS_API_TOKEN=your_api_token_here mcp-esios
```

## Integrating with Claude Desktop

You can integrate this MCP server with Claude Desktop by adding a configuration to the Claude desktop config file:

### Docker-based Integration

```json
{
  "mcpServers": {
    "MCP_ESIOS": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-e", "ESIOS_API_TOKEN", "mcp-esios"],
      "env": {
        "ESIOS_API_TOKEN": "your_api_token_here"
      }
    }
  }
}

```

### UV-based Integration

```json
{
    "mcpServers": {
        "MCP_ESIOS": {
            "command": "uv",
            "args": [
                "--directory",
                "/path/to/mcp-esios",
                "run",
                "mcp-esios"
            ],
            "env": {
                "ESIOS_API_TOKEN": "your_api_token_here"
            }
        }
    }
}
```

Add the configuration to Claude Desktop's config file:
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

For more information about MCP integration, see the [MCP Quickstart Guide](https://modelcontextprotocol.io/quickstart/user).

## Available Tools

This MCP server provides the following tools:

1. `search_indicators` - Search for indicators by name or description
2. `get_indicator_data` - Retrieve data for a specific indicator within a date range
