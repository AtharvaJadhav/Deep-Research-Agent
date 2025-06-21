"use client"

import { useState, useRef, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Send, Bot, User, Search, FileText, Cloud, Loader2, Mail, Sparkles, Paperclip } from "lucide-react"

interface Message {
  role: "user" | "assistant"
  content: string
}

interface StreamEvent {
  type: "content" | "thinking" | "start_answer" | "done" | "error" | "tool_call" | "tool_result" | "tool_error"
  content?: string
  tool?: string
  args?: any
  result?: string
  error?: string
}

const AVAILABLE_TOOLS = [
  { id: "search", name: "Web Search", icon: Search, description: "Search the web for information" },
  { id: "write_file", name: "File Writer", icon: FileText, description: "Write content to markdown files" },
  { id: "get_weather", name: "Weather", icon: Cloud, description: "Get weather information" },
  { id: "send_email", name: "Send Email", icon: Mail, description: "Send an email on your behalf" },
]

export default function DeepResearchAgent() {
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
  }, [messages, toolUsage, currentThinking])

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
    setToolUsage([]) // Clear previous tool usage

    try {
      const response = await fetch("http://localhost:8000/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
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
          content:
            "Sorry, there was an error connecting to the server. Please make sure the Python backend is running on http://localhost:8000",
        },
      ])
      setIsLoading(false)
      setCurrentThinking("")
    }
  }

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file || isLoading) return

    setIsLoading(true)
    setCurrentThinking(`Analyzing ${file.name}...`)
    setToolUsage([])
    setMessages(prev => [...prev, { role: 'user', content: `File Uploaded: ${file.name}` }])

    const formData = new FormData()
    formData.append("file", file)

    try {
      const response = await fetch("http://localhost:8000/upload", {
        method: "POST",
        body: formData,
      })
      if (!response.body) throw new Error("No response body")

      const reader = response.body.getReader()
      let assistantMessage = ""
      setMessages((prev) => [...prev, { role: "assistant", content: "" }])

      // Simplified stream handling for this example
      const processText = async () => {
        const { done, value } = await reader.read()
        if (done) {
          setIsLoading(false)
          setCurrentThinking("")
          return
        }
        const chunk = new TextDecoder().decode(value)
        for (const line of chunk.split("\n")) {
          if (line.startsWith("data: ")) {
            const data = JSON.parse(line.slice(6))
            if (data.type === 'content') {
              assistantMessage += data.content
              setMessages(prev => {
                const newMessages = [...prev]
                const lastMsg = newMessages[newMessages.length - 1]
                if (lastMsg && lastMsg.role === 'assistant') {
                  lastMsg.content = assistantMessage
                }
                return newMessages
              })
            } else if (data.type === 'done') {
              setIsLoading(false)
              setCurrentThinking("")
              return
            }
          }
        }
        await processText()
      }
      await processText()

    } catch (error) {
      console.error("File upload error:", error)
      setMessages((prev) => [...prev, { role: "assistant", content: "Sorry, there was an error analyzing the file." }])
      setIsLoading(false)
      setCurrentThinking("")
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = ""
      }
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

  return (
    <div className="font-sans min-h-screen bg-background text-foreground">
      <div className="container mx-auto grid grid-cols-12 gap-8 p-4 h-screen">
        {/* Settings Panel */}
        <div className="col-span-3">
          <Card className="h-full flex flex-col bg-secondary border-none">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <Sparkles className="w-5 h-5 text-primary" />
                Deep Research Agent
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
                {AVAILABLE_TOOLS.map((tool) => {
                  const IconComponent = tool.icon
                  return (
                    <div key={tool.id} className="flex items-start space-x-3">
                      <Checkbox
                        id={tool.id}
                        checked={selectedTools.includes(tool.id)}
                        onCheckedChange={() => handleToolToggle(tool.id)}
                        className="mt-1"
                      />
                      <div className="flex-1">
                        <Label htmlFor={tool.id} className="text-sm font-medium flex items-center gap-2">
                          <IconComponent className="w-4 h-4" />
                          {tool.name}
                        </Label>
                        <p className="text-xs text-muted-foreground">{tool.description}</p>
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
        <div className="col-span-9 flex flex-col h-full">
          <Card className="flex-1 flex flex-col border-none bg-secondary">
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
                  {isLoading && messages[messages.length - 1].role !== 'assistant' && (
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
                    className="w-full pr-16 resize-none bg-background rounded-lg"
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
                    onChange={handleFileUpload}
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
    </div>
  )
}
