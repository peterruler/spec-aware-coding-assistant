import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import DOMPurify from "dompurify";

type Role = "user" | "assistant" | "system";

type ChatMessage = {
  id: string;
  role: Role;
  content: string;
  html?: string;
};

type ApiChatMessage = {
  role: Role;
  content: string;
};

type AppConfig = {
  app_name: string;
  vllm_base_url: string;
  default_model: string;
  default_provider_id: string;
  providers: ProviderConfig[];
  default_spec_source_id: string;
  spec_sources: SpecSourceConfig[];
  default_temperature: number;
  default_max_tokens: number;
  default_num_ctx: number;
  min_reserved_output_tokens: number;
  spec_prompt_token_budget: number;
  spec_prompt_max_context_fraction: number;
};

type ProviderConfig = {
  id: string;
  label: string;
  runtime: string;
  base_url: string;
  model: string;
  description: string;
};

type SpecSourceConfig = {
  id: string;
  label: string;
  root_path: string;
  exists: boolean;
  description: string;
};

type BackendStatus = {
  status: "ok" | "error";
  provider_id: string;
  provider_label: string;
  base_url: string;
  model: string;
  models: string[];
  detail?: string;
};

type SpecScanResponse = {
  spec_source_id: string;
  spec_source_label: string;
  spec_root: string;
  spec_root_exists: boolean;
  note: string;
  total_estimated_tokens: number;
  files: Array<{
    path: string;
    kind: string;
    chars: number;
    estimated_tokens: number;
    used_in_prompt: boolean;
    notes: string;
  }>;
};

type ChatResponse = {
  assistant_text: string;
  assistant_html: string;
  token_report: string;
  saved_file?: string | null;
};

type ApiEndpoint = {
  id: string;
  label: string;
  baseUrl: string;
  description: string;
};

const DEFAULT_API_BASE_URL = normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL || "");
const DGX_SPARK_API_BASE_URL = "http://192.168.1.196:8080";
const API_ENDPOINTS: ApiEndpoint[] = [
  {
    id: "m1_local",
    label: "M1 Mac local API",
    baseUrl: DEFAULT_API_BASE_URL,
    description: DEFAULT_API_BASE_URL || "Use the Vite proxy to reach http://127.0.0.1:8080."
  },
  {
    id: "dgx_spark_lan",
    label: "DGX Spark LAN API",
    baseUrl: DGX_SPARK_API_BASE_URL,
    description: "Use the FastAPI backend running on the DGX Spark at http://192.168.1.196:8080."
  }
];

const AUTO_TEST_PROMPT = `You are given QScript specification files in this prompt. Generate a complete single-file quiz application using only the QScript language described in those specs.

The app must be a quiz about TypeScript.

Critical rules:
1. The generated program must be QScript only.
2. Do not write the app in TypeScript.
3. Do not output JavaScript, HTML, Python, React, or pseudocode.
4. TypeScript is only the subject matter of the quiz.
5. TypeScript code snippets are allowed only inside question text, answer choices, or explanations.
6. All functions must live inside the FhClass block.
7. The FhClass declaration must be written as SET FORMCLASS FhClass [ and its square bracket block must wrap the entire following function list.
8. Do not close the FhClass square bracket block until after the final function.
9. oninitshow is the start trigger function.
10. Follow the provided QScript specs exactly.
11. Output only the final QScript source code.

App behavior:
- Present at least 20 TypeScript quiz questions.
- Provide multiple-choice answers.
- Accept the user's answer.
- Check correctness.
- Display feedback after each question.
- Track score.
- Display the final score at the end.

Generate the complete QScript file now.`;

function normalizeBaseUrl(value: string): string {
  return value.trim().replace(/\/+$/, "");
}

function makeId(): string {
  return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function codeHtml(source: string): string {
  const content = source.trim() ? source : "[generating...]";
  return `<pre class="generated-code"><code>${escapeHtml(content)}</code></pre>`;
}

function sanitize(html: string): string {
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ["pre", "code", "div", "span", "p", "br"],
    ALLOWED_ATTR: ["class"]
  });
}

