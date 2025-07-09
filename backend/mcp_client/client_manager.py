import asyncio
import logging
import os
import sys
from typing import Dict, Any, Optional, List
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.types import CallToolResult

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_client_manager")

class MCPClientManager:
    """Manages MCP client connections for tool calling."""
    
    def __init__(self):
        # Get the absolute path to the backend directory
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Get the Python executable path
        python_executable = sys.executable
        
        self.server_configs = {
            "web_search": {
                "name": "web-search-server",
                "command": python_executable,
                "args": [os.path.join(backend_dir, "mcp_servers", "web_search_server.py")]
            },
            "file_operations": {
                "name": "file-operations-server", 
                "command": python_executable,
                "args": [os.path.join(backend_dir, "mcp_servers", "file_operations_server.py")]
            },
            "weather": {
                "name": "weather-server",
                "command": python_executable,
                "args": [os.path.join(backend_dir, "mcp_servers", "weather_server.py")]
            }
        }
        
        self.max_retries = 3
        self.retry_delay = 1  # seconds
    
    async def _call_mcp_tool(self, server_name: str, tool_name: str, args: Dict[str, Any]) -> str:
        """Call a specific MCP tool with retry logic."""
        config = self.server_configs.get(server_name)
        if not config:
            raise ValueError(f"Unknown server: {server_name}")
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Calling {tool_name} on {server_name} server (attempt {attempt + 1}/{self.max_retries})")
                logger.info(f"Command: {config['command']} {' '.join(config['args'])}")
                
                # Create stdio client connection
                server_params = StdioServerParameters(
                    command=config["command"],
                    args=config["args"]
                )
                
                logger.info(f"Created stdio server params: {server_params}")
                
                # Use async context manager for stdio client
                logger.info("About to create stdio client connection...")
                try:
                    async with stdio_client(server_params) as (read_stream, write_stream):
                        logger.info("Stdio streams established")
                        
                        # Create client session from streams
                        client = ClientSession(read_stream, write_stream)
                        logger.info("Client session created from streams")
                        
                        # Initialize the client session
                        logger.info("Initializing client session...")
                        try:
                            await client.initialize()
                            logger.info("Client session initialized successfully")
                        except Exception as init_error:
                            logger.error(f"Client initialization failed: {init_error}")
                            logger.error(f"Exception type: {type(init_error)}")
                            logger.error(f"Exception details: {str(init_error)}")
                            raise
                        
                        # List available tools
                        logger.info("Listing available tools...")
                        tools_response = await client.list_tools()
                        tools = tools_response.tools
                        logger.info(f"Available tools: {[t.name for t in tools]}")
                        
                        # Find the requested tool
                        tool = None
                        for t in tools:
                            if t.name == tool_name:
                                tool = t
                                break
                        
                        if not tool:
                            raise ValueError(f"Tool {tool_name} not found on {server_name} server")
                        
                        logger.info(f"Found tool: {tool.name}")
                        
                        # Call the tool
                        logger.info(f"Calling tool {tool_name} with args: {args}")
                        result = await client.call_tool(tool_name, args)
                        logger.info(f"Tool call result: {result}")
                        
                        if result.isError:
                            raise RuntimeError(f"Tool {tool_name} returned error: {result.content}")
                        
                        # Extract text content
                        content = ""
                        logger.info(f"Extracting content from {len(result.content)} items")
                        for i, item in enumerate(result.content):
                            logger.info(f"Content item {i}: {item}")
                            if hasattr(item, 'text'):
                                content += item.text
                                logger.info(f"Added text: {item.text}")
                        
                        logger.info(f"Final content: {content}")
                        logger.info(f"Successfully called {tool_name} on {server_name} server")
                        return content
                        
                except Exception as stdio_error:
                    logger.error(f"Stdio client connection failed: {stdio_error}")
                    raise
                    
            except Exception as e:
                logger.warning(f"Failed to call {tool_name} on {server_name} server (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.error(f"Failed to call {tool_name} on {server_name} server after {self.max_retries} attempts")
                    raise
    
    async def search_web(self, query: str, max_results: int = 5) -> str:
        """Search the web using MCP web search server."""
        return await self._call_mcp_tool("web_search", "web_search", {
            "query": query,
            "max_results": max_results
        })
    
    async def write_file(self, filename: str, content: str) -> str:
        """Write content to a file using MCP file operations server."""
        return await self._call_mcp_tool("file_operations", "write_file", {
            "filename": filename,
            "content": content
        })
    
    async def read_file(self, filename: str) -> str:
        """Read content from a file using MCP file operations server."""
        return await self._call_mcp_tool("file_operations", "read_file", {
            "filename": filename
        })
    
    async def list_files(self, directory: str = "research_output") -> str:
        """List files in a directory using MCP file operations server."""
        return await self._call_mcp_tool("file_operations", "list_files", {
            "directory": directory
        })
    
    async def get_weather(self, location: str, units: str = "metric") -> str:
        """Get weather information using MCP weather server."""
        return await self._call_mcp_tool("weather", "get_weather", {
            "location": location,
            "units": units
        })
    
    async def health_check(self) -> Dict[str, bool]:
        """Check health of all MCP servers."""
        health_status = {}
        
        for server_name in self.server_configs.keys():
            try:
                # Try a simple tool call to test connectivity
                if server_name == "web_search":
                    await self.search_web("test", 1)
                elif server_name == "file_operations":
                    await self.list_files(".")
                elif server_name == "weather":
                    await self.get_weather("test")
                
                health_status[server_name] = True
                logger.info(f"Health check passed for {server_name} server")
                
            except Exception as e:
                health_status[server_name] = False
                logger.warning(f"Health check failed for {server_name} server: {e}")
        
        return health_status

# Global instance
_mcp_manager: Optional[MCPClientManager] = None

async def get_client_manager() -> MCPClientManager:
    """Get the global MCP client manager instance."""
    global _mcp_manager
    if _mcp_manager is None:
        logger.info("Starting MCP Client Manager...")
        _mcp_manager = MCPClientManager()
        logger.info("MCP Client Manager started successfully")
    return _mcp_manager

async def shutdown_client_manager():
    """Shutdown the global MCP client manager."""
    global _mcp_manager
    if _mcp_manager:
        logger.info("Shutting down MCP Client Manager...")
        _mcp_manager = None
        logger.info("MCP Client Manager shutdown complete")
