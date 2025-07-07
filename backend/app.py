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
from tools import search_web, write_file, get_weather, call_tool, send_email, research_planner, extract_learnings, generate_next_queries, synthesize_report

app = FastAPI(title="Deep Research Agent API")

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

client = AsyncOpenAI(api_key=api_key)

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



def get_system_prompt(available_tools: List[str]) -> str:
    """Generate system prompt based on available tools."""
    tool_descriptions = {
        "search": "search(query: str) -> str: Searches the web and returns summaries of top results.",
        "write_file": "write_file(filename: str, content: str) -> str: Writes content to a file. IMPORTANT: You must ask the user for permission *before* calling this tool.",
        "get_weather": "get_weather(location: str) -> str: Gets current weather information for a location.",
        "send_email": "send_email(to: str, subject: str, body: str) -> str: Sends an email. The user must provide the recipient's email address."
    }
    
    tools_text = "\n".join([f"- {tool_descriptions.get(tool, f'{tool}: Tool description not available')}" 
                           for tool in available_tools])
    
    return f"""You are a helpful research assistant that can answer questions and help with tasks. 
You have access to the following tools:

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

async def stream_simple_completion(messages: List[Dict]) -> AsyncGenerator[str, None]:
    """Stream a simple conversational completion."""
    try:
        conversational_system_prompt = "You are a helpful and friendly conversational assistant. Respond directly to the user's query without using tools."
        openai_messages = [{"role": msg["role"], "content": msg["content"]} for msg in messages]
        openai_messages.insert(0, {"role": "system", "content": conversational_system_prompt})
        
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
    """Stream deep research with tool calling loop, showing tool usage to user."""
    try:
        # Convert messages to OpenAI format
        research_messages = [{"role": msg["role"], "content": msg["content"]} for msg in messages]
        research_messages.insert(0, {"role": "system", "content": get_system_prompt(available_tools)})
        
        max_turns = 10
        turn = 0
        final_answer = None
        
        # Show initial thinking message
        yield f"data: {json.dumps({'type': 'thinking', 'content': 'Starting deep research...'})}\n\n"
        
        while turn < max_turns and not final_answer:
            turn += 1
            
            # Get LLM response
            response = await client.chat.completions.create(
                model=MODEL_NAME,
                messages=research_messages,
                temperature=0.7
            )
            

            
            content = response.choices[0].message.content
            
            # Parse response components
            tool_call = parse_tool_call(content)
            answer = parse_answer(content)
            
            # If we have a final answer, break and stream it
            if answer:
                final_answer = answer
                break
            
            # Handle tool call
            if tool_call and tool_call.get('name') in available_tools:
                tool_name = tool_call['name']
                tool_args = tool_call.get('args', {})
                
                # Show tool usage to user
                yield f"data: {json.dumps({'type': 'tool_call', 'tool': tool_name, 'args': tool_args})}\n\n"
                
                try:
                    # Execute the tool
                    tool_result = await call_tool(tool_name, tool_args)
                    
                    # Show tool result to user
                    yield f"data: {json.dumps({'type': 'tool_result', 'tool': tool_name, 'result': tool_result})}\n\n"
                    
                    # Add tool result to conversation
                    research_messages.append({"role": "assistant", "content": content})
                    research_messages.append({"role": "user", "content": f"Tool result: {tool_result}"})
                    
                except Exception as e:
                    error_msg = f"Tool execution error: {str(e)}"
                    yield f"data: {json.dumps({'type': 'tool_error', 'tool': tool_name, 'error': error_msg})}\n\n"
                    research_messages.append({"role": "user", "content": error_msg})
            
            # If no tool call and no answer, this might be the final response
            elif not tool_call:
                final_answer = content
                break
        
        # Stream the final answer word by word
        if final_answer:
            yield f"data: {json.dumps({'type': 'start_answer'})}\n\n"
            
            async for word in stream_words(final_answer):
                yield f"data: {json.dumps({'type': 'content', 'content': word})}\n\n"
        else:
            # Fallback if no final answer was generated
            fallback_answer = "I apologize, but I wasn't able to complete the research within the allowed number of steps. Please try rephrasing your question or being more specific."
            async for word in stream_words(fallback_answer):
                yield f"data: {json.dumps({'type': 'content', 'content': word})}\n\n"
        
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

# Research Session Management Functions
def create_research_session(query: str, research_goals: List[str], max_depth: int, max_breadth: int) -> ResearchSession:
    """Create a new research session."""
    research_id = str(uuid.uuid4())
    now = datetime.now()
    
    session = ResearchSession(
        research_id=research_id,
        original_query=query,
        research_goals=research_goals or [query],
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
    if research_id in sessions:
        session = sessions[research_id]
        for key, value in kwargs.items():
            if hasattr(session, key):
                setattr(session, key, value)
        session.updated_at = datetime.now()
        return session
    return None

# New Research Endpoints
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
    """Get the current status of a research session."""
    session = get_research_session(research_id)
    if not session:
        raise HTTPException(status_code=404, detail="Research session not found")
    
    return {
        "research_id": session.research_id,
        "original_query": session.original_query,
        "research_goals": session.research_goals,
        "current_depth": session.current_depth,
        "max_depth": session.max_depth,
        "current_breadth": session.current_breadth,
        "max_breadth": session.max_breadth,
        "iteration_count": session.iteration_count,
        "status": session.status,
        "learnings_count": len(session.learnings),
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat()
    }

async def stream_research_execution(research_id: str, request: ResearchExecuteRequest) -> AsyncGenerator[str, None]:
    """Stream the iterative research execution."""
    try:
        session = get_research_session(research_id)
        if not session:
            yield f"data: {json.dumps({'type': 'error', 'content': 'Research session not found'})}\n\n"
            return
        
        if session.status == "complete":
            yield f"data: {json.dumps({'type': 'error', 'content': 'Research session already completed'})}\n\n"
            return
        
        # Update session status
        update_research_session(research_id, status="researching")
        
        # Initialize research goals if this is the first iteration
        if session.iteration_count == 0:
            yield f"data: {json.dumps({'type': 'research_status', 'message': 'Planning research strategy...'})}\n\n"
            
            plan = await research_planner(session.original_query, client)
            if plan.get("research_goals"):
                update_research_session(research_id, research_goals=plan["research_goals"])
                yield f"data: {json.dumps({'type': 'research_plan', 'goals': plan['research_goals'], 'reasoning': plan.get('reasoning', '')})}\n\n"
        
        total_searches = 0
        max_total_searches = 20  # Cost control
        
        # Main research loop
        while session.current_depth < session.max_depth and total_searches < max_total_searches:
            session = get_research_session(research_id)  # Refresh session state
            
            # Generate next queries
            next_queries = await generate_next_queries(session.learnings, session.original_query, client)
            
            if not next_queries:
                yield f"data: {json.dumps({'type': 'research_status', 'message': 'No more queries needed - research complete'})}\n\n"
                break
            
            # Limit to max_breadth queries
            queries_to_execute = next_queries[:session.max_breadth]
            total_searches += len(queries_to_execute)
            
            # Stream current iteration status
            message = f'Executing {len(queries_to_execute)} searches for depth {session.current_depth + 1}'
            status_data = {
                'type': 'research_status', 
                'depth': session.current_depth + 1, 
                'iteration': session.iteration_count + 1, 
                'queries': queries_to_execute,
                'message': message
            }
            yield f"data: {json.dumps(status_data)}\n\n"
            
            # Execute searches in parallel
            search_tasks = [search_web(query) for query in queries_to_execute]
            search_results = await asyncio.gather(*search_tasks)
            
            # Extract learnings from each result
            new_learnings = []
            for i, (query, result) in enumerate(zip(queries_to_execute, search_results)):
                # Extract learnings for each research goal
                for goal in session.research_goals:
                    learning = await extract_learnings(result, goal, client)
                    
                    if learning.get("insights"):
                        new_learning = {
                            "query": query,
                            "goal": goal,
                            "insights": learning.get("insights", []),
                            "gaps": learning.get("gaps", []),
                            "sources": learning.get("sources", []),
                            "iteration": session.iteration_count + 1,
                            "depth": session.current_depth + 1
                        }
                        new_learnings.append(new_learning)
                        
                        # Stream individual learning
                        for insight in learning.get("insights", []):
                            source = learning.get('sources', [''])[0] if learning.get('sources') else ''
                            learning_data = {
                                'type': 'learning',
                                'insight': insight,
                                'source': source,
                                'iteration': session.iteration_count + 1,
                                'goal': goal
                            }
                            yield f"data: {json.dumps(learning_data)}\n\n"
            
            # Update session with new learnings
            if new_learnings:
                update_research_session(research_id, 
                    learnings=session.learnings + new_learnings,
                    current_depth=session.current_depth + 1,
                    iteration_count=session.iteration_count + 1)
                
                iteration_data = {
                    'type': 'iteration_complete', 
                    'depth': session.current_depth + 1,
                    'new_learnings': len(new_learnings),
                    'total_learnings': len(session.learnings) + len(new_learnings)
                }
                yield f"data: {json.dumps(iteration_data)}\n\n"
            else:
                # No new learnings found
                no_insights_data = {
                    'type': 'research_status', 
                    'message': 'No new insights found in this iteration'
                }
                yield f"data: {json.dumps(no_insights_data)}\n\n"
                break
        
        # Generate final report
        session = get_research_session(research_id)  # Get final session state
        generating_report_data = {
            'type': 'research_status', 
            'message': 'Generating final research report...'
        }
        yield f"data: {json.dumps(generating_report_data)}\n\n"
        
        final_report = await synthesize_report(session.learnings, session.original_query, client)
        
        # Mark session as complete
        update_research_session(research_id, status="complete")
        
        # Stream final report
        final_report_data = {
            'type': 'research_complete', 
            'total_learnings': len(session.learnings),
            'final_report': final_report,
            'total_searches': total_searches,
            'final_depth': session.current_depth
        }
        yield f"data: {json.dumps(final_report_data)}\n\n"
        
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

@app.post("/research/{research_id}/execute")
async def execute_research(research_id: str, request: ResearchExecuteRequest):
    """Execute the research loop for a session."""
    return StreamingResponse(stream_research_execution(research_id, request), media_type="text/plain")



# Existing endpoints (unchanged for backward compatibility)
@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        user_message = request.messages[-1].content
        mod_response = await client.moderations.create(input=user_message)
        if mod_response.results[0].flagged:
            flagged_message = "Your message has been flagged as inappropriate and cannot be processed."
            return StreamingResponse(
                (f"data: {json.dumps({'type': 'error', 'content': flagged_message})}\n\n"
                 f"data: {json.dumps({'type': 'done'})}\n\n"),
                media_type="text/plain"
            )

        messages = [msg.dict() for msg in request.messages]
        
        if request.deep_research_mode:
            return StreamingResponse(stream_deep_research(messages, request.tools), media_type="text/plain")
        else:
            return StreamingResponse(stream_simple_completion(messages), media_type="text/plain")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "message": "Deep Research Agent API is running"}

async def stream_file_explanation(file_content: str, filename: str) -> AsyncGenerator[str, None]:
    """Streams an explanation of the provided file content."""
    try:
        system_prompt = "You are an expert analyst. Your task is to provide a clear, concise, and comprehensive explanation of the following file content."
        user_prompt = f"Filename: {filename}\n\nFile Content:\n---\n{file_content[:10000]}\n---\n\nPlease provide a detailed explanation of this file. What is its purpose, what does it do, and what are the key components?"
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        
        stream = await client.chat.completions.create(model=MODEL_NAME, messages=messages, stream=True, temperature=0.5)
        
        yield f"data: {json.dumps({'type': 'start_answer'})}\n\n"
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        try:
            file_content_str = contents.decode('utf-8')
        except UnicodeDecodeError:
            file_content_str = f"Error: Could not decode file '{file.filename}'. It may be a binary file or have an unsupported encoding."

        return StreamingResponse(stream_file_explanation(file_content_str, file.filename), media_type="text/plain")
    except Exception as e:
        error_message = f"Failed to process file: {str(e)}"
        return StreamingResponse(
            (f"data: {json.dumps({'type': 'error', 'content': error_message})}\n\n"
             f"data: {json.dumps({'type': 'done'})}\n\n"),
            media_type="text/plain"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
