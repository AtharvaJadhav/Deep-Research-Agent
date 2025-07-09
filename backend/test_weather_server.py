#!/usr/bin/env python3
"""
Simple test script to manually test the weather server MCP communication.
"""

import asyncio
import subprocess
import json
import sys
import os

async def test_weather_server():
    """Test the weather server by manually sending MCP protocol messages."""
    
    # Start the weather server as a subprocess
    server_path = os.path.join(os.path.dirname(__file__), "mcp_servers", "weather_server.py")
    print(f"Starting weather server: {server_path}")
    
    try:
        # Start the server process
        process = await asyncio.create_subprocess_exec(
            sys.executable, server_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        print(f"Weather server started with PID: {process.pid}")
        
        # Send initialization message
        init_message = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        }
        
        print(f"Sending init message: {json.dumps(init_message)}")
        await process.stdin.write((json.dumps(init_message) + "\n").encode())
        await process.stdin.drain()
        
        # Wait for response
        response = await asyncio.wait_for(process.stdout.readline(), timeout=10.0)
        print(f"Received response: {response.decode().strip()}")
        
        # Send list tools request
        list_tools_message = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list"
        }
        
        print(f"Sending list tools message: {json.dumps(list_tools_message)}")
        await process.stdin.write((json.dumps(list_tools_message) + "\n").encode())
        await process.stdin.drain()
        
        # Wait for response
        response = await asyncio.wait_for(process.stdout.readline(), timeout=10.0)
        print(f"Received response: {response.decode().strip()}")
        
        # Send call tool request
        call_tool_message = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "get_weather",
                "arguments": {
                    "location": "New York",
                    "units": "metric"
                }
            }
        }
        
        print(f"Sending call tool message: {json.dumps(call_tool_message)}")
        await process.stdin.write((json.dumps(call_tool_message) + "\n").encode())
        await process.stdin.drain()
        
        # Wait for response
        response = await asyncio.wait_for(process.stdout.readline(), timeout=10.0)
        print(f"Received response: {response.decode().strip()}")
        
        # Terminate the process
        process.terminate()
        await process.wait()
        
        print("Test completed successfully!")
        
    except Exception as e:
        print(f"Test failed: {e}")
        if 'process' in locals():
            process.terminate()
            await process.wait()

if __name__ == "__main__":
    asyncio.run(test_weather_server()) 