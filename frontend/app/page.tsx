"use client"

import { useState, useRef, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import { Slider } from "@/components/ui/slider"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Send, Bot, User, Search, FileText, Cloud, Loader2, Mail, Sparkles, Paperclip, Download, Copy, Check } from "lucide-react"

interface Message {
  role: "user" | "assistant"
  content: string
}

interface StreamEvent {
  type: "content" | "thinking" | "start_answer" | "done" | "error" | "tool_call" | "tool_result" | "tool_error" | "research_status" | "research_plan" | "learning" | "iteration_complete" | "research_complete"
  content?: string
  tool?: string
  args?: any
  result?: string
  error?: string
  depth?: number
  iteration?: number
  queries?: string[]
  message?: string
  goals?: string[]
  reasoning?: string
  insight?: string
  source?: string
  goal?: string
  new_learnings?: number
  total_learnings?: number
  final_report?: string
  total_searches?: number
  final_depth?: number
}

interface ResearchSession {
  research_id: string
  status: string
  original_query: string
  research_goals: string[]
  current_depth: number
  max_depth: number
  current_breadth: number
  max_breadth: number
  iteration_count: number
  learnings: any[]
}

const BACKEND_URL = "http://localhost:8000"

export default function DeepResearchAgent() {
  const [mode, setMode] = useState<"research" | "chat">("research")

  // Research state
  const [researchQuery, setResearchQuery] = useState("")
  const [maxDepth, setMaxDepth] = useState([2])
  const [maxBreadth, setMaxBreadth] = useState([3])
  const [isResearching, setIsResearching] = useState(false)
  const [researchSession, setResearchSession] = useState<ResearchSession | null>(null)
  const [researchProgress, setResearchProgress] = useState<any[]>([])
  const [finalReport, setFinalReport] = useState("")
  const [researchStats, setResearchStats] = useState<any>(null)

  // Chat state (fallback)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [deepResearchMode, setDeepResearchMode] = useState(true)
  const [selectedTools, setSelectedTools] = useState<string[]>(["search", "write_file", "get_weather", "send_email"])
  const [currentThinking, setCurrentThinking] = useState("")
  const [toolUsage, setToolUsage] = useState<Array<{ type: string, tool: string, args?: any, result?: string, error?: string }>>([])

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, toolUsage, currentThinking, researchProgress])

  // Research functions
  const startResearch = async () => {
    if (!researchQuery.trim() || isResearching) return

    setIsResearching(true)
    setResearchProgress([])
    setFinalReport("")
    setResearchStats(null)

    try {
      // Create research session
      const sessionResponse = await fetch(`${BACKEND_URL}/research/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: researchQuery,
          max_depth: maxDepth[0],
          max_breadth: maxBreadth[0]
        })
      })

      if (!sessionResponse.ok) throw new Error("Failed to create research session")

      const sessionData = await sessionResponse.json()
      setResearchSession({
        research_id: sessionData.research_id,
        status: sessionData.status,
        original_query: researchQuery,
        research_goals: [],
        current_depth: 0,
        max_depth: maxDepth[0],
        current_breadth: 0,
        max_breadth: maxBreadth[0],
        iteration_count: 0,
        learnings: []
      })

      // Execute research
      const executeResponse = await fetch(`${BACKEND_URL}/research/${sessionData.research_id}/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tools: ["search"] })
      })

      if (!executeResponse.body) throw new Error("No response body")

      const reader = executeResponse.body.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split("\n")

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const event: StreamEvent = JSON.parse(line.slice(6))

              if (event.type === "done") {
                setIsResearching(false)
                break
              }

              if (event.type === "error") {
                setResearchProgress(prev => [...prev, { type: "error", content: event.content }])
                setIsResearching(false)
                break
              }

              // Handle research-specific events
              if (event.type === "research_status") {
                setResearchProgress(prev => [...prev, {
                  type: "status",
                  message: event.message,
                  depth: event.depth,
                  iteration: event.iteration,
                  queries: event.queries
                }])
              }

              if (event.type === "research_plan") {
                setResearchProgress(prev => [...prev, {
                  type: "plan",
                  goals: event.goals,
                  reasoning: event.reasoning
                }])
                if (researchSession) {
                  setResearchSession(prev => prev ? { ...prev, research_goals: event.goals || [] } : null)
                }
              }

              if (event.type === "learning") {
                setResearchProgress(prev => [...prev, {
                  type: "learning",
                  insight: event.insight,
                  source: event.source,
                  iteration: event.iteration,
                  goal: event.goal
                }])
              }

              if (event.type === "iteration_complete") {
                setResearchProgress(prev => [...prev, {
                  type: "iteration",
                  depth: event.depth,
                  new_learnings: event.new_learnings,
                  total_learnings: event.total_learnings
                }])
              }

              if (event.type === "research_complete") {
                setFinalReport(event.final_report || "")
                setResearchStats({
                  total_learnings: event.total_learnings,
                  total_searches: event.total_searches,
                  final_depth: event.final_depth
                })
                setIsResearching(false)
              }

            } catch (e) {
              console.error("Error parsing SSE data:", e)
            }
          }
        }
      }
    } catch (error) {
      console.error("Research error:", error)
      setResearchProgress(prev => [...prev, {
        type: "error",
        content: "Failed to start research. Please check if the backend is running."
      }])
      setIsResearching(false)
    }
  }

  const downloadReport = () => {
    if (!finalReport) return

    const blob = new Blob([finalReport], { type: "text/markdown" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `research-report-${Date.now()}.md`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const copyReport = async () => {
    if (!finalReport) return
    try {
      await navigator.clipboard.writeText(finalReport)
      // You could add a toast notification here
    } catch (err) {
      console.error("Failed to copy report:", err)
    }
  }

  // Chat functions (existing)
  const handleToolToggle = (toolId: string) => {
    setSelectedTools((prev) => (prev.includes(toolId) ? prev.filter((id) => id !== toolId) : [...prev, toolId]))
  }

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return

    const userMessage: Message = { role: "user", content: input }
    setMessages((prev) => [...prev, userMessage])
    setInput("")
    setIsLoading(true)
    setCurrentThinking("")
    setToolUsage([])

    try {
      const response = await fetch(`${BACKEND_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: [...messages, userMessage],
          tools: selectedTools,
          deep_research_mode: deepResearchMode,
        }),
      })

      if (!response.body) throw new Error("No response body")

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let assistantMessage = ""
      let currentAssistantMessageIndex = -1

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split("\n")

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const event: StreamEvent = JSON.parse(line.slice(6))

              if (event.type === "done") {
                setIsLoading(false)
                setCurrentThinking("")
                break
              }

              if (event.type === "error") {
                setMessages((prev) => [...prev, { role: "assistant", content: `Error: ${event.content}` }])
                setIsLoading(false)
                setCurrentThinking("")
                break
              }

              if (event.type === "thinking") {
                setCurrentThinking(event.content || "")
              }

              if (event.type === "tool_call") {
                setToolUsage(prev => [...prev, {
                  type: "call",
                  tool: event.tool || "",
                  args: event.args
                }])
              }

              if (event.type === "tool_result") {
                setToolUsage(prev => [...prev, {
                  type: "result",
                  tool: event.tool || "",
                  result: event.result
                }])
              }

              if (event.type === "tool_error") {
                setToolUsage(prev => [...prev, {
                  type: "error",
                  tool: event.tool || "",
                  error: event.error
                }])
              }

              if (event.type === "start_answer") {
                setCurrentThinking("")
                assistantMessage = ""
                setMessages((prev) => [...prev, { role: "assistant", content: "" }])
                currentAssistantMessageIndex = messages.length + 1
              }

              if (event.type === "content") {
                assistantMessage += event.content || ""
                setMessages((prev) => {
                  const newMessages = [...prev]
                  const lastMessage = newMessages[newMessages.length - 1]
                  if (lastMessage && lastMessage.role === "assistant") {
                    lastMessage.content = assistantMessage
                  }
                  return newMessages
                })
              }
            } catch (e) {
              console.error("Error parsing SSE data:", e)
            }
          }
        }
      }
    } catch (error) {
      console.error("Error:", error)
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Sorry, there was an error connecting to the server. Please make sure the Python backend is running.",
        },
      ])
      setIsLoading(false)
      setCurrentThinking("")
    }
  }

  const renderMessage = (message: Message, index: number) => {
    const isUser = message.role === "user"
    return (
      <div key={index} className={`flex items-start gap-4 ${isUser ? "justify-end" : ""}`}>
        {!isUser && (
          <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center flex-shrink-0">
            <Bot className="w-5 h-5 text-secondary-foreground" />
          </div>
        )}
        <div className={`p-4 rounded-lg max-w-[80%] ${isUser ? "bg-primary text-primary-foreground" : "bg-secondary"}`}>
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        </div>
        {isUser && (
          <div className="w-8 h-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center flex-shrink-0">
            <User className="w-5 h-5" />
          </div>
        )}
      </div>
    )
  }

  const renderResearchProgress = (item: any, index: number) => {
    switch (item.type) {
      case "status":
        return (
          <div key={index} className="flex items-center gap-3 p-3 bg-blue-50 rounded-lg">
            <Loader2 className="w-4 h-4 animate-spin text-blue-600" />
            <div>
              <p className="text-sm font-medium text-blue-900">{item.message}</p>
              {item.depth && (
                <p className="text-xs text-blue-700">Depth {item.depth}, Iteration {item.iteration}</p>
              )}
              {item.queries && (
                <div className="mt-2 space-y-1">
                  {item.queries.map((query: string, i: number) => (
                    <Badge key={i} variant="outline" className="text-xs">
                      {query}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </div>
        )

      case "plan":
        return (
          <div key={index} className="p-4 bg-green-50 rounded-lg">
            <h4 className="font-medium text-green-900 mb-2">Research Plan</h4>
            <div className="space-y-2">
              {item.goals?.map((goal: string, i: number) => (
                <div key={i} className="flex items-center gap-2">
                  <div className="w-2 h-2 bg-green-500 rounded-full" />
                  <span className="text-sm text-green-800">{goal}</span>
                </div>
              ))}
            </div>
            {item.reasoning && (
              <p className="text-xs text-green-700 mt-2">{item.reasoning}</p>
            )}
          </div>
        )

      case "learning":
        return (
          <div key={index} className="p-3 bg-yellow-50 rounded-lg">
            <div className="flex items-start gap-2">
              <Search className="w-4 h-4 text-yellow-600 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm text-yellow-900">{item.insight}</p>
                {item.source && (
                  <p className="text-xs text-yellow-700 mt-1">Source: {item.source}</p>
                )}
                <div className="flex gap-2 mt-2">
                  <Badge variant="outline" className="text-xs">Iteration {item.iteration}</Badge>
                  {item.goal && <Badge variant="outline" className="text-xs">{item.goal}</Badge>}
                </div>
              </div>
            </div>
          </div>
        )

      case "iteration":
        return (
          <div key={index} className="p-3 bg-purple-50 rounded-lg">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-purple-500 rounded-full" />
              <span className="text-sm font-medium text-purple-900">
                Iteration {item.depth} Complete
              </span>
            </div>
            <p className="text-xs text-purple-700 mt-1">
              {item.new_learnings} new insights, {item.total_learnings} total
            </p>
          </div>
        )

      case "error":
        return (
          <div key={index} className="p-3 bg-red-50 rounded-lg">
            <p className="text-sm text-red-900">{item.content}</p>
          </div>
        )

      default:
        return null
    }
  }

  return (
    <div className="font-sans min-h-screen bg-background text-foreground">
      <div className="container mx-auto p-4">
        <div className="mb-6">
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <Sparkles className="w-8 h-8 text-primary" />
            Deep Research Agent
          </h1>
          <p className="text-muted-foreground mt-2">
            AI-powered research system that discovers insights through iterative exploration
          </p>
        </div>

        <Tabs value={mode} onValueChange={(value) => setMode(value as "research" | "chat")}>
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="research">Research Mode</TabsTrigger>
            <TabsTrigger value="chat">Chat Mode</TabsTrigger>
          </TabsList>

          <TabsContent value="research" className="space-y-6">
            {/* Research Form */}
            <Card>
              <CardHeader>
                <CardTitle>Start Deep Research</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label htmlFor="query">Research Query</Label>
                  <Textarea
                    id="query"
                    value={researchQuery}
                    onChange={(e) => setResearchQuery(e.target.value)}
                    placeholder="What would you like me to research? (e.g., 'AI trends 2025', 'Climate change solutions', 'Quantum computing applications')"
                    className="min-h-[100px]"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>Research Depth: {maxDepth[0]}</Label>
                    <Slider
                      value={maxDepth}
                      onValueChange={setMaxDepth}
                      max={3}
                      min={1}
                      step={1}
                      className="mt-2"
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      How deep to explore each research direction
                    </p>
                  </div>
                  <div>
                    <Label>Research Breadth: {maxBreadth[0]}</Label>
                    <Slider
                      value={maxBreadth}
                      onValueChange={setMaxBreadth}
                      max={5}
                      min={2}
                      step={1}
                      className="mt-2"
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      How many parallel searches per iteration
                    </p>
                  </div>
                </div>

                <Button
                  onClick={startResearch}
                  disabled={isResearching || !researchQuery.trim()}
                  className="w-full"
                >
                  {isResearching ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Researching...
                    </>
                  ) : (
                    <>
                      <Search className="w-4 h-4 mr-2" />
                      Start Research
                    </>
                  )}
                </Button>
              </CardContent>
            </Card>

            {/* Research Progress */}
            {researchProgress.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Research Progress</CardTitle>
                </CardHeader>
                <CardContent>
                  <ScrollArea className="h-[400px]">
                    <div className="space-y-3 pr-4">
                      {researchProgress.map(renderResearchProgress)}
                    </div>
                  </ScrollArea>
                </CardContent>
              </Card>
            )}

            {/* Final Report */}
            {finalReport && (
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle>Research Report</CardTitle>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" onClick={copyReport}>
                        <Copy className="w-4 h-4 mr-2" />
                        Copy
                      </Button>
                      <Button variant="outline" size="sm" onClick={downloadReport}>
                        <Download className="w-4 h-4 mr-2" />
                        Download
                      </Button>
                    </div>
                  </div>
                  {researchStats && (
                    <div className="flex gap-4 text-sm text-muted-foreground">
                      <span>Total Learnings: {researchStats.total_learnings}</span>
                      <span>Total Searches: {researchStats.total_searches}</span>
                      <span>Final Depth: {researchStats.final_depth}</span>
                    </div>
                  )}
                </CardHeader>
                <CardContent>
                  <div className="prose prose-sm max-w-none">
                    <div dangerouslySetInnerHTML={{ __html: finalReport.replace(/\n/g, '<br/>') }} />
                  </div>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          <TabsContent value="chat" className="space-y-6">
            <div className="grid grid-cols-12 gap-8">
              {/* Settings Panel */}
              <div className="col-span-3">
                <Card className="h-full flex flex-col">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-lg">
                      <Sparkles className="w-5 h-5 text-primary" />
                      Chat Settings
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="flex-1 flex flex-col space-y-6">
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <Label htmlFor="deep-research" className="text-sm font-medium">
                          Deep Research Mode
                        </Label>
                        <Switch id="deep-research" checked={deepResearchMode} onCheckedChange={setDeepResearchMode} />
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {deepResearchMode
                          ? "Agent will use tools iteratively until complete."
                          : "Simple completion without tool loops."}
                      </p>
                    </div>

                    <Separator />

                    <div className="space-y-4">
                      <Label className="text-sm font-medium">Available Tools</Label>
                      {[
                        { id: "search", name: "Web Search", icon: Search },
                        { id: "write_file", name: "File Writer", icon: FileText },
                        { id: "get_weather", name: "Weather", icon: Cloud },
                        { id: "send_email", name: "Send Email", icon: Mail },
                      ].map((tool) => {
                        const IconComponent = tool.icon
                        return (
                          <div key={tool.id} className="flex items-start space-x-3">
                            <input
                              type="checkbox"
                              id={tool.id}
                              checked={selectedTools.includes(tool.id)}
                              onChange={() => handleToolToggle(tool.id)}
                              className="mt-1"
                            />
                            <div className="flex-1">
                              <Label htmlFor={tool.id} className="text-sm font-medium flex items-center gap-2">
                                <IconComponent className="w-4 h-4" />
                                {tool.name}
                              </Label>
                            </div>
                          </div>
                        )
                      })}
                    </div>

                    {(isLoading && currentThinking) && (
                      <>
                        <Separator />
                        <div className="space-y-3">
                          <Label className="text-sm font-medium">Status</Label>
                          <div className="flex items-center space-x-2 text-sm text-muted-foreground">
                            <Loader2 className="w-4 h-4 animate-spin" />
                            <span>{currentThinking}</span>
                          </div>
                        </div>
                      </>
                    )}

                    {toolUsage.length > 0 && (
                      <>
                        <Separator />
                        <div className="space-y-3">
                          <Label className="text-sm font-medium">Tool Usage</Label>
                          <ScrollArea className="h-40">
                            <div className="space-y-2 pr-4">
                              {toolUsage.map((usage, index) => (
                                <div key={index} className="text-xs p-2 bg-background rounded-lg border">
                                  {usage.type === "call" && (
                                    <div className="flex items-center gap-2 font-medium">
                                      <Search className="w-3 h-3 text-blue-400" />
                                      <span>Using {usage.tool}</span>
                                    </div>
                                  )}
                                  {usage.type === "result" && (
                                    <div className="flex items-center gap-2 text-green-400">
                                      <FileText className="w-3 h-3" />
                                      <span>{usage.tool} completed</span>
                                    </div>
                                  )}
                                  {usage.type === "error" && (
                                    <div className="flex items-center gap-2 text-red-400">
                                      <span className="font-bold">!</span>
                                      <span>{usage.tool} failed</span>
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          </ScrollArea>
                        </div>
                      </>
                    )}
                  </CardContent>
                </Card>
              </div>

              {/* Chat Panel */}
              <div className="col-span-9 flex flex-col h-[600px]">
                <Card className="flex-1 flex flex-col">
                  <CardHeader>
                    <CardTitle className="text-lg">Research Chat</CardTitle>
                  </CardHeader>

                  <CardContent className="flex-1 flex flex-col p-0">
                    <ScrollArea className="flex-1 p-6">
                      <div className="space-y-6">
                        {messages.length === 0 && (
                          <div className="text-center text-muted-foreground py-16">
                            <Bot className="w-12 h-12 mx-auto mb-4" />
                            <h3 className="text-lg font-medium">Start a conversation</h3>
                            <p className="text-sm mt-1">Ask me to research anything, and I'll do my best to help.</p>
                          </div>
                        )}
                        {messages.map(renderMessage)}
                        {isLoading && messages[messages.length - 1]?.role !== 'assistant' && (
                          <div className="flex items-start gap-4">
                            <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center flex-shrink-0">
                              <Bot className="w-5 h-5 text-secondary-foreground" />
                            </div>
                            <div className="p-4 rounded-lg bg-secondary flex items-center">
                              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                            </div>
                          </div>
                        )}
                      </div>
                      <div ref={messagesEndRef} />
                    </ScrollArea>

                    <div className="border-t border-border p-4">
                      <div className="relative">
                        <Textarea
                          value={input}
                          onChange={(e) => setInput(e.target.value)}
                          placeholder="Ask me to research anything..."
                          className="w-full pr-16 resize-none"
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && !e.shiftKey) {
                              e.preventDefault()
                              sendMessage()
                            }
                          }}
                        />
                        <input
                          type="file"
                          ref={fileInputRef}
                          onChange={() => { }} // Simplified for this example
                          className="hidden"
                          accept=".txt,.md,.py,.json,.csv"
                          disabled={isLoading}
                        />
                        <Button variant="ghost" size="icon" className="absolute top-1/2 right-20 -translate-y-1/2" onClick={() => fileInputRef.current?.click()} disabled={isLoading}>
                          <Paperclip className="w-5 h-5" />
                        </Button>
                        <Button onClick={sendMessage} disabled={isLoading || !input.trim()} className="absolute top-1/2 right-3 -translate-y-1/2 rounded-full w-10 h-10 p-2">
                          {isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}
