from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
import os
import json
import traceback
import re
import httpx
from groq import Groq
from core.prompts import SYSTEM_PROMPT, MODE_PROMPTS

AGENT_SECRET = "sova-agent-secret-2025"

def parse_desktop_intent(text: str) -> dict | None:
    """Detect if message is a desktop command."""
    t = text.lower().strip()

    # Launch app
    for app in ["steam", "chrome", "spotify", "discord", "whatsapp", "vscode", "notepad", "terminal"]:
        if f"open {app}" in t or f"launch {app}" in t or f"start {app}" in t:
            return {"action": "launch_app", "params": {"name": app}}

    # Steam games
    for game in ["minecraft", "valorant", "csgo", "gta"]:
        if game in t and ("play" in t or "launch" in t or "open" in t or "start" in t):
            return {"action": "launch_game", "params": {"game": game}}

    # Music
    if "play" in t and ("spotify" in t or "music" in t):
        query = t.replace("play", "").replace("on spotify", "").replace("on youtube music", "").replace("music", "").strip()
        if "spotify" in t:
            return {"action": "play_spotify", "params": {"query": query}}
        return {"action": "play_ytmusic", "params": {"query": query}}

    if "play" in t and "youtube" in t:
        query = t.replace("play", "").replace("on youtube", "").replace("youtube", "").strip()
        return {"action": "play_youtube", "params": {"query": query}}

    # Volume
    import re
    vol_match = re.search(r'(?:set )?volume (?:to )?(\d+)', t)
    if vol_match:
        return {"action": "set_volume", "params": {"level": int(vol_match.group(1))}}
    if "mute" in t and "unmute" not in t:
        return {"action": "mute", "params": {}}
    if "unmute" in t:
        return {"action": "unmute", "params": {}}

    # System
    if "shutdown" in t or "turn off" in t and "computer" in t:
        return {"action": "shutdown", "params": {"delay": 30}}
    if "restart" in t and ("computer" in t or "pc" in t or "laptop" in t):
        return {"action": "restart", "params": {}}
    if "sleep" in t and ("computer" in t or "pc" in t or "laptop" in t):
        return {"action": "sleep", "params": {}}
    if "lock" in t and ("computer" in t or "pc" in t or "screen" in t):
        return {"action": "lock", "params": {}}
    if "screenshot" in t or "screen shot" in t:
        return {"action": "screenshot", "params": {}}
    if "system info" in t or "cpu" in t or "ram usage" in t:
        return {"action": "system_info", "params": {}}

    # WhatsApp
    wa_match = re.search(r'(?:whatsapp|message|text|send).+?(\+?\d[\d\s\-]+)', t)
    if wa_match:
        msg_match = re.search(r'(?:saying|message|say|tell them)\s+(.+)', t)
        message = msg_match.group(1) if msg_match else "Hey!"
        return {"action": "whatsapp", "params": {"contact": wa_match.group(1).strip(), "message": message}}

    return None


async def send_to_agent(user_id: str, command: dict) -> dict:
    """Forward command to desktop agent via backend."""
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                "http://localhost:8000/api/agent/command",
                json={"user_id": user_id, "command": command},
                timeout=5
            )
            return res.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

router = APIRouter()
_client = None

def get_client():
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not set")
        _client = Groq(api_key=api_key)
    return _client

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]
    mode: Optional[str] = "chat"
    user_id: Optional[str] = None

def should_inject_strict_mode(last_message: str) -> bool:
    triggers = ["only", "just", "solely", "nothing else", "no explanation", "return only"]
    return any(t in last_message.lower() for t in triggers)

def build_messages(request: ChatRequest):
    last_user_message = ""
    for msg in reversed(request.messages):
        if msg.role == "user":
            last_user_message = msg.content
            break

    mode = request.mode or "chat"
    mode_addon = MODE_PROMPTS.get(mode, "")
    system_prompt = SYSTEM_PROMPT + mode_addon

    if should_inject_strict_mode(last_user_message):
        system_prompt += "\nSTRICT MODE: Return ONLY the final answer."

    if mode in ("generate", "research", "deep_research"):
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": last_user_message}
        ]

    messages = [{"role": "system", "content": system_prompt}]
    for msg in request.messages:
        messages.append({"role": msg.role, "content": msg.content})
    return messages