export default function App() {
  const [apiBaseUrl, setApiBaseUrl] = useState(() =>
    normalizeBaseUrl(localStorage.getItem("qscript_api_base_url") ?? DEFAULT_API_BASE_URL)
  );
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [prompt, setPrompt] = useState("");
  const [selectedProviderId, setSelectedProviderId] = useState("");
  const [selectedSpecSourceId, setSelectedSpecSourceId] = useState("");
  const [model, setModel] = useState("");
  const [temperature, setTemperature] = useState(0.2);
  const [maxTokens, setMaxTokens] = useState(8192);
  const [numCtx, setNumCtx] = useState(32768);
  const [reserveTokens, setReserveTokens] = useState(8192);
  const [status, setStatus] = useState("Ready");
  const [backendStatus, setBackendStatus] = useState<BackendStatus | null>(null);
  const [specScan, setSpecScan] = useState<SpecScanResponse | null>(null);
  const [tokenReport, setTokenReport] = useState("");
  const [savedFile, setSavedFile] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const chatWindowRef = useRef<HTMLDivElement | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const copyResetTimerRef = useRef<number | null>(null);

  const apiHistory: ApiChatMessage[] = useMemo(
    () =>
      messages.map((message) => ({
        role: message.role,
        content: message.content
      })),
    [messages]
  );

  const currentProvider = useMemo(
    () => config?.providers.find((provider) => provider.id === selectedProviderId) ?? null,
    [config, selectedProviderId]
  );

  const currentSpecSource = useMemo(
    () => config?.spec_sources.find((source) => source.id === selectedSpecSourceId) ?? null,
    [config, selectedSpecSourceId]
  );

  const currentApiEndpoint = useMemo(
    () => API_ENDPOINTS.find((endpoint) => endpoint.baseUrl === apiBaseUrl) ?? null,
    [apiBaseUrl]
  );
  const apiLocationLabel = currentApiEndpoint?.label ?? (apiBaseUrl || "M1 Mac local API");

  useEffect(() => {
    void loadConfig();
  }, [apiBaseUrl]);

  useEffect(() => {
    const chatWindow = chatWindowRef.current;
    if (chatWindow) {
      chatWindow.scrollTo({ top: chatWindow.scrollHeight, behavior: "smooth" });
    } else {
      chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages]);

  useEffect(() => {
    if (selectedSpecSourceId) {
      void scanSpecs(selectedSpecSourceId);
    }
  }, [selectedSpecSourceId, apiBaseUrl]);

  useEffect(() => {
    return () => {
      if (copyResetTimerRef.current !== null) {
        window.clearTimeout(copyResetTimerRef.current);
      }
    };
  }, []);

  function apiUrl(path: string): string {
    return `${apiBaseUrl}${path}`;
  }

  async function loadConfig() {
    try {
      setStatus(`Loading API config from ${apiBaseUrl || "local M1 proxy"}...`);
      const response = await fetch(apiUrl("/api/config"));
      if (!response.ok) throw new Error(await response.text());
      const data = (await response.json()) as AppConfig;
      setConfig(data);
      const providerId = data.default_provider_id || data.providers[0]?.id || "";
      const provider = data.providers.find((item) => item.id === providerId) ?? data.providers[0];
      setSelectedProviderId(providerId);
      setSelectedSpecSourceId(data.default_spec_source_id || data.spec_sources[0]?.id || "");
      setModel(provider?.model || data.default_model);
      setTemperature(data.default_temperature);
      setMaxTokens(data.default_max_tokens);
      setNumCtx(data.default_num_ctx);
      setReserveTokens(data.min_reserved_output_tokens);
      setBackendStatus(null);
      setStatus(`Connected to ${apiLocationLabel}`);
      void scanSpecs(data.default_spec_source_id || data.spec_sources[0]?.id || "");
    } catch (error) {
      setConfig(null);
      setBackendStatus(null);
      setSpecScan(null);
      setStatus(`Config error: ${String(error)}`);
    }
  }

  async function checkBackend() {
    setStatus("Checking selected backend...");
    try {
      const params = new URLSearchParams();
      if (selectedProviderId) params.set("provider_id", selectedProviderId);
      const response = await fetch(apiUrl(`/api/backend?${params.toString()}`));
      if (!response.ok) throw new Error(await response.text());
      const data = (await response.json()) as BackendStatus;
      setBackendStatus(data);
      setStatus(data.status === "ok" ? `${data.provider_label} is reachable` : `${data.provider_label} returned an error`);
    } catch (error) {
      setBackendStatus(null);
      setStatus(`Backend check failed: ${String(error)}`);
    }
  }

  async function scanSpecs(specSourceId = selectedSpecSourceId) {
    try {
      const params = new URLSearchParams();
      if (specSourceId) params.set("spec_source_id", specSourceId);
      const response = await fetch(apiUrl(`/api/specs?${params.toString()}`));
      if (!response.ok) throw new Error(await response.text());
      setSpecScan((await response.json()) as SpecScanResponse);
    } catch (error) {
      setStatus(`Spec scan failed: ${String(error)}`);
    }
  }

  async function submitPrompt(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = prompt.trim();
    if (!message || isSending) return;

    const userMessage: ChatMessage = {
      id: makeId(),
      role: "user",
      content: message
    };
    const assistantId = makeId();
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      html: codeHtml("")
    };

    setMessages((current) => [...current, userMessage, assistantMessage]);
    setPrompt("");
    setIsSending(true);
    setStatus("Generating...");
    setSavedFile(null);

    try {
      const response = await fetch(apiUrl("/api/chat/stream"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          history: apiHistory,
          provider_id: selectedProviderId,
          spec_source_id: selectedSpecSourceId,
          model,
          temperature,
          max_tokens: maxTokens,
          num_ctx: numCtx,
          reserve_output_tokens: reserveTokens
        })
      });

      if (!response.ok || !response.body) {
        throw new Error(await response.text());
      }

      await readEventStream(response.body, {
        onMeta: (payload) => {
          if (typeof payload.token_report === "string") {
            setTokenReport(payload.token_report);
          }
        },
        onDelta: (delta) => {
          updateAssistant(assistantId, (previous) => {
            const content = previous.content + delta;
            return { ...previous, content, html: codeHtml(content) };
          });
        },
        onFinal: (payload) => {
          const finalPayload = payload as ChatResponse;
          updateAssistant(assistantId, (previous) => ({
            ...previous,
            content: finalPayload.assistant_text,
            html: finalPayload.assistant_html
          }));
          setTokenReport(finalPayload.token_report);
          setSavedFile(finalPayload.saved_file ?? null);
          setStatus("Complete");
        },
        onError: (payload) => {
          const messageText = typeof payload.message === "string" ? payload.message : "Unknown streaming error";
          updateAssistant(assistantId, (previous) => ({
            ...previous,
            content: messageText,
            html: `<div class="assistant-error">${escapeHtml(messageText)}</div>`
          }));
          setStatus("Generation failed");
        }
      });
    } catch (error) {
      updateAssistant(assistantId, (previous) => ({
        ...previous,
        content: String(error),
        html: `<div class="assistant-error">${escapeHtml(String(error))}</div>`
      }));
      setStatus("Generation failed");
    } finally {
      setIsSending(false);
    }
  }

  async function continueOutput() {
    if (isSending || messages.length === 0) return;
    setIsSending(true);
    setStatus("Continuing...");

    try {
      const response = await fetch(apiUrl("/api/chat/continue"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          history: apiHistory,
          provider_id: selectedProviderId,
          spec_source_id: selectedSpecSourceId,
          model,
          temperature,
          max_tokens: maxTokens
        })
      });
      if (!response.ok) throw new Error(await response.text());
      const data = (await response.json()) as ChatResponse;
      const continued: ChatMessage = {
        id: makeId(),
        role: "assistant",
        content: data.assistant_text,
        html: data.assistant_html
      };
      setMessages((current) => [...current, continued]);
      setTokenReport(data.token_report);
      setSavedFile(data.saved_file ?? null);
      setStatus("Complete");
    } catch (error) {
      setStatus(`Continue failed: ${String(error)}`);
    } finally {
      setIsSending(false);
    }
  }

  function updateAssistant(id: string, updater: (message: ChatMessage) => ChatMessage) {
    setMessages((current) =>
      current.map((message) => (message.id === id ? updater(message) : message))
    );
  }

  function clearChat() {
    setMessages([]);
    setTokenReport("");
    setSavedFile(null);
    setStatus("Ready");
  }

  function selectApiEndpoint(endpoint: ApiEndpoint) {
    const nextBaseUrl = normalizeBaseUrl(endpoint.baseUrl);
    localStorage.setItem("qscript_api_base_url", nextBaseUrl);
    setApiBaseUrl(nextBaseUrl);
    setConfig(null);
    setBackendStatus(null);
    setSpecScan(null);
    setTokenReport("");
    setSavedFile(null);
    setStatus(`Switching to ${endpoint.label}`);
  }

  function selectProvider(provider: ProviderConfig) {
    setSelectedProviderId(provider.id);
    setModel(provider.model);
    setBackendStatus(null);
    setStatus(`Selected ${provider.label}`);
  }

  function selectSpecSource(source: SpecSourceConfig) {
    setSelectedSpecSourceId(source.id);
    setSpecScan(null);
    setStatus(`Selected ${source.label}`);
  }

  function fillAutoTestPrompt() {
    setPrompt(AUTO_TEST_PROMPT);
    setStatus("Auto test prompt loaded");
  }

  async function copyGeneratedSource(message: ChatMessage) {
    const source = message.content.trim();
    if (!source) return;

    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(source);
      } else {
        fallbackCopyText(source);
      }
      setCopiedMessageId(message.id);
      setStatus("Source copied to clipboard");
      if (copyResetTimerRef.current !== null) {
        window.clearTimeout(copyResetTimerRef.current);
      }
      copyResetTimerRef.current = window.setTimeout(() => {
        setCopiedMessageId(null);
      }, 1600);
    } catch (error) {
      setStatus(`Copy failed: ${String(error)}`);
    }
  }

  function fallbackCopyText(source: string) {
    const textarea = document.createElement("textarea");
    textarea.value = source;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();
    const copied = document.execCommand("copy");
    document.body.removeChild(textarea);
    if (!copied) {
      throw new Error("Clipboard copy is not available");
    }
  }

  return (
    <main className="app-shell">
      <section className="top-bar">
        <div>
          <h1>QScript Coding Assistant</h1>
          <p>
            API: {apiLocationLabel}
            {currentProvider ? ` | Model: ${currentProvider.label} -> ${currentProvider.base_url}` : " | Loading configuration..."}
          </p>
        </div>
        <div className="status-pill">{status}</div>
      </section>

      <section className="workspace">
        <aside className="control-panel" aria-label="Assistant controls">
          <section className="provider-switcher" aria-label="API endpoint">
            <h2>API Location</h2>
            <div className="provider-buttons">
              {API_ENDPOINTS.map((endpoint) => (
                <button
                  type="button"
                  key={endpoint.id}
                  className={endpoint.baseUrl === apiBaseUrl ? "provider-button active" : "provider-button"}
                  onClick={() => selectApiEndpoint(endpoint)}
                  disabled={isSending}
                >
                  <span>{endpoint.baseUrl || "same-origin /api proxy"}</span>
                  <strong>{endpoint.label}</strong>
                </button>
              ))}
            </div>
            <p className="provider-description">
              {currentApiEndpoint?.description ?? apiBaseUrl}
            </p>
          </section>

          {config && (
            <section className="provider-switcher" aria-label="Backend provider">
              <h2>Backend Target</h2>
              <div className="provider-buttons">
                {config.providers.map((provider) => (
                  <button
                    type="button"
                    key={provider.id}
                    className={provider.id === selectedProviderId ? "provider-button active" : "provider-button"}
                    onClick={() => selectProvider(provider)}
                    disabled={isSending}
                  >
                    <span>{provider.runtime === "vllm" ? "DGX Spark" : "M1 Mac"}</span>
                    <strong>{provider.runtime === "vllm" ? "vLLM + Qwen" : "Ollama + Qwen Coder"}</strong>
                  </button>
                ))}
              </div>
              {currentProvider && (
                <p className="provider-description">
                  {currentProvider.description}
                </p>
              )}
            </section>
          )}

          {config && (
            <section className="provider-switcher" aria-label="Spec source">
              <h2>Spec Source</h2>
              <div className="provider-buttons">
                {config.spec_sources.map((source) => (
                  <button
                    type="button"
                    key={source.id}
                    className={source.id === selectedSpecSourceId ? "provider-button active" : "provider-button"}
                    onClick={() => selectSpecSource(source)}
                    disabled={isSending}
                  >
                    <span>{source.exists ? "Available" : "Not found"}</span>
                    <strong>{source.id === "usb_untitled_spec" ? "External Device" : "Project Local"}</strong>
                  </button>
                ))}
              </div>
              {currentSpecSource && (
                <p className="provider-description">
                  {currentSpecSource.description} Path: {currentSpecSource.root_path}
                </p>
              )}
            </section>
          )}

          <label>
            Model
            <input value={model} onChange={(event) => setModel(event.target.value)} />
          </label>

          <div className="field-grid">
            <label>
              Temperature
              <input
                type="number"
                min="0"
                max="2"
                step="0.05"
                value={temperature}
                onChange={(event) => setTemperature(Number(event.target.value))}
              />
            </label>
            <label>
              Max tokens
              <input
                type="number"
                min="1"
                value={maxTokens}
                onChange={(event) => setMaxTokens(Number(event.target.value))}
              />
            </label>
            <label>
              Context
              <input
                type="number"
                min="4096"
                value={numCtx}
                onChange={(event) => setNumCtx(Number(event.target.value))}
              />
            </label>
            <label>
              Reserve
              <input
                type="number"
                min="512"
                value={reserveTokens}
                onChange={(event) => setReserveTokens(Number(event.target.value))}
              />
            </label>
          </div>

          <div className="button-row">
            <button type="button" onClick={checkBackend}>Check backend</button>
            <button type="button" onClick={() => scanSpecs()}>Scan specs</button>
          </div>
          <button type="button" onClick={fillAutoTestPrompt} disabled={isSending}>
            Auto test prompt
          </button>
          <div className="button-row">
            <button type="button" onClick={continueOutput} disabled={isSending || messages.length === 0}>
              Continue
            </button>
            <button type="button" onClick={clearChat} disabled={isSending || messages.length === 0}>
              Clear
            </button>
          </div>

          {backendStatus && (
            <section className="info-block">
              <h2>Backend</h2>
              <p>Target: {backendStatus.provider_label}</p>
              <p>URL: {backendStatus.base_url}</p>
              <p>Model: {backendStatus.model}</p>
              <p>Status: {backendStatus.status}</p>
              <p>Models: {backendStatus.models.length || 0}</p>
              {backendStatus.detail && <p>{backendStatus.detail}</p>}
            </section>
          )}

          {specScan && (
            <section className="info-block">
              <h2>Spec Scan</h2>
              <p>Source: {specScan.spec_source_label}</p>
              <p>Root: {specScan.spec_root}</p>
              <p>{specScan.note}</p>
              {config && (
                <p>
                  Prompt spec budget: {config.spec_prompt_token_budget} max, capped at{" "}
                  {Math.round(config.spec_prompt_max_context_fraction * 100)}% of context
                </p>
              )}
              <p>Total tokens: {specScan.total_estimated_tokens}</p>
              <p>Files: {specScan.files.length}</p>
            </section>
          )}

          {savedFile && (
            <section className="info-block">
              <h2>Saved File</h2>
              <p>{savedFile}</p>
            </section>
          )}
        </aside>

        <section className="chat-panel" aria-label="Chat">
          <div className="chat-window" ref={chatWindowRef}>
            {messages.length === 0 && (
              <div className="empty-state">
                Ask for a complete QScript or source file generated from the local specs.
              </div>
            )}

            {messages.map((message) => (
              <article className={`message ${message.role}`} key={message.id}>
                <div className="message-role">{message.role}</div>
                {message.role === "assistant" ? (
                  <div className="message-body assistant-output">
                    <div className="message-actions">
                      <button
                        type="button"
                        className="copy-source-button"
                        onClick={() => void copyGeneratedSource(message)}
                        disabled={!message.content.trim()}
                      >
                        {copiedMessageId === message.id ? "Copied" : "Copy source"}
                      </button>
                    </div>
                    <div
                      className="html-output"
                      dangerouslySetInnerHTML={{ __html: sanitize(message.html || codeHtml(message.content)) }}
                    />
                  </div>
                ) : (
                  <div className="message-body plain-text">{message.content}</div>
                )}
              </article>
            ))}
            <div ref={chatEndRef} />
          </div>

          <form className="prompt-form" onSubmit={submitPrompt}>
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="Ask for code generated from the local specification files..."
              rows={5}
              disabled={isSending}
            />
            <button type="submit" disabled={isSending || !prompt.trim()}>
              {isSending ? "Generating" : "Send"}
            </button>
          </form>
        </section>

        <aside className="report-panel" aria-label="Token report">
          <h2>Prompt Report</h2>
          <pre>{tokenReport || "Prompt budget details appear after a request."}</pre>
        </aside>
      </section>
    </main>
  );
}

