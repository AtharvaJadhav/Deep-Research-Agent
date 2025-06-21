#!/bin/bash

# Set environment variables (replace with your actual API keys)
export OPENAI_API_KEY="your-openai-api-key-here"
export SERPER_API_KEY="your-serper-api-key-here"
export OPENWEATHER_API_KEY="your-openweather-api-key-here"

# Install dependencies
pip install -r requirements.txt

# Create reports directory
mkdir -p reports

# Run the FastAPI server
python app.py
