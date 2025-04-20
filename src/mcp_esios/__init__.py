import asyncio
import click
import logging
import os
import sys
from typing import Optional

from .__version__ import __version__
from .mcp_esios import serve

def configure_logging(verbose: int) -> None:
    """Configure logging based on verbosity level."""
    if verbose == 0:
        logging_level = logging.WARNING
    elif verbose == 1:
        logging_level = logging.INFO
    else:
        logging_level = logging.DEBUG
    
    logging.basicConfig(
        level=logging_level,
        stream=sys.stderr,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def get_api_token() -> Optional[str]:
    """Get the ESIOS API token from environment variables."""
    token = os.getenv("ESIOS_API_TOKEN")
    if not token:
        logging.error("ESIOS_API_TOKEN environment variable is not set.")
        return None
    return token

@click.command()
@click.option("-v", "--verbose", count=True, help="Increase verbosity (can be used multiple times)")
def main(verbose: int) -> None:
    """ESIOS MCP Client - REE ESIOS API functionality for MCP."""
    configure_logging(verbose)
    
    token = get_api_token()
    if token is None:
        sys.exit(1)
        
    asyncio.run(serve(token))

if __name__ == "__main__":
    main()