type StreamHandlers = {
  onMeta: (payload: Record<string, unknown>) => void;
  onDelta: (delta: string) => void;
  onFinal: (payload: Record<string, unknown>) => void;
  onError: (payload: Record<string, unknown>) => void;
};

async function readEventStream(body: ReadableStream<Uint8Array>, handlers: StreamHandlers) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";

    for (const rawEvent of events) {
      const parsed = parseSseEvent(rawEvent);
      if (!parsed) continue;
      if (parsed.event === "meta") handlers.onMeta(parsed.payload);
      if (parsed.event === "delta" && typeof parsed.payload.text === "string") {
        handlers.onDelta(parsed.payload.text);
      }
      if (parsed.event === "final") handlers.onFinal(parsed.payload);
      if (parsed.event === "error") handlers.onError(parsed.payload);
    }
  }
}

function parseSseEvent(rawEvent: string): { event: string; payload: Record<string, unknown> } | null {
  const eventLine = rawEvent.split("\n").find((line) => line.startsWith("event:"));
  const dataLine = rawEvent.split("\n").find((line) => line.startsWith("data:"));
  if (!eventLine || !dataLine) return null;

  const event = eventLine.replace("event:", "").trim();
  const data = dataLine.replace("data:", "").trim();
  try {
    return { event, payload: JSON.parse(data) as Record<string, unknown> };
  } catch {
    return null;
  }
}
