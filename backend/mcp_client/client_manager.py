import asyncio
import logging
from typing import Dict, Any, Optional, List
from mcp.client import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.tcp import tcp_client
from mcp.types import CallToolResult

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_client_manager")

class MCPClientManager:
    """Manages connections to multiple MCP servers and provides unified interface."""
    
    def __init__(self):
        self.clients: Dict[str, ClientSession] = {}
        self.server_configs = {
            "web_search": {
                "name": "web-search-server",
                "port": 8001,
                "host": "localhost"
            },
            "file_operations": {
                "name": "file-operations-server", 
                "port": 8002,
                "host": "localhost"
            },
            "weather": {
                "name": "weather-server",
                "port": 8003,
                "host": "localhost"
            }
        }
        self.is_initialized = False
        self.max_retries = 3
        self.retry_delay = 1.0  # seconds
    
    async def startup(self) -> bool:
        """Initialize connections to all MCP servers."""
        logger.info("Starting MCP Client Manager...")
        
        try:
            for server_name, config in self.server_configs.items():
                await self._connect_to_server(server_name, config)
            
            # Verify all connections
            health_status = await self.health_check()
            if all(health_status.values()):
                self.is_initialized = True
                logger.info("MCP Client Manager initialized successfully")
                return True
            else:
                logger.error("Some servers failed health check during startup")
                return False
                
        except Exception as e:
            logger.error(f"Failed to initialize MCP Client Manager: {e}")
            return False
    
    async def _connect_to_server(self, server_name: str, config: Dict[str, Any]) -> None:
        """Connect to a specific MCP server with retry logic."""
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Connecting to {server_name} server (attempt {attempt + 1}/{self.max_retries})")
                
                # Create TCP client connection
                client = await tcp_client(
                    host=config["host"],
                    port=config["port"]
                )
                
                # Initialize the client session
                await client.initialize(
                    server_name=config["name"],
                    server_version="1.0.0",
                    client_name="mcp-client-manager",
                    client_version="1.0.0"
                )
                
                self.clients[server_name] = client
                logger.info(f"Successfully connected to {server_name} server")
                return
                
            except Exception as e:
                logger.warning(f"Failed to connect to {server_name} server (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.error(f"Failed to connect to {server_name} server after {self.max_retries} attempts")
                    raise
    
    async def shutdown(self) -> None:
        """Cleanup all MCP server connections."""
        logger.info("Shutting down MCP Client Manager...")
        
        for server_name, client in self.clients.items():
            try:
                await client.close()
                logger.info(f"Closed connection to {server_name} server")
            except Exception as e:
                logger.error(f"Error closing connection to {server_name} server: {e}")
        
        self.clients.clear()
        self.is_initialized = False
        logger.info("MCP Client Manager shutdown complete")
    
    async def health_check(self) -> Dict[str, bool]:
        """Check health status of all MCP servers."""
        health_status = {}
        
        for server_name in self.server_configs.keys():
            try:
                if server_name in self.clients:
                    # Try to list tools as a health check
                    tools = await self.clients[server_name].list_tools()
                    health_status[server_name] = len(tools) > 0
                    logger.debug(f"Health check for {server_name}: OK")
                else:
                    health_status[server_name] = False
                    logger.warning(f"Health check for {server_name}: No connection")
            except Exception as e:
                health_status[server_name] = False
                logger.error(f"Health check for {server_name} failed: {e}")
        
        return health_status
    
    async def _call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> CallToolResult:
        """Call a tool on a specific MCP server with error handling."""
        if not self.is_initialized:
            raise RuntimeError("MCP Client Manager not initialized. Call startup() first.")
        
        if server_name not in self.clients:
            raise RuntimeError(f"No connection to {server_name} server")
        
        try:
            result = await self.clients[server_name].call_tool(tool_name, arguments)
            return result
        except Exception as e:
            logger.error(f"Error calling {tool_name} on {server_name} server: {e}")
            raise
    
    # Web Search Methods
    async def search_web(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """Search the web using the web search MCP server."""
        try:
            result = await self._call_tool("web_search", "web_search", {
                "query": query,
                "max_results": max_results
            })
            
            if result.isError:
                raise RuntimeError(f"Web search failed: {result.content[0].text}")
            
            # Parse the result string back to dict
            import ast
            return ast.literal_eval(result.content[0].text)
            
        except Exception as e:
            logger.error(f"Web search error: {e}")
            raise
    
    # File Operations Methods
    async def write_file(self, filename: str, content: str) -> Dict[str, Any]:
        """Write content to a file using the file operations MCP server."""
        try:
            result = await self._call_tool("file_operations", "write_file", {
                "filename": filename,
                "content": content
            })
            
            if result.isError:
                raise RuntimeError(f"File write failed: {result.content[0].text}")
            
            import ast
            return ast.literal_eval(result.content[0].text)
            
        except Exception as e:
            logger.error(f"File write error: {e}")
            raise
    
    async def read_file(self, filename: str) -> Dict[str, Any]:
        """Read content from a file using the file operations MCP server."""
        try:
            result = await self._call_tool("file_operations", "read_file", {
                "filename": filename
            })
            
            if result.isError:
                raise RuntimeError(f"File read failed: {result.content[0].text}")
            
            import ast
            return ast.literal_eval(result.content[0].text)
            
        except Exception as e:
            logger.error(f"File read error: {e}")
            raise
    
    async def list_files(self, directory: str = "research_output") -> Dict[str, Any]:
        """List files in a directory using the file operations MCP server."""
        try:
            result = await self._call_tool("file_operations", "list_files", {
                "directory": directory
            })
            
            if result.isError:
                raise RuntimeError(f"File listing failed: {result.content[0].text}")
            
            import ast
            return ast.literal_eval(result.content[0].text)
            
        except Exception as e:
            logger.error(f"File listing error: {e}")
            raise
    
    # Weather Methods
    async def get_weather(self, location: str, units: str = "metric") -> Dict[str, Any]:
        """Get weather information using the weather MCP server."""
        try:
            result = await self._call_tool("weather", "get_weather", {
                "location": location,
                "units": units
            })
            
            if result.isError:
                raise RuntimeError(f"Weather lookup failed: {result.content[0].text}")
            
            import ast
            return ast.literal_eval(result.content[0].text)
            
        except Exception as e:
            logger.error(f"Weather lookup error: {e}")
            raise
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.startup()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.shutdown()

# Global instance for easy access
_client_manager: Optional[MCPClientManager] = None

async def get_client_manager() -> MCPClientManager:
    """Get or create the global MCP client manager instance."""
    global _client_manager
    if _client_manager is None:
        _client_manager = MCPClientManager()
        await _client_manager.startup()
    return _client_manager

async def shutdown_client_manager():
    """Shutdown the global MCP client manager instance."""
    global _client_manager
    if _client_manager is not None:
        await _client_manager.shutdown()
        _client_manager = None
