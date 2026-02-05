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
                    Searches for energy indicators in the Spanish electricity system (Red Eléctrica de España - REE ESIOS).
                    ESIOS provides data on electricity prices, demand, generation by source (solar, wind, nuclear, etc.), 
                    cross-border exchanges, and system operations.
                    
                    **Search is regex-based** - use Spanish terms like:
                    - "precio" - find all price-related indicators
                    - "demanda|consumo" - find demand or consumption indicators  
                    - "solar|eólica" - find renewable generation indicators
                    - "mercado.*diario" - find daily market indicators
                    - "generación.*nuclear" - find nuclear generation data
                    
                    **Returns structured JSON** with:
                    - indicator metadata (ID, name, unit, data_type)
                    - total match count
                    - usage guidance
                    
                    Use indicator IDs from results with get_indicator_data to retrieve actual time series data.
                """,
                inputSchema=SearchIndicators.schema(),
            ),
            Tool(
                name=EsiosTools.GET_INDICATOR_DATA,
                description="""
                    Retrieves time series data for a specific ESIOS indicator within a date range. You must provide a valid 
                    indicator ID (found using search_indicators), start date, and end date in ISO8601 format.
                    
                    **Parameters guidance**:
                    - time_trunc: "hour" for detailed data, "day" for daily summaries, "month"/"year" for longer periods
                    - time_agg: "avg" for prices (€/MWh), "sum" for energy quantities (MWh)
                    
                    **Returns structured JSON** with:
                    - Complete indicator metadata (name, unit, description)
                    - Summary statistics (min, max, avg, count)
                    - Time series data points with timestamps and values
                    - Query parameters for reference
                    
                    Common data types include:
                    - Electricity prices in €/MWh
                    - Generation/demand in MW or MWh  
                    - Cross-border flows in MW
                    - System operation metrics
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