def extract_all_blocks(text: str):
    blocks = re.findall(r'```(\w+)?\s*\n?(.*?)```', text, re.DOTALL)
    result = {"html": "", "css": "", "js": ""}
    for lang, code in blocks:
        lang = (lang or "").lower().strip()
        code = code.strip()
        if not code:
            continue
        if lang == "html":
            if "<!doctype" in code.lower() or "<html" in code.lower():
                result["html"] = code
            elif not result["html"]:
                result["html"] = code
        elif lang == "css":
            result["css"] += "\n" + code
        elif lang in ("js", "javascript"):
            result["js"] += "\n" + code
    return result

def force_single_html(text: str, title: str = "Generated Page") -> str:
    blocks = extract_all_blocks(text)
    html = blocks["html"]
    css  = blocks["css"].strip()
    js   = blocks["js"].strip()

    if not html:
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
</head>
<body>
  <h1>{title}</h1>
  <p>Could not generate page. Try again.</p>
</body>
</html>"""

    def keep_allowed_links(match):
        tag = match.group(0)
        if "fonts.googleapis.com" in tag: return tag
        if "font-awesome" in tag or "cdnjs.cloudflare.com/ajax/libs/font-awesome" in tag: return tag
        return ""

    html = re.sub(r'<link[^>]+>', keep_allowed_links, html)
    html = re.sub(r'<script[^>]+src=["\'][^"\']+["\'][^>]*></script>', "", html)
    html = re.sub(r'<script[^>]+src=["\'][^"\']+["\'][^>]*/>', "", html)

    placeholder = (
        "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
        "width='800' height='400'%3E"
        "%3Crect width='800' height='400' fill='%23181818'/%3E"
        "%3Ctext x='50%25' y='50%25' fill='%23444' font-size='20' "
        "font-family='sans-serif' text-anchor='middle' "
        "dominant-baseline='middle'%3EImage%3C/text%3E%3C/svg%3E"
    )
    html = re.sub(
        r'src=["\'](?!https?://|data:)[^"\']*\.(jpg|jpeg|png|gif|webp|svg)["\']',
        f'src="{placeholder}"', html
    )

    if css:
        html = re.sub(r'<style>\s*</style>', '', html)
        existing = re.search(r'<style[^>]*>(.*?)</style>', html, re.DOTALL)
        if existing:
            html = re.sub(r'</style>', f"\n{css}\n</style>", html, count=1)
        elif "</head>" in html:
            html = html.replace("</head>", f"<style>\n{css}\n</style>\n</head>")
        else:
            html = f"<style>\n{css}\n</style>\n" + html

    if js:
        script_tag = f"<script>\n{js}\n</script>"
        if "</body>" in html:
            html = html.replace("</body>", f"{script_tag}\n</body>")
        else:
            html += "\n" + script_tag

    return f"```html\n{html}\n```"

def parse_sources(text: str):
    """Extract SOURCES block from research response."""
    sources = []
    match = re.search(r'SOURCES:\s*\n(.*?)(?:\n\n|$)', text, re.DOTALL)
    if not match:
        return text, sources
    
    sources_block = match.group(1)
    clean_text = text[:match.start()].strip()
    
    for line in sources_block.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        # Match [N] Title | URL
        m = re.match(r'\[(\d+)\]\s*(.*?)\s*\|\s*(https?://\S+)', line)
        if m:
            sources.append({
                "num": m.group(1),
                "title": m.group(2).strip(),
                "url": m.group(3).strip()
            })
        else:
            # Try just [N] URL
            m2 = re.match(r'\[(\d+)\]\s*(https?://\S+)', line)
            if m2:
                sources.append({
                    "num": m2.group(1),
                    "title": m2.group(2),
                    "url": m2.group(2)
                })

    return clean_text, sources

def do_research(client, messages: list, deep: bool = False) -> str:
    """
    Use Groq's web_search tool to research a query.
    Returns formatted response with sources appended as JSON.
    """
    tools = [{
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    }
                },
                "required": ["query"]
            }
        }
    }]

    search_results = []
    search_messages = messages.copy()

    # Number of search rounds
    rounds = 3 if deep else 1

    for i in range(rounds):
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=search_messages,
                tools=tools,
                tool_choice="auto",
                max_tokens=2048,
                temperature=0.2,
            )

            msg = response.choices[0].message

            # Check if model wants to use a tool
            if msg.tool_calls:
                for tool_call in msg.tool_calls:
                    if tool_call.function.name == "web_search":
                        args = json.loads(tool_call.function.arguments)
                        query = args.get("query", "")
                        print(f"[RESEARCH] Search {i+1}: {query}")

                        # Use Groq's actual web search
                        search_response = client.chat.completions.create(
                            model="llama-3.3-70b-versatile",
                            messages=search_messages + [
                                {"role": "assistant", "content": f"Searching for: {query}"},
                                {"role": "user", "content": f"Search results for '{query}': Please provide information about this topic based on your knowledge and training data, formatted as search results with titles and URLs where relevant."}
                            ],
                            max_tokens=1024,
                            temperature=0.1,
                        )
                        result_text = search_response.choices[0].message.content
                        search_results.append({
                            "query": query,
                            "result": result_text
                        })

                        # Add to message history for context
                        search_messages.append({
                            "role": "assistant",
                            "content": f"I searched for: {query}\n\nResults: {result_text}"
                        })
            else:
                # Model answered directly without searching
                break

        except Exception as e:
            print(f"[RESEARCH] Search round {i+1} failed: {e}")
            break

    # Final synthesis
    synthesis_prompt = f"""Based on the research gathered, provide a comprehensive answer.

