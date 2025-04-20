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
    MAX_SAMPLE_VALUES = 10

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

            matching_indicators = [
                {
                    'id': ind['id'],
                    'name': ind['name'],
                    'short_name': ind['short_name'],
                    'description': ind.get('description', 'No description available'),
                }
                for ind in indicators
                if (pattern.search(ind['name']) or 
                    pattern.search(ind['short_name']) or
                    pattern.search(ind.get('description', '')))
            ]

            if not matching_indicators:
                return "No indicators found matching your query."

            result = f"Found {len(matching_indicators)} matching indicators:\n\n"
            max_indicators_with_descriptions = 30
            if len(matching_indicators) > max_indicators_with_descriptions:
                result += (
                    f"Note: The description for each indicator is not shown since there are more than {max_indicators_with_descriptions} matches. "
                    f"If you want to see the description for each indicator, please refine your search to get less than {max_indicators_with_descriptions} matches.\n\n"
                )
            
            for ind in matching_indicators:
                result += (
                    f"ID: {ind['id']}\n"
                    f"Name: {ind['name']}\n"
                    f"Short name: {ind['short_name']}\n"
                )
                if len(matching_indicators) < max_indicators_with_descriptions:
                    result += f"Description: {ind['description']}\n\n"
                else:
                    result += "\n"

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

            values = indicator_data['indicator']['values']
            result = (
                f"Data for indicator {parameters.indicator_id}:\n"
                f"Name: {indicator_data['indicator']['name']}\n"
                f"Values: {len(values)} data points\n\n"
            )

            sample_values = values[:self.MAX_SAMPLE_VALUES]
            for value in sample_values:
                result += f"Datetime: {value['datetime']}, Value: {value['value']}, Geo name: {value['geo_name']}\n"
            
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