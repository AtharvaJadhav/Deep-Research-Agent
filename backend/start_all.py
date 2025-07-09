#!/usr/bin/env python3
"""
Complete System Orchestrator
Starts MCP servers and FastAPI app with proper coordination.
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
import requests
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('system_orchestrator.log')
    ]
)
logger = logging.getLogger("system_orchestrator")

class SystemOrchestrator:
    """Orchestrates the complete system: MCP servers + FastAPI app."""
    
    def __init__(self):
        self.mcp_servers = {
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
        
        self.fastapi_app = {
            "script": "app.py",
            "port": 8000,
            "name": "FastAPI App",
            "process": None,
            "pid": None
        }
        
        self.running = False
        self.startup_timeout = 30  # seconds per server
        
    def check_port_available(self, port: int) -> bool:
        """Check if a port is available."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(('localhost', port))
                return result != 0  # Port is available if connection fails
        except Exception:
            return False
    
    def check_mcp_server_health(self, process) -> bool:
        """Check if an MCP server process is healthy."""
        try:
            return process.poll() is None  # Process is running if poll() returns None
        except Exception:
            return False
    
    def check_fastapi_health(self, port: int) -> bool:
        """Check if FastAPI app is responding."""
        try:
            response = requests.get(f"http://localhost:{port}/health", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
    
    async def wait_for_mcp_server(self, server_name: str, process, timeout: int) -> bool:
        """Wait for an MCP server to become ready."""
        logger.info(f"Waiting for {server_name} to be ready...")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.check_mcp_server_health(process):
                logger.info(f"✅ {server_name} is ready")
                return True
            await asyncio.sleep(1)
        
        logger.error(f"❌ {server_name} failed to start within {timeout} seconds")
        return False
    
    async def wait_for_fastapi(self, server_name: str, port: int, timeout: int) -> bool:
        """Wait for FastAPI app to become ready."""
        logger.info(f"Waiting for {server_name} to be ready on port {port}...")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.check_fastapi_health(port):
                logger.info(f"✅ {server_name} is ready on port {port}")
                return True
            await asyncio.sleep(1)
        
        logger.error(f"❌ {server_name} failed to start within {timeout} seconds")
        return False
    
    def start_mcp_server(self, server_name: str, server_config: Dict) -> bool:
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
    
    def start_fastapi_app(self) -> bool:
        """Start the FastAPI application."""
        script_path = self.fastapi_app["script"]
        port = self.fastapi_app["port"]
        name = self.fastapi_app["name"]
        
        # Check if script exists
        if not Path(script_path).exists():
            logger.error(f"❌ Script not found: {script_path}")
            return False
        
        # Check if port is available
        if not self.check_port_available(port):
            logger.error(f"❌ Port {port} is already in use")
            return False
        
        try:
            logger.info(f"🚀 Starting {name} on port {port}...")
            
            # Start the FastAPI process
            process = subprocess.Popen(
                [sys.executable, script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            self.fastapi_app["process"] = process
            self.fastapi_app["pid"] = process.pid
            
            logger.info(f"✅ {name} started with PID {process.pid}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start {name}: {e}")
            return False
    
    async def start_mcp_servers(self) -> bool:
        """Start all MCP servers in sequence with health checks."""
        logger.info("🎯 Starting MCP Servers...")
        
        # Start servers in order
        for server_name, server_config in self.mcp_servers.items():
            if not self.start_mcp_server(server_name, server_config):
                logger.error(f"Failed to start {server_config['name']}")
                await self.shutdown_all()
                return False
            
            # Wait for server to be ready
            if not await self.wait_for_mcp_server(
                server_config["name"], 
                server_config["process"], 
                self.startup_timeout
            ):
                logger.error(f"Health check failed for {server_config['name']}")
                await self.shutdown_all()
                return False
        
        logger.info("🎉 All MCP servers started successfully!")
        return True
    
    async def start_fastapi_with_mcp_check(self) -> bool:
        """Start FastAPI app after ensuring MCP servers are ready."""
        logger.info("🎯 Starting FastAPI App...")
        
        # Double-check MCP servers are healthy
        logger.info("🔍 Verifying MCP servers before starting FastAPI...")
        for server_name, server_config in self.mcp_servers.items():
            if not self.check_mcp_server_health(server_config["process"]):
                logger.error(f"MCP server {server_config['name']} is not healthy")
                return False
        
        # Start FastAPI app
        if not self.start_fastapi_app():
            return False
        
        # Wait for FastAPI to be ready
        if not await self.wait_for_fastapi(
            self.fastapi_app["name"],
            self.fastapi_app["port"],
            self.startup_timeout
        ):
            logger.error("FastAPI app failed to start")
            await self.shutdown_all()
            return False
        
        logger.info("🎉 FastAPI app started successfully!")
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
    
    async def shutdown_fastapi(self):
        """Gracefully shutdown FastAPI app."""
        process = self.fastapi_app.get("process")
        if process:
            try:
                logger.info(f"🛑 Shutting down {self.fastapi_app['name']} (PID: {self.fastapi_app['pid']})...")
                
                # Try graceful shutdown first
                process.terminate()
                
                # Wait for graceful shutdown
                try:
                    process.wait(timeout=5)
                    logger.info(f"✅ {self.fastapi_app['name']} shutdown gracefully")
                except subprocess.TimeoutExpired:
                    # Force kill if graceful shutdown fails
                    logger.warning(f"⚠️ Force killing {self.fastapi_app['name']}")
                    process.kill()
                    process.wait()
                    logger.info(f"✅ {self.fastapi_app['name']} force killed")
                
            except Exception as e:
                logger.error(f"❌ Error shutting down {self.fastapi_app['name']}: {e}")
            finally:
                self.fastapi_app["process"] = None
                self.fastapi_app["pid"] = None
    
    async def shutdown_all(self):
        """Shutdown all processes."""
        logger.info("🛑 Shutting down all processes...")
        
        # Shutdown FastAPI first
        await self.shutdown_fastapi()
        
        # Shutdown MCP servers
        shutdown_tasks = []
        for server_name, server_config in self.mcp_servers.items():
            task = asyncio.create_task(
                self.shutdown_server(server_name, server_config)
            )
            shutdown_tasks.append(task)
        
        # Wait for all servers to shutdown
        await asyncio.gather(*shutdown_tasks, return_exceptions=True)
        
        self.running = False
        logger.info("✅ All processes shutdown complete")
    
    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all running processes."""
        health_status = {}
        
        # Check MCP servers
        for server_name, server_config in self.mcp_servers.items():
            is_healthy = self.check_mcp_server_health(server_config["process"])
            health_status[server_name] = is_healthy
            status = "✅" if is_healthy else "❌"
            logger.info(f"{status} {server_config['name']}: {'Healthy' if is_healthy else 'Unhealthy'}")
        
        # Check FastAPI app
        fastapi_healthy = self.check_fastapi_health(self.fastapi_app["port"])
        health_status["fastapi"] = fastapi_healthy
        status = "✅" if fastapi_healthy else "❌"
        logger.info(f"{status} {self.fastapi_app['name']}: {'Healthy' if fastapi_healthy else 'Unhealthy'}")
        
        return health_status
    
    async def monitor_system(self):
        """Monitor all processes and restart if needed."""
        logger.info("🔍 Starting system monitoring...")
        
        while self.running:
            try:
                health_status = await self.health_check_all()
                
                if not all(health_status.values()):
                    logger.warning("⚠️ Some processes are unhealthy, attempting restart...")
                    await self.shutdown_all()
                    await asyncio.sleep(2)
                    
                    # Restart everything
                    if not await self.start_mcp_servers():
                        logger.error("Failed to restart MCP servers")
                        break
                    
                    if not await self.start_fastapi_with_mcp_check():
                        logger.error("Failed to restart FastAPI app")
                        break
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"❌ Monitoring error: {e}")
                await asyncio.sleep(10)

def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"📡 Received signal {signum}, initiating shutdown...")
    if hasattr(signal_handler, 'orchestrator'):
        asyncio.create_task(signal_handler.orchestrator.shutdown_all())

async def main():
    """Main orchestrator function."""
    orchestrator = SystemOrchestrator()
    
    # Set up signal handlers
    signal_handler.orchestrator = orchestrator
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Start MCP servers first
        if not await orchestrator.start_mcp_servers():
            logger.error("❌ Failed to start MCP servers")
            sys.exit(1)
        
        # Start FastAPI app
        if not await orchestrator.start_fastapi_with_mcp_check():
            logger.error("❌ Failed to start FastAPI app")
            sys.exit(1)
        
        orchestrator.running = True
        
        # Print status
        logger.info("\n" + "="*60)
        logger.info("🎯 Complete System Status:")
        logger.info("="*60)
        logger.info("MCP Servers:")
        for server_name, server_config in orchestrator.mcp_servers.items():
            logger.info(f"  {server_config['name']}: PID {server_config['pid']}")
        logger.info("FastAPI App:")
        logger.info(f"  {orchestrator.fastapi_app['name']}: localhost:{orchestrator.fastapi_app['port']} (PID: {orchestrator.fastapi_app['pid']})")
        logger.info("="*60)
        logger.info("🚀 All servers are ready!")
        logger.info("Press Ctrl+C to shutdown all servers")
        logger.info("="*60 + "\n")
        
        # Start monitoring
        await orchestrator.monitor_system()
        
    except KeyboardInterrupt:
        logger.info("📡 Keyboard interrupt received")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
    finally:
        await orchestrator.shutdown_all()
        logger.info("👋 System Orchestrator shutdown complete")

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