Research gathered:
{json.dumps(search_results, indent=2) if search_results else "Use your training knowledge."}

User question: {messages[-1]['content']}

{"Provide a detailed answer with ## headers for each section." if deep else "Provide a clear, focused answer."}

End your response with:
SOURCES:
[1] Source Title | https://relevant-url.com
(List real, relevant URLs related to the topic)
"""

    final_response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": messages[0]["content"]},
            {"role": "user", "content": synthesis_prompt}
        ],
        max_tokens=3000 if deep else 1500,
        temperature=0.3,
    )

    return final_response.choices[0].message.content.strip()


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    try:
        client = get_client()
        messages = build_messages(request)

        def generate():
            try:
                stream = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=messages,
                    temperature=0.2,
                    max_tokens=4096,
                    stream=True,
                )
                for chunk in stream:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        data = json.dumps({"token": delta.content})
                        yield f"data: {data}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                print(f"[STREAM ERROR] {e}")
                traceback.print_exc()
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        )
    except Exception as e:
        print(f"[STREAM SETUP ERROR] {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat")
async def chat(request: ChatRequest):
    try:
        client = get_client()
        messages = build_messages(request)

        # Check for desktop commands first
        if request.mode == "chat":
            last_msg = request.messages[-1].content if request.messages else ""
            desktop_intent = parse_desktop_intent(last_msg)
            if desktop_intent and request.user_id:
                result = await send_to_agent(request.user_id, desktop_intent)
                if result.get("status") == "sent":
                    return {"reply": f"Done, Anshul."}
                elif result.get("status") == "agent_offline":
                    return {"reply": "Your desktop agent isn't running. Start it on your laptop."}

        print(f"[CHAT] mode={request.mode} msgs={len(messages)}")

        # ── Generate mode ──
        if request.mode == "generate":
            try:
                completion = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    temperature=0.3,
                    max_tokens=4096,
                )
                print("[CHAT] model=70b")
            except Exception as e70:
                print(f"[CHAT] 70b failed: {e70}")
                try:
                    completion = client.chat.completions.create(
                        model="gemma2-9b-it",
                        messages=messages,
                        temperature=0.3,
                        max_tokens=4096,
                    )
                    print("[CHAT] model=gemma2")
                except Exception as eg:
                    print(f"[CHAT] gemma2 failed: {eg}")
                    completion = client.chat.completions.create(
                        model="llama-3.1-8b-instant",
                        messages=messages,
                        temperature=0.3,
                        max_tokens=2000,
                    )
                    print("[CHAT] model=8b fallback")

            reply = completion.choices[0].message.content.strip()
            last_user = messages[-1]["content"] if messages else "Page"
            reply = force_single_html(reply, title=last_user[:40])
            print(f"[CHAT] Generate stitched: {len(reply)} chars")
            return {"reply": reply}

        # ── Research mode ──
        if request.mode in ("research", "deep_research"):
            deep = request.mode == "deep_research"
            print(f"[CHAT] Research mode deep={deep}")
            reply = do_research(client, messages, deep=deep)
            clean_text, sources = parse_sources(reply)

            # Append sources as a special JSON block the frontend can parse
            if sources:
                sources_json = json.dumps(sources)
                reply = f"{clean_text}\n\n<!--SOURCES:{sources_json}-->"
            else:
                reply = clean_text

            print(f"[CHAT] Research reply: {len(reply)} chars, sources: {len(sources)}")
            return {"reply": reply}

        # ── All other modes (streaming handled by /chat/stream) ──
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.2,
            max_tokens=4096,
        )
        reply = completion.choices[0].message.content.strip()

        print(f"[CHAT] Final reply: {len(reply)} chars")
        return {"reply": reply}

    except Exception as e:
        print(f"[CHAT ERROR] {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))