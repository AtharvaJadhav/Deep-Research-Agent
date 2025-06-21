import asyncio
import aiohttp
import json

async def test_chat_endpoint():
    """Test the chat endpoint with both simple and deep research modes."""
    
    # Test data
    simple_request = {
        "messages": [
            {"role": "user", "content": "Hello, how are you?"}
        ],
        "tools": [],
        "deep_research_mode": False
    }
    
    deep_research_request = {
        "messages": [
            {"role": "user", "content": "Research the latest AI developments and write a report"}
        ],
        "tools": ["search", "write_file"],
        "deep_research_mode": True
    }
    
    async with aiohttp.ClientSession() as session:
        # Test simple completion
        print("Testing simple completion...")
        async with session.post(
            "http://localhost:8000/chat",
            json=simple_request,
            headers={"Content-Type": "application/json"}
        ) as response:
            print(f"Status: {response.status}")
            if response.status == 200:
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        print(f"Received: {data}")
                        if data.get('type') == 'done':
                            break
        
        print("\n" + "="*50 + "\n")
        
        # Test deep research
        print("Testing deep research...")
        async with session.post(
            "http://localhost:8000/chat",
            json=deep_research_request,
            headers={"Content-Type": "application/json"}
        ) as response:
            print(f"Status: {response.status}")
            if response.status == 200:
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if line.startswith('data: '):
                        data = json.loads(line[6:])
                        print(f"Received: {data}")
                        if data.get('type') == 'done':
                            break

if __name__ == "__main__":
    asyncio.run(test_chat_endpoint()) 