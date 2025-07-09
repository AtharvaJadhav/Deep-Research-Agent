import os
import logging
import asyncio
from typing import List, Dict, Any, Optional
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, CallToolResult, TextContent
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("web_search_server")

SERPER_API_KEY = os.getenv("SERPER_API_KEY")
SERPER_API_URL = "https://google.serper.dev/search"

# MCP server setup
server = Server("web-search-server")

@server.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(
            name="web_search",
            description="Search the web using Serper API. Returns structured results.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."},
                    "max_results": {"type": "integer", "description": "Number of results to return.", "default": 5}
                },
                "required": ["query"]
            }
        )
    ]

def call_serper_api(query: str, max_results: int) -> Dict[str, Any]:
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    payload = {"q": query, "num": max_results}
    try:
        response = requests.post(SERPER_API_URL, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        results = []
        for item in data.get("organic", [])[:max_results]:
            results.append({
                "title": item.get("title", "No title"),
                "url": item.get("link", "No url"),
                "snippet": item.get("snippet", "")
            })
        return {
            "results": results,
            "query_used": query,
            "source": "serper",
            "total_results": len(results)
        }
    except Exception as e:
        logger.error(f"Serper API error: {e}")
        raise

def mock_search(query: str, max_results: int) -> Dict[str, Any]:
    results = [
        {
            "title": f"Mock result {i+1} for '{query}'",
            "url": f"https://example.com/{query.replace(' ', '_')}/{i+1}",
            "snippet": f"This is a mock search result {i+1} for query '{query}'."
        }
        for i in range(max_results)
    ]
    return {
        "results": results,
        "query_used": query,
        "source": "mock",
        "total_results": len(results)
    }

@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
    if name != "web_search":
        return CallToolResult(
            content=[TextContent(type="text", text=f"Unknown tool: {name}")],
            isError=True
        )
    query = arguments.get("query")
    max_results = arguments.get("max_results", 5)
    if not isinstance(max_results, int):
        try:
            max_results = int(max_results)
        except Exception:
            max_results = 5
    if not query or not isinstance(query, str):
        return CallToolResult(
            content=[TextContent(type="text", text="Missing or invalid 'query' parameter.")],
            isError=True
        )
    try:
        if SERPER_API_KEY:
            try:
                result = call_serper_api(query, max_results)
            except Exception as e:
                logger.warning(f"Falling back to mock search due to Serper error: {e}")
                result = mock_search(query, max_results)
        else:
            logger.info("SERPER_API_KEY not found, using mock search.")
            result = mock_search(query, max_results)
        return CallToolResult(
            content=[TextContent(type="text", text=str(result))],
            isError=False
        )
    except Exception as e:
        logger.error(f"Web search tool error: {e}")
        return CallToolResult(
            content=[TextContent(type="text", text=f"Web search error: {e}")],
            isError=True
        )

async def main():
    logger.info("Starting MCP Web Search Server...")
    async with stdio_server() as (read_stream, write_stream):
        from mcp.types import ServerCapabilities
        
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="web-search-server",
                server_version="1.0.0",
                capabilities=ServerCapabilities(),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
