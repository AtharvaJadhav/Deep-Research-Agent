# Deep Research Agent

A comprehensive AI research agent with Python FastAPI backend and React frontend.

## Features

- **Streaming Output**: ChatGPT-like word-by-word streaming responses
- **Deep Research Mode**: Iterative tool usage behind the scenes
- **Three Custom Tools**:
  - Web Search (Serper API with fallback)
  - File Writer (Local markdown files)
  - Weather API (OpenWeatherMap with fallback)
- **Clean UI**: Only shows final results, hides tool execution

## Project Structure

```
├── backend/          # Python FastAPI backend
│   ├── app.py        # Main FastAPI application
│   ├── tools.py      # Custom tools implementation
│   ├── requirements.txt
│   └── Dockerfile
└── frontend/         # Next.js React frontend
    ├── app/          # Next.js app directory
    ├── components/   # React components
    ├── lib/          # Utility functions
    ├── hooks/        # Custom React hooks
    ├── public/       # Static assets
    ├── styles/       # CSS styles
    ├── package.json
    └── next.config.mjs
```

## Setup

### Backend (Python FastAPI)

1. Navigate to backend directory:
   ```bash
   cd backend
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set environment variables:
   ```bash
   export OPENAI_API_KEY="your-openai-api-key"
   export SERPER_API_KEY="your-serper-api-key"  # Optional
   export OPENWEATHER_API_KEY="your-weather-api-key"  # Optional
   ```

4. Run the server:
   ```bash
   python app.py
   ```

   Server will start on http://localhost:8000

### Frontend (Next.js)

1. Navigate to frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   # or
   pnpm install
   ```

3. Start development server:
   ```bash
   npm run dev
   # or
   pnpm dev
   ```

   Frontend will start on http://localhost:3000

## API Keys Required

- **OpenAI API Key**: Required for LLM functionality
- **Serper API Key**: Optional (falls back to mock search)
- **OpenWeatherMap API Key**: Optional (falls back to mock weather)

## Usage

1. Start both backend and frontend servers
2. Open http://localhost:3000
3. Toggle Deep Research Mode on/off
4. Select which tools to enable
5. Ask research questions like:
   - "Research the latest AI developments and write a report"
   - "What's the weather like in Tokyo?"
   - "Find information about quantum computing"

The agent will work behind the scenes using tools but only show you the final streaming answer.

## Architecture

- **Backend**: FastAPI with async streaming
- **Tools**: Three Python tools with real API integrations
- **Frontend**: React with real-time streaming display
- **Streaming**: Word-by-word output like ChatGPT/Claude
