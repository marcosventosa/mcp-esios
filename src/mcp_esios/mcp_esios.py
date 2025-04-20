import logging
import asyncio
from datetime import datetime
from enum import Enum
from typing import List

from mcp.shared.exceptions import McpError
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool, ErrorData, INTERNAL_ERROR, METHOD_NOT_FOUND

from .__version__ import __version__

from .services.esios_service import (
    EsiosService,
    SearchIndicators,
    GetIndicatorData
)

logger = logging.getLogger(__name__)

class EsiosTools(str, Enum):
    SEARCH_INDICATORS = "search_indicators"
    GET_INDICATOR_DATA = "get_indicator_data"

def _parse_datetime(datetime_value) -> datetime:
    """Parse ISO datetime string to datetime object if needed."""
    if isinstance(datetime_value, str):
        return datetime.fromisoformat(datetime_value.replace("Z", "+00:00"))
    return datetime_value


async def serve(api_token: str) -> None:
    """Start the MCP server with ESIOS tools."""
    # Initialize ESIOS service
    try:
        esios_service = EsiosService(api_token)
        # Pre-warm the session and cache to avoid timeout during initialize request
        await esios_service._ensure_session()
        
        # Start a background task to pre-fetch indicators
        asyncio.create_task(esios_service._fetch_all_indicators())
        
        logger.info("ESIOS service initialized successfully")
    except ValueError as e:
        logger.error(f"Failed to initialize ESIOS service: {e}")
        return

    server = Server(name="mcp-esios", version=__version__)

    @server.list_tools()
    async def list_tools() -> List[Tool]:
        return [
            Tool(
                name=EsiosTools.SEARCH_INDICATORS,
                description="""
                    Searches for energy indicators in the ESIOS system (Spanish Electricity System Operator Information System) 
                    based on a text query. **The search is regex-based**, allowing for powerful pattern matching in indicator names 
                    and descriptions. You can use standard regex patterns to refine your search (e.g., "price.*market" to find 
                    indicators with "price" followed by "market"). 
                    
                    Use this tool to find available indicators by name or description before requesting their specific data. 
                    Returns a list of matching indicators with their IDs, names, and descriptions.
                """,
                inputSchema=SearchIndicators.schema(),
            ),
            Tool(
                name=EsiosTools.GET_INDICATOR_DATA,
                description="""
                    Retrieves time series data for a specific ESIOS indicator within a date range. You must provide a valid 
                    indicator ID (which can be found using the SEARCH_INDICATORS tool), start date, and end date. 
                    Dates should be in ISO8601 format (YYYY-MM-DDTHH:mm:ss.SSS[Z]). This tool returns actual data values for the specified 
                    indicator over time, which can include electricity prices, generation amounts, demand levels, or other 
                    energy metrics depending on the indicator requested. The data is typically returned as a time series with 
                    timestamps and corresponding values.
                """,
                inputSchema=GetIndicatorData.schema(),
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> List[TextContent]:
        try:
            if name == EsiosTools.SEARCH_INDICATORS:
                parameters = SearchIndicators(**arguments)
                result = await esios_service.search_indicators(parameters)
                return [TextContent(type="text", text=result)]
                
            elif name == EsiosTools.GET_INDICATOR_DATA:
                # Parse dates
                #start_date = _parse_datetime(arguments["start_date"])
                #end_date = _parse_datetime(arguments["end_date"])
                parameters = GetIndicatorData(**arguments)
                result = await esios_service.get_indicator_data(parameters)
                return [TextContent(type="text", text=result)]
                
            else:
                #raise ValueError(f"Unknown tool: {name}, available tools: {list_tools()}")
                raise McpError(ErrorData(code=METHOD_NOT_FOUND, message=f"Unknown tool: {name}, available tools: {list_tools()}"))

        except Exception as e:
            logger.error(f"Error calling tool {name}: {e}")
            raise McpError(ErrorData(code=INTERNAL_ERROR, message=f"Error calling tool {name}: {e}"))

    try:
        options = server.create_initialization_options()
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, options, raise_exceptions=True)
    finally:
        # Ensure resources are cleaned up
        await esios_service.close()