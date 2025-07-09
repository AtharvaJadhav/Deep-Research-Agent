#!/usr/bin/env python3
"""
MCP Servers Orchestrator
Starts all MCP servers with health checks and process management.
"""

import asyncio
import logging
import os
import signal
import subprocess
import sys
import time
from typing import Dict, List, Optional
import socket
import json
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('mcp_servers.log')
    ]
)
logger = logging.getLogger("mcp_orchestrator")

class MCPServerManager:
    """Manages MCP server processes with health checks and graceful shutdown."""
    
    def __init__(self):
        self.servers = {
            "web_search": {
                "script": "mcp_servers/web_search_server.py",
                "name": "Web Search Server",
                "process": None,
                "pid": None
            },
            "file_operations": {
                "script": "mcp_servers/file_operations_server.py", 
                "name": "File Operations Server",
                "process": None,
                "pid": None
            },
            "weather": {
                "script": "mcp_servers/weather_server.py",
                "name": "Weather Server", 
                "process": None,
                "pid": None
            }
        }
        self.running = False
        self.startup_timeout = 30  # seconds per server
        
    def check_server_health(self, process) -> bool:
        """Check if a server process is healthy."""
        try:
            return process.poll() is None  # Process is running if poll() returns None
        except Exception:
            return False
    
    async def wait_for_server(self, server_name: str, process, timeout: int) -> bool:
        """Wait for a server to become ready."""
        logger.info(f"Waiting for {server_name} to be ready...")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.check_server_health(process):
                logger.info(f"✅ {server_name} is ready")
                return True
            await asyncio.sleep(1)
        
        logger.error(f"❌ {server_name} failed to start within {timeout} seconds")
        return False
    
    def start_server(self, server_name: str, server_config: Dict) -> bool:
        """Start a single MCP server process."""
        script_path = server_config["script"]
        name = server_config["name"]
        
        # Check if script exists
        if not Path(script_path).exists():
            logger.error(f"❌ Script not found: {script_path}")
            return False
        
        try:
            logger.info(f"🚀 Starting {name}...")
            
            # Start the server process
            process = subprocess.Popen(
                [sys.executable, script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            server_config["process"] = process
            server_config["pid"] = process.pid
            
            logger.info(f"✅ {name} started with PID {process.pid}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start {name}: {e}")
            return False
    
    async def start_all_servers(self) -> bool:
        """Start all MCP servers in sequence with health checks."""
        logger.info("🎯 Starting MCP Servers Orchestrator...")
        
        # Start servers in order
        for server_name, server_config in self.servers.items():
            if not self.start_server(server_name, server_config):
                logger.error(f"Failed to start {server_config['name']}")
                await self.shutdown_all_servers()
                return False
            
            # Wait for server to be ready
            if not await self.wait_for_server(
                server_config["name"], 
                server_config["process"], 
                self.startup_timeout
            ):
                logger.error(f"Health check failed for {server_config['name']}")
                await self.shutdown_all_servers()
                return False
        
        self.running = True
        logger.info("🎉 All MCP servers started successfully!")
        return True
    
    async def shutdown_server(self, server_name: str, server_config: Dict):
        """Gracefully shutdown a single server."""
        process = server_config.get("process")
        if process:
            try:
                logger.info(f"🛑 Shutting down {server_config['name']} (PID: {server_config['pid']})...")
                
                # Try graceful shutdown first
                process.terminate()
                
                # Wait for graceful shutdown
                try:
                    process.wait(timeout=5)
                    logger.info(f"✅ {server_config['name']} shutdown gracefully")
                except subprocess.TimeoutExpired:
                    # Force kill if graceful shutdown fails
                    logger.warning(f"⚠️ Force killing {server_config['name']}")
                    process.kill()
                    process.wait()
                    logger.info(f"✅ {server_config['name']} force killed")
                
            except Exception as e:
                logger.error(f"❌ Error shutting down {server_config['name']}: {e}")
            finally:
                server_config["process"] = None
                server_config["pid"] = None
    
    async def shutdown_all_servers(self):
        """Shutdown all MCP servers."""
        logger.info("🛑 Shutting down all MCP servers...")
        
        shutdown_tasks = []
        for server_name, server_config in self.servers.items():
            task = asyncio.create_task(
                self.shutdown_server(server_name, server_config)
            )
            shutdown_tasks.append(task)
        
        # Wait for all servers to shutdown
        await asyncio.gather(*shutdown_tasks, return_exceptions=True)
        
        self.running = False
        logger.info("✅ All MCP servers shutdown complete")
    
    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all running servers."""
        health_status = {}
        for server_name, server_config in self.servers.items():
            is_healthy = self.check_server_health(server_config["process"])
            health_status[server_name] = is_healthy
            status = "✅" if is_healthy else "❌"
            logger.info(f"{status} {server_config['name']}: {'Healthy' if is_healthy else 'Unhealthy'}")
        return health_status
    
    async def monitor_servers(self):
        """Monitor servers and restart if needed."""
        logger.info("🔍 Starting server monitoring...")
        
        while self.running:
            try:
                health_status = await self.health_check_all()
                
                if not all(health_status.values()):
                    logger.warning("⚠️ Some servers are unhealthy, attempting restart...")
                    await self.shutdown_all_servers()
                    await asyncio.sleep(2)
                    await self.start_all_servers()
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"❌ Monitoring error: {e}")
                await asyncio.sleep(10)

def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"📡 Received signal {signum}, initiating shutdown...")
    if hasattr(signal_handler, 'manager'):
        asyncio.create_task(signal_handler.manager.shutdown_all_servers())

async def main():
    """Main orchestrator function."""
    manager = MCPServerManager()
    
    # Set up signal handlers
    signal_handler.manager = manager
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Start all servers
        if not await manager.start_all_servers():
            logger.error("❌ Failed to start MCP servers")
            sys.exit(1)
        
        # Print status
        logger.info("\n" + "="*50)
        logger.info("🎯 MCP Servers Status:")
        logger.info("="*50)
        for server_name, server_config in manager.servers.items():
            logger.info(f"  {server_config['name']}: PID {server_config['pid']}")
        logger.info("="*50)
        logger.info("🚀 All servers are ready!")
        logger.info("Press Ctrl+C to shutdown all servers")
        logger.info("="*50 + "\n")
        
        # Start monitoring
        await manager.monitor_servers()
        
    except KeyboardInterrupt:
        logger.info("📡 Keyboard interrupt received")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
    finally:
        await manager.shutdown_all_servers()
        logger.info("👋 MCP Servers Orchestrator shutdown complete")

if __name__ == "__main__":
    # Ensure we're in the backend directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Shutdown by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)
