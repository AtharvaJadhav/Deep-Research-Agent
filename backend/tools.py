import aiohttp
import asyncio
import os
import json
import aiofiles
from typing import Dict, Any
from pathlib import Path
import requests

async def search_web(query: str) -> str:
    """Search the web using Serper API or fallback to mock results."""
    try:
        # TODO: Replace with your actual Serper API key
        serper_api_key = os.getenv("SERPER_API_KEY", "your-serper-api-key-here")
        
        if serper_api_key == "your-serper-api-key-here":
            # Fallback to mock results if no API key
            await asyncio.sleep(1)  # Simulate API delay
            
            results = [
                {
                    "title": f"Latest developments in {query}",
                    "link": "https://example.com/article1",
                    "snippet": f"Comprehensive coverage of {query} with recent updates and expert analysis from leading researchers and industry experts."
                },
                {
                    "title": f"{query} - Breaking News and Updates",
                    "link": "https://example.com/news",
                    "snippet": f"Latest news and developments related to {query} from trusted sources, including recent breakthroughs and market trends."
                },
                {
                    "title": f"Complete Guide to {query}",
                    "link": "https://example.com/guide",
                    "snippet": f"In-depth guide covering everything you need to know about {query}, including best practices and future outlook."
                }
            ]
            
            formatted_results = []
            for i, result in enumerate(results, 1):
                formatted_results.append(
                    f"{i}. **{result['title']}**\n"
                    f"   URL: {result['link']}\n"
                    f"   Summary: {result['snippet']}\n"
                )
            
            return "\n".join(formatted_results)
        
        # Real Serper API implementation
        url = "https://google.serper.dev/search"
        payload = json.dumps({
            "q": query,
            "num": 5
        })
        headers = {
            'X-API-KEY': serper_api_key,
            'Content-Type': 'application/json'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    results = []
                    if 'organic' in data:
                        for i, result in enumerate(data['organic'][:5], 1):
                            results.append(
                                f"{i}. **{result.get('title', 'No title')}**\n"
                                f"   URL: {result.get('link', 'No URL')}\n"
                                f"   Summary: {result.get('snippet', 'No summary available')}\n"
                            )
                    
                    return "\n".join(results) if results else "No search results found."
                else:
                    return f"Search API error: {response.status}"
        
    except Exception as e:
        return f"Search error: {str(e)}"

async def write_file(filename: str, content: str) -> str:
    """Write content to a file in the reports directory."""
    try:
        # Create reports directory if it doesn't exist
        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)
        
        # Ensure filename has .md extension
        if not filename.endswith('.md'):
            filename += '.md'
        
        file_path = reports_dir / filename
        
        # Write content to file asynchronously
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(content)
        
        return f"Successfully wrote content to {file_path}. File size: {len(content)} characters."
        
    except Exception as e:
        return f"File write error: {str(e)}"

async def get_weather(location: str) -> str:
    """Get weather information for a location using OpenWeatherMap API."""
    try:
        # TODO: Replace with your actual OpenWeatherMap API key
        weather_api_key = os.getenv("OPENWEATHER_API_KEY", "your-openweather-api-key-here")
        
        if weather_api_key == "your-openweather-api-key-here":
            # Fallback to mock weather data if no API key
            await asyncio.sleep(0.5)  # Simulate API delay
            
            import random
            weather_conditions = ["sunny", "cloudy", "rainy", "partly cloudy", "windy", "foggy"]
            temperatures = list(range(15, 35))
            
            condition = random.choice(weather_conditions)
            temp = random.choice(temperatures)
            humidity = random.randint(30, 80)
            wind_speed = random.randint(5, 25)
            
            weather_data = {
                "location": location,
                "temperature": f"{temp}°C",
                "condition": condition,
                "humidity": f"{humidity}%",
                "wind_speed": f"{wind_speed} km/h",
                "description": f"Current weather in {location}: {condition} with temperature of {temp}°C, humidity at {humidity}%, and wind speed of {wind_speed} km/h."
            }
            
            return json.dumps(weather_data, indent=2)
        
        # Real OpenWeatherMap API implementation
        base_url = "http://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": location,
            "appid": weather_api_key,
            "units": "metric"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(base_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    weather_info = {
                        "location": data["name"],
                        "temperature": f"{data['main']['temp']}°C",
                        "condition": data["weather"][0]["description"],
                        "humidity": f"{data['main']['humidity']}%",
                        "wind_speed": f"{data['wind']['speed']} m/s",
                        "description": f"Current weather in {data['name']}: {data['weather'][0]['description']} with temperature of {data['main']['temp']}°C, humidity at {data['main']['humidity']}%, and wind speed of {data['wind']['speed']} m/s."
                    }
                    
                    return json.dumps(weather_info, indent=2)
                else:
                    return f"Weather API error: {response.status}"
        
    except Exception as e:
        return f"Weather API error: {str(e)}"

async def send_email(to: str, subject: str, body: str) -> str:
    """Send an email."""
    try:
        # This is a mock implementation. In a real application, you'd integrate with an email service.
        print(f"--- MOCK EMAIL ---")
        print(f"To: {to}")
        print(f"Subject: {subject}")
        print(f"Body: {body}")
        print(f"------------------")
        await asyncio.sleep(1) # Simulate network delay
        return f"Email successfully sent to {to}."
    except Exception as e:
        return f"Email sending error: {str(e)}"

async def call_tool(tool_name: str, args: Dict[str, Any]) -> str:
    """Execute a tool with given arguments."""
    if tool_name == "search":
        return await search_web(args.get("query", ""))
    elif tool_name == "write_file":
        return await write_file(args.get("filename", ""), args.get("content", ""))
    elif tool_name == "get_weather":
        return await get_weather(args.get("location", ""))
    elif tool_name == "send_email":
        return await send_email(args.get("to", ""), args.get("subject", ""), args.get("body", ""))
    else:
        return f"Unknown tool: {tool_name}"
