import logging
import re
from datetime import datetime
from typing import List, Optional

import aiohttp
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class SearchIndicators(BaseModel):
    query: str = Field(..., description="Regex search query to filter indicators by name or description")


class GetIndicatorData(BaseModel):
    indicator_id: int = Field(..., description="ID of the indicator to retrieve")
    start_date: datetime = Field(..., description="Start date for the data retrieval")
    end_date: datetime = Field(..., description="End date for the data retrieval")
    time_trunc: str = Field("hour", description="Time truncation (hour, day, month, year)")
    time_agg: str = Field("sum", description="Time aggregation (sum, avg), default is sum, generation should use sum and price should use avg")


class EsiosService:
    BASE_URL = "https://api.esios.ree.es"
    TIMEOUT = 600  # seconds
    MAX_SAMPLE_VALUES = 10000

    def __init__(self, api_token: str) -> None:
        """Initializes the connection to the ESIOS API."""
        if not api_token:
            raise ValueError("API token is required to access ESIOS API.")
        
        self.headers = {'x-api-key': api_token}
        self.indicators_cache: Optional[List[dict]] = None
        self.session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensures an aiohttp session is available."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def _fetch_all_indicators(self) -> List[dict]:
        """Fetches all indicators from ESIOS API and caches them."""
        if self.indicators_cache is None:
            try:
                session = await self._ensure_session()
                timeout = aiohttp.ClientTimeout(total=self.TIMEOUT)
                
                async with session.get(
                    f"{self.BASE_URL}/indicators", 
                    headers=self.headers,
                    timeout=timeout
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
                    self.indicators_cache = data['indicators']
                    logger.info(f"Successfully cached {len(self.indicators_cache)} indicators")
            except aiohttp.ClientError as e:
                logger.error(f"Network error fetching indicators: {e}")
                self.indicators_cache = []
            except Exception as e:
                logger.error(f"Failed to fetch indicators: {e}")
                self.indicators_cache = []
        
        return self.indicators_cache

    async def search_indicators(self, parameters: SearchIndicators) -> str:
        """Searches for indicators matching the query in their name or description."""
        try:
            indicators = await self._fetch_all_indicators()
            
            try:
                pattern = re.compile(parameters.query, re.IGNORECASE)
            except re.error:
                return f"Invalid regex pattern: '{parameters.query}'"

            matching_indicators = []
            for ind in indicators:
                if (pattern.search(ind['name']) or 
                    pattern.search(ind['short_name']) or
                    pattern.search(ind.get('description', ''))):
                    matching_indicators.append(ind)

            if not matching_indicators:
                return "No indicators found matching your query."

            result = f"Found {len(matching_indicators)} matching indicators:\n\n"
            
            # For better LLM processing, use consistent formatting
            for ind in matching_indicators:
                result += f"ID: {ind['id']}\n"
                result += f"Name: {ind['name']}\n"
                if ind.get('short_name'):
                    result += f"Short name: {ind['short_name']}\n"
                
                # Include description - it's crucial for LLMs to understand what the indicator represents
                if ind.get('description'):
                    result += f"Description: {ind['description']}\n"
                
                result += "\n"

            if len(matching_indicators) > 100:
                result += "Note: Large result set returned. Consider refining your search query for more targeted results.\n"
                
            result += "Use the indicator ID with get_indicator_data to retrieve actual time series data."
            
            return result
        except Exception as e:
            logger.error(f"Failed to search indicators: {e}")
            return f"Failed to search indicators: {e}"

    async def get_indicator_data(self, parameters: GetIndicatorData) -> str:
        """Retrieves data for a specific indicator within the given date range."""
        try:
            start_date_str = parameters.start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
            end_date_str = parameters.end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

            endpoint = (
                f"{self.BASE_URL}/indicators/{parameters.indicator_id}"
                f"?start_date={start_date_str}&end_date={end_date_str}"
                f"&time_trunc={parameters.time_trunc}"
                f"&time_agg={parameters.time_agg}"
            )

            session = await self._ensure_session()
            timeout = aiohttp.ClientTimeout(total=self.TIMEOUT)
            
            async with session.get(endpoint, headers=self.headers, timeout=timeout) as response:
                response.raise_for_status()
                indicator_data = await response.json()

            indicator_info = indicator_data['indicator']
            values = indicator_info['values']
            
            # Build clean, structured text output
            result = f"Indicator: {indicator_info['name']} (ID: {parameters.indicator_id})\n"
            result += f"Data points: {len(values)}\n"
            result += f"Period: {start_date_str} to {end_date_str}\n"
            result += f"Aggregation: {parameters.time_agg} per {parameters.time_trunc}\n\n"
            
            # Add summary statistics
            if values:
                numeric_values = [float(v['value']) for v in values if v['value'] is not None]
                if numeric_values:
                    result += f"Summary: min={min(numeric_values):.2f}, max={max(numeric_values):.2f}, avg={sum(numeric_values)/len(numeric_values):.2f}\n\n"
            
            # Show sample data points
            result += "Data:\n"
            sample_values = values[:self.MAX_SAMPLE_VALUES]
            for value in sample_values:
                # Use the cleaner datetime format from API
                dt = value.get('datetime', 'Unknown')
                val = value.get('value', 'N/A')
                geo = value.get('geo_name', '')
                
                result += f"{dt}: {val}"
                if geo:
                    result += f" ({geo})"
                result += "\n"
            
            if len(values) > self.MAX_SAMPLE_VALUES:
                result += f"\n... and {len(values) - self.MAX_SAMPLE_VALUES} more data points"
                
            return result
        except Exception as e:
            logger.error(f"Failed to get indicator data: {e}")
            return f"Failed to get indicator data: {e}"

    async def close(self) -> None:
        """Close the session when done."""
        if self.session and not self.session.closed:
            await self.session.close()