from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, AsyncGenerator
import json
import asyncio
import os
from openai import AsyncOpenAI
from tools import search_web, write_file, get_weather, call_tool, send_email

app = FastAPI(title="Deep Research Agent API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize OpenAI client
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", "api-key"))

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]
    tools: List[str] = []
    deep_research_mode: bool = False

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
        
        stream = await client.chat.completions.create(model="gpt-4", messages=openai_messages, stream=True, temperature=0.7)
        
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
                model="gpt-4",
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
        
        stream = await client.chat.completions.create(model="gpt-4", messages=messages, stream=True, temperature=0.5)
        
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
