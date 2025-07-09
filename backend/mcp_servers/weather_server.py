import os
import logging
import asyncio
import random
from typing import List, Dict, Any, Optional
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, CallToolResult, TextContent
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("weather_server")

# OpenWeatherMap API configuration
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
OPENWEATHER_API_URL = "http://api.openweathermap.org/data/2.5/weather"

# MCP server setup
server = Server("weather-server")

def call_openweather_api(location: str, units: str) -> Dict[str, Any]:
    """Call OpenWeatherMap API to get weather data."""
    params = {
        "q": location,
        "appid": OPENWEATHER_API_KEY,
        "units": units
    }
    
    try:
        response = requests.get(OPENWEATHER_API_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Extract weather information
        weather_info = {
            "temperature": data["main"]["temp"],
            "description": data["weather"][0]["description"],
            "humidity": data["main"]["humidity"],
            "location": data["name"],
            "country": data.get("sys", {}).get("country", ""),
            "wind_speed": data.get("wind", {}).get("speed", 0),
            "pressure": data.get("main", {}).get("pressure", 0),
            "source": "openweather",
            "units": units
        }
        
        # Add temperature unit suffix
        if units == "metric":
            weather_info["temperature_unit"] = "°C"
            weather_info["wind_speed_unit"] = "m/s"
        elif units == "imperial":
            weather_info["temperature_unit"] = "°F"
            weather_info["wind_speed_unit"] = "mph"
        else:  # kelvin
            weather_info["temperature_unit"] = "K"
            weather_info["wind_speed_unit"] = "m/s"
        
        return weather_info
        
    except Exception as e:
        logger.error(f"OpenWeatherMap API error: {e}")
        raise

def mock_weather_data(location: str, units: str) -> Dict[str, Any]:
    """Generate mock weather data for testing."""
    # Generate realistic mock data
    weather_conditions = [
        "clear sky", "few clouds", "scattered clouds", "broken clouds",
        "shower rain", "rain", "thunderstorm", "snow", "mist"
    ]
    
    # Temperature ranges based on units
    if units == "metric":
        temp_range = (-10, 35)
        temp_unit = "°C"
        wind_unit = "m/s"
    elif units == "imperial":
        temp_range = (14, 95)
        temp_unit = "°F"
        wind_unit = "mph"
    else:  # kelvin
        temp_range = (263, 308)
        temp_unit = "K"
        wind_unit = "m/s"
    
    temperature = round(random.uniform(*temp_range), 1)
    humidity = random.randint(30, 90)
    wind_speed = round(random.uniform(0, 25), 1)
    pressure = random.randint(980, 1030)
    
    return {
        "temperature": temperature,
        "description": random.choice(weather_conditions),
        "humidity": humidity,
        "location": location,
        "country": "Mock",
        "wind_speed": wind_speed,
        "pressure": pressure,
        "source": "mock",
        "units": units,
        "temperature_unit": temp_unit,
        "wind_speed_unit": wind_unit
    }

@server.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(
            name="get_weather",
            description="Get current weather information for a location using OpenWeatherMap API.",
            inputSchema={
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name or coordinates (e.g., 'London' or '40.7128,-74.0060')."},
                    "units": {"type": "string", "description": "Temperature units: 'metric' (Celsius), 'imperial' (Fahrenheit), or 'kelvin'.", "default": "metric"}
                },
                "required": ["location"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
    if name != "get_weather":
        return CallToolResult(
            content=[TextContent(type="text", text=f"Unknown tool: {name}")],
            isError=True
        )
    
    location = arguments.get("location")
    units = arguments.get("units", "metric")
    
    # Validate location parameter
    if not location or not isinstance(location, str):
        return CallToolResult(
            content=[TextContent(type="text", text="Missing or invalid 'location' parameter.")],
            isError=True
        )
    
    # Validate units parameter
    valid_units = ["metric", "imperial", "kelvin"]
    if units not in valid_units:
        units = "metric"
        logger.warning(f"Invalid units '{units}', defaulting to 'metric'")
    
    try:
        if OPENWEATHER_API_KEY:
            try:
                result = call_openweather_api(location, units)
                logger.info(f"Weather data retrieved for {location} using OpenWeatherMap API")
            except Exception as e:
                logger.warning(f"Falling back to mock weather data due to API error: {e}")
                result = mock_weather_data(location, units)
        else:
            logger.info("OPENWEATHER_API_KEY not found, using mock weather data")
            result = mock_weather_data(location, units)
        
        # Format the result for better readability
        formatted_result = {
            "success": True,
            "weather": result,
            "message": f"Weather data for {result['location']}: {result['temperature']}{result['temperature_unit']}, {result['description']}"
        }
        
        return CallToolResult(
            content=[TextContent(type="text", text=str(formatted_result))],
            isError=False
        )
        
    except Exception as e:
        logger.error(f"Weather tool error: {e}")
        return CallToolResult(
            content=[TextContent(type="text", text=f"Weather tool error: {e}")],
            isError=True
        )

async def main():
    logger.info("Starting MCP Weather Server...")
    
    # Log API key status
    if OPENWEATHER_API_KEY:
        logger.info("OpenWeatherMap API key found")
    else:
        logger.info("No OpenWeatherMap API key found, will use mock data")
    
    async with stdio_server() as (read_stream, write_stream):
        from mcp.types import ServerCapabilities
        
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="weather-server",
                server_version="1.0.0",
                capabilities=ServerCapabilities(),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
