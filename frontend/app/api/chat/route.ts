import type { NextRequest } from "next/server"

interface Message {
  role: string
  content: string
}

interface ChatRequest {
  messages: Message[]
  tools: string[]
  deep_research_mode: boolean
}

interface ToolCall {
  name: string
  args: Record<string, any>
}

// Mock tools implementation
async function searchWeb(query: string): Promise<string> {
  // Simulate API delay
  await new Promise((resolve) => setTimeout(resolve, 1000))

  const results = [
    {
      title: `Latest developments in ${query}`,
      url: "https://example.com/article1",
      snippet: `Comprehensive coverage of ${query} with recent updates and expert analysis.`,
    },
    {
      title: `${query} - Breaking News`,
      url: "https://example.com/news",
      snippet: `Latest news and developments related to ${query} from trusted sources.`,
    },
    {
      title: `Complete Guide to ${query}`,
      url: "https://example.com/guide",
      snippet: `In-depth guide covering everything you need to know about ${query}.`,
    },
  ]

  return results
    .map((result, i) => `${i + 1}. **${result.title}**\n   URL: ${result.url}\n   Summary: ${result.snippet}\n`)
    .join("\n")
}

async function writeFile(filename: string, content: string): Promise<string> {
  // Simulate file writing delay
  await new Promise((resolve) => setTimeout(resolve, 500))

  if (!filename.endsWith(".md")) {
    filename += ".md"
  }

  return `Successfully wrote content to reports/${filename}. File size: ${content.length} characters.`
}

async function getWeather(location: string): Promise<string> {
  // Simulate API delay
  await new Promise((resolve) => setTimeout(resolve, 500))

  const conditions = ["sunny", "cloudy", "rainy", "partly cloudy", "windy"]
  const temperatures = [15, 20, 25, 30, 35]

  const condition = conditions[Math.floor(Math.random() * conditions.length)]
  const temp = temperatures[Math.floor(Math.random() * temperatures.length)]
  const humidity = Math.floor(Math.random() * 50) + 30

  return JSON.stringify(
    {
      location,
      temperature: `${temp}°C`,
      condition,
      humidity: `${humidity}%`,
      description: `Current weather in ${location}: ${condition} with temperature of ${temp}°C and humidity at ${humidity}%.`,
    },
    null,
    2,
  )
}

async function callTool(toolName: string, args: Record<string, any>): Promise<string> {
  switch (toolName) {
    case "search":
      return await searchWeb(args.query || "")
    case "write_file":
      return await writeFile(args.filename || "", args.content || "")
    case "get_weather":
      return await getWeather(args.location || "")
    default:
      return `Unknown tool: ${toolName}`
  }
}

function parseToolFromResponse(response: string): ToolCall | null {
  const toolMatch = response.match(/<tool>(.*?)<\/tool>/s)
  if (toolMatch) {
    try {
      return JSON.parse(toolMatch[1])
    } catch {
      return null
    }
  }
  return null
}

function parseThinkingFromResponse(response: string): string | null {
  const thinkingMatch = response.match(/<Thinking>(.*?)<\/Thinking>/s)
  return thinkingMatch ? thinkingMatch[1].trim() : null
}

function parseAnswerFromResponse(response: string): string | null {
  const answerMatch = response.match(/<answer>(.*?)<\/answer>/s)
  return answerMatch ? answerMatch[1].trim() : null
}

function getSystemPrompt(availableTools: string[]): string {
  const toolDescriptions: Record<string, string> = {
    search: "search(query: str) -> str: Searches the web and returns summaries of top results.",
    write_file: "write_file(filename: str, content: str) -> str: Writes content to a file in the reports directory.",
    get_weather: "get_weather(location: str) -> str: Gets current weather information for a location.",
  }

  const toolsText = availableTools
    .map((tool) => `- ${toolDescriptions[tool] || `${tool}: Tool description not available`}`)
    .join("\n")

  return `You are a helpful research assistant that can answer questions and help with tasks. 
You have access to the following tools:

${toolsText}

When using tools, respond in this format:

<Thinking>
[your reasoning here]
</Thinking>
<tool>
{"name": "tool_name", "args": {"param": "value"}}
</tool>

When you have completed your research and are ready to provide a final answer, use:

<answer>
[your final comprehensive answer here]
</answer>

Be thorough in your research and cite sources when relevant.`
}

