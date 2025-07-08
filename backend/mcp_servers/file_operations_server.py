import os
import logging
import asyncio
from typing import List, Dict, Any, Optional
from pathlib import Path
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.tcp import tcp_server
from mcp.types import Tool, CallToolResult, TextContent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("file_operations_server")

# Default directory for research output
DEFAULT_OUTPUT_DIR = "research_output"

# MCP server setup
server = Server("file-operations-server")

def secure_path(base_dir: str, filename: str) -> Path:
    """Create a secure path within the base directory, preventing path traversal."""
    base_path = Path(base_dir).resolve()
    file_path = (base_path / filename).resolve()
    
    # Ensure the file path is within the base directory
    if not str(file_path).startswith(str(base_path)):
        raise ValueError("Path traversal detected")
    
    return file_path

def ensure_directory(directory: str) -> Path:
    """Ensure the directory exists, create if it doesn't."""
    dir_path = Path(directory)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path

@server.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(
            name="write_file",
            description="Write content to a markdown file in the research output directory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "The filename to write to."},
                    "content": {"type": "string", "description": "The content to write to the file."}
                },
                "required": ["filename", "content"]
            }
        ),
        Tool(
            name="read_file",
            description="Read content from an existing file in the research output directory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "The filename to read from."}
                },
                "required": ["filename"]
            }
        ),
        Tool(
            name="list_files",
            description="List files in the research output directory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "Directory to list files from.", "default": "research_output"}
                }
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
    try:
        if name == "write_file":
            filename = arguments.get("filename")
            content = arguments.get("content")
            
            if not filename or not isinstance(filename, str):
                return CallToolResult(
                    content=[TextContent(type="text", text="Missing or invalid 'filename' parameter.")],
                    isError=True
                )
            
            if not content or not isinstance(content, str):
                return CallToolResult(
                    content=[TextContent(type="text", text="Missing or invalid 'content' parameter.")],
                    isError=True
                )
            
            try:
                # Ensure the output directory exists
                output_dir = ensure_directory(DEFAULT_OUTPUT_DIR)
                
                # Create secure file path
                file_path = secure_path(DEFAULT_OUTPUT_DIR, filename)
                
                # Ensure the file has .md extension
                if not file_path.suffix:
                    file_path = file_path.with_suffix('.md')
                
                # Write the file
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                result = {
                    "success": True,
                    "file_path": str(file_path),
                    "file_size": len(content),
                    "message": f"Successfully wrote {len(content)} characters to {file_path}"
                }
                
                logger.info(f"File written: {file_path}")
                return CallToolResult(
                    content=[TextContent(type="text", text=str(result))],
                    isError=False
                )
                
            except ValueError as e:
                logger.error(f"Path validation error: {e}")
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Path validation error: {e}")],
                    isError=True
                )
            except Exception as e:
                logger.error(f"File write error: {e}")
                return CallToolResult(
                    content=[TextContent(type="text", text=f"File write error: {e}")],
                    isError=True
                )
        
        elif name == "read_file":
            filename = arguments.get("filename")
            
            if not filename or not isinstance(filename, str):
                return CallToolResult(
                    content=[TextContent(type="text", text="Missing or invalid 'filename' parameter.")],
                    isError=True
                )
            
            try:
                # Create secure file path
                file_path = secure_path(DEFAULT_OUTPUT_DIR, filename)
                
                # Check if file exists
                if not file_path.exists():
                    return CallToolResult(
                        content=[TextContent(type="text", text=f"File not found: {filename}")],
                        isError=True
                    )
                
                # Read the file
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                result = {
                    "success": True,
                    "file_path": str(file_path),
                    "content": content,
                    "file_size": len(content),
                    "message": f"Successfully read {len(content)} characters from {file_path}"
                }
                
                logger.info(f"File read: {file_path}")
                return CallToolResult(
                    content=[TextContent(type="text", text=str(result))],
                    isError=False
                )
                
            except ValueError as e:
                logger.error(f"Path validation error: {e}")
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Path validation error: {e}")],
                    isError=True
                )
            except Exception as e:
                logger.error(f"File read error: {e}")
                return CallToolResult(
                    content=[TextContent(type="text", text=f"File read error: {e}")],
                    isError=True
                )
        
        elif name == "list_files":
            directory = arguments.get("directory", DEFAULT_OUTPUT_DIR)
            
            if not isinstance(directory, str):
                directory = DEFAULT_OUTPUT_DIR
            
            try:
                # Ensure the directory exists
                dir_path = ensure_directory(directory)
                
                # List files in the directory
                files = []
                for file_path in dir_path.iterdir():
                    if file_path.is_file():
                        files.append({
                            "name": file_path.name,
                            "size": file_path.stat().st_size,
                            "modified": file_path.stat().st_mtime
                        })
                
                result = {
                    "success": True,
                    "directory": str(dir_path),
                    "files": files,
                    "total_files": len(files),
                    "message": f"Found {len(files)} files in {dir_path}"
                }
                
                logger.info(f"Files listed: {dir_path}")
                return CallToolResult(
                    content=[TextContent(type="text", text=str(result))],
                    isError=False
                )
                
            except Exception as e:
                logger.error(f"File listing error: {e}")
                return CallToolResult(
                    content=[TextContent(type="text", text=f"File listing error: {e}")],
                    isError=True
                )
        
        else:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Unknown tool: {name}")],
                isError=True
            )
    
    except Exception as e:
        logger.error(f"Tool call error: {e}")
        return CallToolResult(
            content=[TextContent(type="text", text=f"Tool call error: {e}")],
            isError=True
        )

async def main():
    logger.info("Starting MCP File Operations Server on port 8002...")
    # Ensure the default output directory exists
    ensure_directory(DEFAULT_OUTPUT_DIR)
    
    async with tcp_server(port=8002) as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="file-operations-server",
                server_version="1.0.0",
                capabilities=server.get_capabilities(),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
