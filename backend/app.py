from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, AsyncGenerator
import json
import asyncio
import os
import uuid
from datetime import datetime
from openai import AsyncOpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import MCP client manager
from mcp_client.client_manager import get_client_manager, shutdown_client_manager, MCPClientManager

app = FastAPI(title="Deep Research Agent API with MCP Integration")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")

# Initialize OpenAI client
api_key = os.getenv("OPENAI_API_KEY")
if not api_key or api_key == "api-key":
    print(f"Warning: OPENAI_API_KEY not found or invalid. Current value: {api_key}")
    print("Please check your .env file contains: OPENAI_API_KEY=your-actual-key")
else:
    print(f"OpenAI API key loaded successfully (length: {len(api_key)})")

# Initialize OpenAI client - will be created per request to avoid compatibility issues
def get_openai_client():
    return AsyncOpenAI(api_key=api_key)

# Global MCP client manager
mcp_manager: Optional[MCPClientManager] = None

# Research session storage
sessions: Dict[str, 'ResearchSession'] = {}

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]
    tools: List[str] = []
    deep_research_mode: bool = False

class ResearchSession(BaseModel):
    research_id: str
    original_query: str
    research_goals: List[str]
    learnings: List[Dict[str, Any]]
    current_depth: int
    max_depth: int
    current_breadth: int
    max_breadth: int
    iteration_count: int
    status: str  # "planning", "researching", "complete"
    created_at: datetime
    updated_at: datetime

class ResearchStartRequest(BaseModel):
    query: str
    research_goals: List[str] = []
    max_depth: int = 3
    max_breadth: int = 5

class ResearchExecuteRequest(BaseModel):
    tools: List[str] = []

class MCPStatusResponse(BaseModel):
    overall_status: str
    servers: Dict[str, Dict[str, Any]]

# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Initialize MCP client manager on startup."""
    global mcp_manager
    try:
        print("Initializing MCP Client Manager...")
        mcp_manager = await get_client_manager()
        print("MCP Client Manager initialized successfully")
    except Exception as e:
        print(f"Failed to initialize MCP Client Manager: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup MCP client manager on shutdown."""
    global mcp_manager
    if mcp_manager:
        await shutdown_client_manager()
        print("MCP Client Manager shutdown complete")

def get_system_prompt(available_tools: List[str]) -> str:
    """Generate system prompt based on available MCP tools."""
    tool_descriptions = {
        "search_web": "search_web(query: str, max_results: int = 5) -> dict: Searches the web using Serper API and returns structured results.",
        "write_file": "write_file(filename: str, content: str) -> dict: Writes content to a markdown file in research_output directory.",
        "read_file": "read_file(filename: str) -> dict: Reads content from an existing file.",
        "list_files": "list_files(directory: str = 'research_output') -> dict: Lists files in the specified directory.",
        "get_weather": "get_weather(location: str, units: str = 'metric') -> dict: Gets current weather information for a location."
    }
    
    tools_text = "\n".join([f"- {tool_descriptions.get(tool, f'{tool}: Tool description not available')}" 
                           for tool in available_tools])
    
    return f"""You are a helpful research assistant that can answer questions and help with tasks using MCP (Model Context Protocol) tools.

You have access to the following MCP tools:

{tools_text}

When you need to use a tool, respond in this format:
<tool>
{{"name": "tool_name", "args": {{"param": "value"}}}}
</tool>

When you have completed your research and are ready to provide a final answer, use this format:
<answer>
[your final comprehensive answer here]
</answer>

After conducting your research, you must synthesize the gathered information into a comprehensive and detailed report. Your final answer should be a well-structured summary of your findings, not just a list of links or brief summaries.

At the end of your final answer, always ask the user: "Would you like me to dive deeper into any specific aspect of this report?"
"""

def parse_tool_call(response: str) -> Optional[Dict]:
    """Parse a tool call from LLM response."""
    import re
    tool_match = re.search(r'<tool>(.*?)</tool>', response, re.DOTALL)
    if tool_match:
        try:
            return json.loads(tool_match.group(1))
        except json.JSONDecodeError:
            return None
    return None

def parse_answer(response: str) -> Optional[str]:
    """Parse final answer from LLM response."""
    import re
    answer_match = re.search(r'<answer>(.*?)</answer>', response, re.DOTALL | re.IGNORECASE)
    if answer_match:
        return answer_match.group(1).strip()
    return None

async def stream_words(text: str) -> AsyncGenerator[str, None]:
    """Stream text word by word with realistic delays."""
    words = text.split()
    for i, word in enumerate(words):
        if i > 0:
            yield " "
        yield word
        # Add slight delay between words for realistic streaming effect
        await asyncio.sleep(0.05)

async def call_mcp_tool(tool_name: str, args: Dict[str, Any]) -> str:
    """Call MCP tool and return result as string."""
    global mcp_manager
    if not mcp_manager:
        raise RuntimeError("MCP Client Manager not initialized")
    
    print(f"call_mcp_tool called with {tool_name} and args: {args}")
    
    try:
        if tool_name == "search_web":
            print(f"Calling web search with query: {args.get('query', '')}")
            result = await mcp_manager.search_web(
                query=args.get("query", ""),
                max_results=args.get("max_results", 5)
            )
        elif tool_name == "write_file":
            result = await mcp_manager.write_file(
                filename=args.get("filename", ""),
                content=args.get("content", "")
            )
        elif tool_name == "read_file":
            result = await mcp_manager.read_file(
                filename=args.get("filename", "")
            )
        elif tool_name == "list_files":
            result = await mcp_manager.list_files(
                directory=args.get("directory", "research_output")
            )
        elif tool_name == "get_weather":
            print(f"Calling weather with location: {args.get('location', '')}")
            result = await mcp_manager.get_weather(
                location=args.get("location", ""),
                units=args.get("units", "metric")
            )
        else:
            raise ValueError(f"Unknown MCP tool: {tool_name}")
        
        print(f"MCP tool {tool_name} returned result: {str(result)[:100]}...")
        return str(result)
    except Exception as e:
        return f"Error calling {tool_name}: {str(e)}"

async def stream_simple_completion(messages: List[Dict]) -> AsyncGenerator[str, None]:
    """Stream a simple conversational completion."""
    try:
        conversational_system_prompt = "You are a helpful and friendly conversational assistant. Respond directly to the user's query without using tools."
        openai_messages = [{"role": msg.role, "content": msg.content} for msg in messages]
        openai_messages.insert(0, {"role": "system", "content": conversational_system_prompt})
        
        client = get_openai_client()
        stream = await client.chat.completions.create(model=MODEL_NAME, messages=openai_messages, stream=True, temperature=0.7)
        
        yield f"data: {json.dumps({'type': 'start_answer'})}\n\n"
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

async def stream_deep_research(messages: List[Dict], available_tools: List[str]) -> AsyncGenerator[str, None]:
    """Stream deep research with MCP tool calling loop, showing tool usage to user."""
    try:
        print(f"Starting deep research with {len(available_tools)} available tools: {available_tools}")
        
        # Convert messages to OpenAI format
        research_messages = [{"role": msg.role, "content": msg.content} for msg in messages]
        research_messages.insert(0, {"role": "system", "content": get_system_prompt(available_tools)})
        
        max_turns = 10
        turn = 0
        final_answer = None
        
        # Show initial thinking message
        yield f"data: {json.dumps({'type': 'thinking', 'content': 'Starting deep research with MCP tools...'})}\n\n"
        
        while turn < max_turns and not final_answer:
            turn += 1
            print(f"Research turn {turn}/{max_turns}")
            
            # Get LLM response
            client = get_openai_client()
            print(f"Calling OpenAI API...")
            response = await client.chat.completions.create(
                model=MODEL_NAME,
                messages=research_messages,
                temperature=0.7
            )
            
            content = response.choices[0].message.content
            print(f"LLM Response: {content[:200]}...")
            
            # Parse response components
            tool_call = parse_tool_call(content)
            answer = parse_answer(content)
            
            print(f"Tool call found: {tool_call is not None}")
            print(f"Answer found: {answer is not None}")
            
            # If we have a final answer, break and stream it
            if answer:
                final_answer = answer
                break
            
            # Handle tool call
            if tool_call and tool_call.get('name') in available_tools:
                tool_name = tool_call['name']
                tool_args = tool_call.get('args', {})
                
                print(f"Calling MCP tool: {tool_name} with args: {tool_args}")
                
                # Show tool usage to user
                yield f"data: {json.dumps({'type': 'tool_call', 'tool': tool_name, 'args': tool_args})}\n\n"
                
                # Call MCP tool
                try:
                    print(f"Starting MCP tool call for {tool_name}...")
                    tool_result = await call_mcp_tool(tool_name, tool_args)
                    print(f"MCP tool {tool_name} completed successfully")
                    yield f"data: {json.dumps({'type': 'tool_result', 'tool': tool_name, 'result': tool_result})}\n\n"
                    
                    # Add tool result to conversation
                    research_messages.append({"role": "assistant", "content": content})
                    research_messages.append({"role": "user", "content": f"Tool result: {tool_result}"})
                    
                except Exception as e:
                    error_msg = f"Error calling {tool_name}: {str(e)}"
                    print(f"MCP tool {tool_name} failed: {str(e)}")
                    yield f"data: {json.dumps({'type': 'tool_error', 'tool': tool_name, 'error': error_msg})}\n\n"
                    research_messages.append({"role": "assistant", "content": content})
                    research_messages.append({"role": "user", "content": f"Tool error: {error_msg}"})
            else:
                # No tool call, add response to conversation
                research_messages.append({"role": "assistant", "content": content})
        
        # Stream final answer
        if final_answer:
            print(f"Research completed with final answer")
            yield f"data: {json.dumps({'type': 'start_answer'})}\n\n"
            async for word in stream_words(final_answer):
                yield f"data: {json.dumps({'type': 'content', 'content': word})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        else:
            print(f"Research completed without final answer")
            yield f"data: {json.dumps({'type': 'error', 'content': 'Research completed without final answer'})}\n\n"
            
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

def create_research_session(query: str, research_goals: List[str], max_depth: int, max_breadth: int) -> ResearchSession:
    """Create a new research session."""
    research_id = str(uuid.uuid4())
    now = datetime.now()
    
    session = ResearchSession(
        research_id=research_id,
        original_query=query,
        research_goals=research_goals,
        learnings=[],
        current_depth=0,
        max_depth=max_depth,
        current_breadth=0,
        max_breadth=max_breadth,
        iteration_count=0,
        status="planning",
        created_at=now,
        updated_at=now
    )
    
    sessions[research_id] = session
    return session

def get_research_session(research_id: str) -> Optional[ResearchSession]:
    """Get a research session by ID."""
    return sessions.get(research_id)

def update_research_session(research_id: str, **kwargs) -> Optional[ResearchSession]:
    """Update a research session."""
    session = sessions.get(research_id)
    if session:
        for key, value in kwargs.items():
            if hasattr(session, key):
                setattr(session, key, value)
        session.updated_at = datetime.now()
    return session

# Research endpoints
@app.post("/research/start")
async def start_research(request: ResearchStartRequest):
    """Start a new research session."""
    try:
        session = create_research_session(
            query=request.query,
            research_goals=request.research_goals,
            max_depth=request.max_depth,
            max_breadth=request.max_breadth
        )
        
        return {
            "research_id": session.research_id,
            "status": session.status,
            "message": "Research session created successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/research/{research_id}/status")
async def get_research_status(research_id: str):
    """Get the status of a research session."""
    session = get_research_session(research_id)
    if not session:
        raise HTTPException(status_code=404, detail="Research session not found")
    
    return {
        "research_id": session.research_id,
        "status": session.status,
        "current_depth": session.current_depth,
        "max_depth": session.max_depth,
        "current_breadth": session.current_breadth,
        "max_breadth": session.max_breadth,
        "iteration_count": session.iteration_count,
        "learnings_count": len(session.learnings),
        "created_at": session.created_at,
        "updated_at": session.updated_at
    }

async def stream_research_execution(research_id: str, request: ResearchExecuteRequest) -> AsyncGenerator[str, None]:
    """Stream research execution with MCP tools."""
    session = get_research_session(research_id)
    if not session:
        yield f"data: {json.dumps({'type': 'error', 'content': 'Research session not found'})}\n\n"
        return
    
    try:
        # Update session status
        update_research_session(research_id, status="researching")
        
        # Create research plan using MCP tools
        yield f"data: {json.dumps({'type': 'status', 'content': 'Planning research strategy...'})}\n\n"
        
        # Use MCP search to gather initial information
        search_results = await call_mcp_tool("search_web", {
            "query": session.original_query,
            "max_results": 3
        })
        
        yield f"data: {json.dumps({'type': 'search_results', 'content': search_results})}\n\n"
        
        # Generate research report
        yield f"data: {json.dumps({'type': 'status', 'content': 'Generating research report...'})}\n\n"
        
        # Save report using MCP file operations
        report_content = f"""# Research Report: {session.original_query}

## Executive Summary
Research conducted using MCP tools for: {session.original_query}

## Search Results
{search_results}

## Research Session Details
- Research ID: {session.research_id}
- Created: {session.created_at}
- Status: {session.status}
- Iterations: {session.iteration_count}

## Conclusion
This research was conducted using the Model Context Protocol (MCP) infrastructure, demonstrating the integration of multiple specialized tools for comprehensive information gathering and analysis.
"""
        
        filename = f"research_report_{session.research_id}.md"
        await call_mcp_tool("write_file", {
            "filename": filename,
            "content": report_content
        })
        
        yield f"data: {json.dumps({'type': 'report_saved', 'content': f'Report saved as {filename}'})}\n\n"
        
        # Update session
        update_research_session(research_id, status="complete", iteration_count=session.iteration_count + 1)
        
        yield f"data: {json.dumps({'type': 'complete', 'content': 'Research completed successfully'})}\n\n"
        
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

@app.post("/research/{research_id}/execute")
async def execute_research(research_id: str, request: ResearchExecuteRequest):
    """Execute research for a session."""
    return StreamingResponse(
        stream_research_execution(research_id, request),
        media_type="text/plain"
    )

# Chat endpoint
@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """Main chat endpoint with MCP tool integration."""
    print(f"DEBUG: Chat endpoint called with deep_research_mode: {request.deep_research_mode}")
    print(f"DEBUG: Messages: {[msg.content[:50] + '...' if len(msg.content) > 50 else msg.content for msg in request.messages]}")
    
    if request.deep_research_mode:
        print("DEBUG: Using deep research mode with MCP tools")
        # Use deep research mode with MCP tools
        available_tools = ["search_web", "write_file", "read_file", "list_files", "get_weather"]
        return StreamingResponse(
            stream_deep_research(request.messages, available_tools),
            media_type="text/plain"
        )
    else:
        print("DEBUG: Using simple chat mode")
        # Use simple chat mode
        return StreamingResponse(
            stream_simple_completion(request.messages),
            media_type="text/plain"
        )

# Health check endpoints
@app.get("/health")
async def health_check():
    """Basic health check."""
    return {"status": "healthy", "service": "Deep Research Agent API"}

@app.get("/debug")
async def debug_endpoint():
    """Debug endpoint to test if backend is receiving requests."""
    print("DEBUG: Backend received a request to /debug endpoint")
    return {"message": "Backend is working!", "timestamp": datetime.now().isoformat()}

@app.post("/debug-post")
async def debug_post_endpoint(request: dict):
    """Debug POST endpoint to test if backend is receiving POST requests."""
    print(f"DEBUG: Backend received POST request with data: {request}")
    return {"message": "Backend POST is working!", "received_data": request, "timestamp": datetime.now().isoformat()}

@app.get("/mcp/status")
async def mcp_status() -> MCPStatusResponse:
    """Detailed MCP server status check."""
    global mcp_manager
    
    if not mcp_manager:
        return MCPStatusResponse(
            overall_status="error",
            servers={
                "web_search": {"status": "disconnected", "error": "MCP Manager not initialized"},
                "file_operations": {"status": "disconnected", "error": "MCP Manager not initialized"},
                "weather": {"status": "disconnected", "error": "MCP Manager not initialized"}
            }
        )
    
    try:
        health_status = await mcp_manager.health_check()
        
        servers_info = {}
        for server_name, is_healthy in health_status.items():
            servers_info[server_name] = {
                "status": "connected" if is_healthy else "disconnected"
            }
        
        overall_status = "healthy" if all(health_status.values()) else "degraded"
        
        return MCPStatusResponse(
            overall_status=overall_status,
            servers=servers_info
        )
        
    except Exception as e:
        return MCPStatusResponse(
            overall_status="error",
            servers={
                "web_search": {"status": "error", "error": str(e)},
                "file_operations": {"status": "error", "error": str(e)},
                "weather": {"status": "error", "error": str(e)}
            }
        )

# File upload endpoint (kept for compatibility)
@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a file for analysis."""
    try:
        content = await file.read()
        content_str = content.decode('utf-8')
        
        # Save file using MCP file operations
        filename = f"uploaded_{file.filename}"
        await call_mcp_tool("write_file", {
            "filename": filename,
            "content": content_str
        })
        
        return {
            "filename": filename,
            "size": len(content),
            "message": "File uploaded and saved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