// Mock OpenAI API call
async function mockOpenAICall(messages: Message[]): Promise<string> {
  // Simulate API delay
  await new Promise((resolve) => setTimeout(resolve, 1000))

  const lastMessage = messages[messages.length - 1]
  const userQuery = lastMessage.content.toLowerCase()

  // Simple logic to determine response based on query
  if (userQuery.includes("weather")) {
    return `<Thinking>
The user is asking about weather. I should use the get_weather tool to get current weather information.
</Thinking>
<tool>
{"name": "get_weather", "args": {"location": "New York"}}
</tool>`
  }

  if (userQuery.includes("search") || userQuery.includes("research") || userQuery.includes("find")) {
    const searchQuery = userQuery.includes("ai")
      ? "artificial intelligence"
      : userQuery.includes("quantum")
        ? "quantum computing"
        : "latest technology trends"

    return `<Thinking>
The user wants me to research information. I should start by searching the web for relevant information.
</Thinking>
<tool>
{"name": "search", "args": {"query": "${searchQuery}"}}
</tool>`
  }

  if (userQuery.includes("write") || userQuery.includes("report") || userQuery.includes("file")) {
    return `<Thinking>
The user wants me to write content to a file. Let me create a comprehensive report based on the research.
</Thinking>
<tool>
{"name": "write_file", "args": {"filename": "research_report", "content": "# Research Report\\n\\nThis is a comprehensive report based on the research conducted.\\n\\n## Key Findings\\n\\n- Finding 1: Important discovery\\n- Finding 2: Significant trend\\n- Finding 3: Notable development\\n\\n## Conclusion\\n\\nThe research shows promising developments in the field."}}
</tool>`
  }

  // Default response
  return `<Thinking>
I should provide a helpful response to the user's query.
</Thinking>
<answer>
I'm ready to help you with research tasks! I can search the web, write reports to files, and get weather information. What would you like me to research for you?
</answer>`
}

export async function POST(request: NextRequest) {
  try {
    const body: ChatRequest = await request.json()
    const { messages, tools, deep_research_mode } = body

    const encoder = new TextEncoder()

    const stream = new ReadableStream({
      async start(controller) {
        try {
          if (!deep_research_mode) {
            // Simple completion mode
            const systemMessage = { role: "system", content: getSystemPrompt(tools) }
            const allMessages = [systemMessage, ...messages]

            const response = await mockOpenAICall(allMessages)

            controller.enqueue(
              encoder.encode(
                `data: ${JSON.stringify({
                  type: "content",
                  content: response,
                })}\n\n`,
              ),
            )

            controller.enqueue(
              encoder.encode(
                `data: ${JSON.stringify({
                  type: "done",
                })}\n\n`,
              ),
            )

            controller.close()
            return
          }

          // Deep research mode
          const researchMessages = [{ role: "system", content: getSystemPrompt(tools) }, ...messages]

          const maxTurns = 10
          let turn = 0

          while (turn < maxTurns) {
            turn++

            // Get LLM response
            const response = await mockOpenAICall(researchMessages)

            // Parse response components
            const thinking = parseThinkingFromResponse(response)
            const toolCall = parseToolFromResponse(response)
            const finalAnswer = parseAnswerFromResponse(response)

            // Stream thinking if present
            if (thinking) {
              controller.enqueue(
                encoder.encode(
                  `data: ${JSON.stringify({
                    type: "thinking",
                    content: thinking,
                    turn,
                  })}\n\n`,
                ),
              )

              await new Promise((resolve) => setTimeout(resolve, 500))
            }

            // Handle tool call
            if (toolCall && tools.includes(toolCall.name)) {
              controller.enqueue(
                encoder.encode(
                  `data: ${JSON.stringify({
                    type: "tool_call",
                    tool: toolCall,
                    turn,
                  })}\n\n`,
                ),
              )

              await new Promise((resolve) => setTimeout(resolve, 500))

              try {
                const toolResult = await callTool(toolCall.name, toolCall.args)

                controller.enqueue(
                  encoder.encode(
                    `data: ${JSON.stringify({
                      type: "tool_result",
                      content: toolResult.length > 500 ? toolResult.substring(0, 500) + "..." : toolResult,
                      turn,
                    })}\n\n`,
                  ),
                )

                // Add tool result to conversation
                researchMessages.push({ role: "assistant", content: response })
                researchMessages.push({ role: "user", content: `Tool result: ${toolResult}` })

                await new Promise((resolve) => setTimeout(resolve, 500))
              } catch (error) {
                const errorMsg = `Tool execution error: ${error}`
                controller.enqueue(
                  encoder.encode(
                    `data: ${JSON.stringify({
                      type: "error",
                      content: errorMsg,
                    })}\n\n`,
                  ),
                )
                researchMessages.push({ role: "user", content: errorMsg })
              }
            }
            // Handle final answer
            else if (finalAnswer) {
              controller.enqueue(
                encoder.encode(
                  `data: ${JSON.stringify({
                    type: "final_answer",
                    content: finalAnswer,
                    turn,
                  })}\n\n`,
                ),
              )
              break
            }
            // If no tool call or answer, stream the raw content
            else {
              controller.enqueue(
                encoder.encode(
                  `data: ${JSON.stringify({
                    type: "content",
                    content: response,
                    turn,
                  })}\n\n`,
                ),
              )
              break
            }
          }

          controller.enqueue(
            encoder.encode(
              `data: ${JSON.stringify({
                type: "done",
              })}\n\n`,
            ),
          )

          controller.close()
        } catch (error) {
          controller.enqueue(
            encoder.encode(
              `data: ${JSON.stringify({
                type: "error",
                content: `Server error: ${error}`,
              })}\n\n`,
            ),
          )
          controller.close()
        }
      },
    })

    return new Response(stream, {
      headers: {
        "Content-Type": "text/plain",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    })
  } catch (error) {
    return new Response(JSON.stringify({ error: "Internal server error" }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    })
  }
}
