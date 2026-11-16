"""Adaptadores de LLM com a mesma interface: uma sessão com histórico próprio.

O agente só conhece `Session.send` e `Session.send_tool_results`; trocar de
provedor é mudar LLM_PROVIDER no .env (ollama | gemini | anthropic).
"""
import json
import os
import urllib.request
from dataclasses import dataclass, field

DEFAULTS = {"ollama": "qwen2.5:3b", "gemini": "gemini-2.5-flash", "anthropic": "claude-haiku-5-5"}


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class Turn:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


class AnthropicSession:
    def __init__(self, system: str, tools: list[dict], model: str) -> None:
        import anthropic

        self.client, self.system, self.model = anthropic.Anthropic(), system, model
        self.tools, self.messages = tools, []

    def _call(self) -> Turn:
        r = self.client.messages.create(model=self.model, max_tokens=1500, system=self.system,
                                        tools=self.tools, messages=self.messages)
        self.messages.append({"role": "assistant", "content": r.content})
        return Turn(
            text="".join(b.text for b in r.content if b.type == "text"),
            tool_calls=[ToolCall(b.id, b.name, b.input) for b in r.content if b.type == "tool_use"],
            stop_reason=r.stop_reason, input_tokens=r.usage.input_tokens,
            output_tokens=r.usage.output_tokens)

    def send(self, text: str) -> Turn:
        self.messages.append({"role": "user", "content": text})
        return self._call()

    def send_tool_results(self, results: list[tuple[ToolCall, str]]) -> Turn:
        self.messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": call.id, "content": content}
            for call, content in results]})
        return self._call()


class GeminiSession:
    def __init__(self, system: str, tools: list[dict], model: str) -> None:
        from google import genai
        from google.genai import types

        self.types, self.model, self.contents, self._n = types, model, [], 0
        self.client = genai.Client()  # lê GEMINI_API_KEY do ambiente
        declarations = [
            types.FunctionDeclaration(name=t["name"], description=t["description"],
                                      **({"parameters": t["input_schema"]} if t["input_schema"]["properties"] else {}))
            for t in tools]
        self.config = types.GenerateContentConfig(
            system_instruction=system, max_output_tokens=2000,
            tools=[types.Tool(function_declarations=declarations)],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))

    def _call(self) -> Turn:
        r = self.client.models.generate_content(model=self.model, contents=self.contents, config=self.config)
        content = r.candidates[0].content
        self.contents.append(content)  # guarda o conteúdo bruto do modelo (inclui assinaturas de raciocínio)
        parts = content.parts or []
        calls = []
        for part in parts:
            if part.function_call:
                self._n += 1
                calls.append(ToolCall(f"call-{self._n}", part.function_call.name, dict(part.function_call.args or {})))
        usage = r.usage_metadata
        return Turn(text="".join(p.text for p in parts if p.text and not p.thought), tool_calls=calls,
                    stop_reason=str(r.candidates[0].finish_reason),
                    input_tokens=usage.prompt_token_count or 0, output_tokens=usage.candidates_token_count or 0)

    def send(self, text: str) -> Turn:
        self.contents.append(self.types.Content(role="user", parts=[self.types.Part(text=text)]))
        return self._call()

    def send_tool_results(self, results: list[tuple[ToolCall, str]]) -> Turn:
        parts = [self.types.Part.from_function_response(name=call.name, response={"result": content})
                 for call, content in results]
        self.contents.append(self.types.Content(role="user", parts=parts))
        return self._call()


class OllamaSession:
    """LLM local via API HTTP do Ollama: sem chave, sem custo e nada sai da máquina."""

    def __init__(self, system: str, tools: list[dict], model: str) -> None:
        self.model = model
        self.url = os.getenv("OLLAMA_URL", "http://localhost:11434") + "/api/chat"
        self.tools = [{"type": "function", "function": {
            "name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
            for t in tools]
        self.messages = [{"role": "system", "content": system}]
        self._n = 0

    def _call(self) -> Turn:
        body = json.dumps({"model": self.model, "messages": self.messages, "tools": self.tools,
                           "stream": False, "options": {"temperature": 0.2}}).encode()
        request = urllib.request.Request(self.url, body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=900) as response:
            data = json.loads(response.read())
        message = data["message"]
        self.messages.append(message)
        calls = []
        for raw in message.get("tool_calls") or []:
            self._n += 1
            calls.append(ToolCall(f"call-{self._n}", raw["function"]["name"], raw["function"].get("arguments") or {}))
        return Turn(text=message.get("content") or "", tool_calls=calls,
                    stop_reason=data.get("done_reason", ""),
                    input_tokens=data.get("prompt_eval_count", 0), output_tokens=data.get("eval_count", 0))

    def send(self, text: str) -> Turn:
        self.messages.append({"role": "user", "content": text})
        return self._call()

    def send_tool_results(self, results: list[tuple[ToolCall, str]]) -> Turn:
        self.messages += [{"role": "tool", "tool_name": call.name, "content": content}
                          for call, content in results]
        return self._call()


SESSIONS = {"gemini": GeminiSession, "anthropic": AnthropicSession, "ollama": OllamaSession}


def make_session(system: str, tools: list[dict]):
    provider = os.getenv("LLM_PROVIDER", "ollama")
    if provider not in SESSIONS:
        raise ValueError(f"LLM_PROVIDER inválido: {provider!r} (use {', '.join(SESSIONS)})")
    return SESSIONS[provider](system, tools, os.getenv("LLM_MODEL", DEFAULTS[provider]))
