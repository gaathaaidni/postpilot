"""
PostPilot AI Marketing Studio Service Layer
Provides clean, configurable AI provider abstractions for brand-aware marketing
content generation supporting OpenAI-compatible chat completion APIs (Groq, OpenAI,
Together, DeepSeek, Local Ollama) and a deterministic Mock provider.
Zero third-party proprietary AI SDK requirements (uses existing requests library).
"""
import os
import re
import json
import logging
from abc import ABC, abstractmethod
import requests

import config

logger = logging.getLogger(__name__)

# --- Exception Hierarchy ---

class AIProviderError(Exception):
    """Base exception for all AI provider errors."""
    def __init__(self, message, provider=None, model=None, status_code=None):
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.model = model
        self.status_code = status_code

class AIConfigurationError(AIProviderError):
    """Raised when an AI provider lacks necessary credentials or configuration."""
    pass

class AIRateLimitError(AIProviderError):
    """Raised when a provider rejects requests due to rate limits (HTTP 429)."""
    pass

class AITimeoutError(AIProviderError):
    """Raised when an AI provider request exceeds timeout limits."""
    pass

class AIResponseValidationError(AIProviderError):
    """Raised when the provider output is empty, malformed, or fails schema validation."""
    pass

# --- Generation Result Data Container ---

class GenerationResult:
    """Encapsulates the structured output of an AI copy generation request."""
    def __init__(self, headline, caption, hashtags="", call_to_action="",
                 target_platform="facebook", language="en", content_format="post",
                 ai_provider="mock", ai_model="mock-v1", raw_response="", metadata=None):
        self.headline = headline or ""
        self.caption = caption or ""
        self.hashtags = hashtags or ""
        self.call_to_action = call_to_action or ""
        self.target_platform = target_platform
        self.language = language
        self.content_format = content_format
        self.ai_provider = ai_provider
        self.ai_model = ai_model
        self.raw_response = raw_response
        self.metadata = metadata or {}

    def to_dict(self):
        return {
            "headline": self.headline,
            "caption": self.caption,
            "hashtags": self.hashtags,
            "call_to_action": self.call_to_action,
            "target_platform": self.target_platform,
            "language": self.language,
            "content_format": self.content_format,
            "ai_provider": self.ai_provider,
            "ai_model": self.ai_model,
            "raw_response": self.raw_response,
            "metadata": self.metadata
        }

# --- Prompt Construction Helper ---

def build_marketing_prompts(brand_info, campaign_info, target_platform, language="en", content_format="post"):
    """
    Constructs comprehensive system and user prompts injecting:
    - Brand positioning, tone of voice, approved facts, prohibited claims.
    - Campaign objective, brief, target audience, and target markets.
    - Platform-specific copy requirements and factual honesty guardrails.
    """
    brand_name = brand_info.get('name', 'Brand')
    positioning = brand_info.get('positioning') or brand_info.get('description', '')
    voice_and_tone = brand_info.get('voice_and_tone', 'Professional, authoritative, customer-focused')
    messaging_guidelines = brand_info.get('messaging_guidelines', '')
    approved_facts = brand_info.get('approved_product_facts', '')
    prohibited_claims = brand_info.get('prohibited_claims', '')
    preferred_ctas = brand_info.get('preferred_ctas', '')

    camp_name = campaign_info.get('name', '')
    camp_obj = campaign_info.get('objective', '')
    camp_brief = campaign_info.get('brief', '')
    camp_audience = campaign_info.get('target_audience') or 'Target audience'
    camp_markets = campaign_info.get('target_markets') or 'Global'

    platform_rules = {
        'facebook': (
            "Platform: Facebook Page Post.\n"
            "- Hook the reader with an engaging, clear headline.\n"
            "- Provide an informative narrative with comfortable paragraph spacing.\n"
            "- Include 2-3 focused, relevant hashtags.\n"
            "- End with a strong conversational Call to Action (CTA) encouraging clicks or inquiries."
        ),
        'instagram': (
            "Platform: Instagram Post / Reel Caption.\n"
            "- Open with a high-impact, visual hook.\n"
            "- Use clean line breaks, modern storytelling, and natural emojis.\n"
            "- Include a cohesive block of 5-8 relevant hashtags.\n"
            "- End with a clear action CTA (e.g. 'Save this', 'Tap the link in bio', 'DM for details')."
        ),
        'linkedin': (
            "Platform: LinkedIn Professional Post.\n"
            "- Open with thought leadership framing or an industry insight.\n"
            "- Emphasize business impact, measurable advantages, or leadership vision.\n"
            "- Use clean professional spacing without excessive hype or informal jargon.\n"
            "- Include 3-5 professional hashtags.\n"
            "- End with an executive/professional CTA."
        ),
        'x': (
            "Platform: X (formerly Twitter) Post.\n"
            "- Keep the primary text punchy and concise, strictly under 280 characters if possible.\n"
            "- Fast hook, high clarity, and 1-2 sharp hashtags.\n"
            "- Immediate, low-friction CTA."
        ),
        'whatsapp': (
            "Platform: WhatsApp Business Messaging Draft.\n"
            "NOTE: This is a direct conversational message draft for customer communications or newsletter broadcasts, "
            "NOT an automated WhatsApp Status post.\n"
            "- Greet politely and get straight to the value proposition.\n"
            "- Use clean bullet points for readability on mobile screens.\n"
            "- Do NOT clutter with hashtags.\n"
            "- Provide a clear, polite next step or immediate response prompt."
        )
    }

    selected_rule = platform_rules.get(target_platform.lower(), platform_rules['facebook'])

    system_prompt = (
        f"You are the senior brand copywriter for '{brand_name}'.\n"
        f"Brand Positioning: {positioning}\n"
        f"Voice & Tone: {voice_and_tone}\n"
        f"{f'Messaging Guidelines: {messaging_guidelines}' if messaging_guidelines else ''}\n\n"
        "FACTUAL GUARDRAILS & TRUTHFULNESS (MANDATORY):\n"
        "- Never invent product features, certifications, legal approvals, awards, customer metrics, or performance guarantees.\n"
        f"- Approved Product Facts: {approved_facts if approved_facts else 'Rely strictly on facts provided in the brief.'}\n"
        f"- Prohibited Claims: {prohibited_claims if prohibited_claims else 'Do not make unverified claims or false promises.'}\n"
        "- If specific technical or verified product data is not provided, use cautious, truthful phrasing and highlight any need for verification.\n\n"
        "RESPONSE FORMAT:\n"
        "You must return ONLY a valid JSON object with the following exact keys:\n"
        "{\n"
        '  "headline": "A short, compelling title or hook",\n'
        '  "caption": "The main body text formatted appropriately for the target platform",\n'
        '  "hashtags": "Space-separated hashtags or empty string if not applicable",\n'
        '  "call_to_action": "Clear, specific CTA"\n'
        "}\n"
        "Do not include markdown code fence formatting (```json) outside the JSON output if possible."
    )

    user_prompt = (
        f"Generate a {content_format} for {target_platform.capitalize()} in language: '{language}'.\n\n"
        f"Campaign: {camp_name}\n"
        f"Objective: {camp_obj}\n"
        f"Target Audience: {camp_audience}\n"
        f"Target Markets / Geography: {camp_markets}\n"
        f"Campaign Brief:\n{camp_brief}\n\n"
        f"{selected_rule}\n"
        f"{f'Preferred Calls to Action: {preferred_ctas}' if preferred_ctas else ''}\n\n"
        "Produce the JSON object now:"
    )

    return system_prompt, user_prompt

def parse_ai_json_response(raw_text, fallback_platform="facebook", strict=False):
    """
    Robustly parses JSON from LLM output, handling markdown fences,
    extraneous prose, and structured fallbacks.
    If strict=True, raises AIResponseValidationError on malformed JSON.
    """
    if not raw_text or not raw_text.strip():
        raise AIResponseValidationError("Empty response received from AI provider.")

    clean = raw_text.strip()
    # Strip markdown code blocks if present
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean)
        clean = clean.strip()

    # Attempt direct JSON parse
    try:
        data = json.loads(clean)
        if isinstance(data, dict):
            return {
                "headline": str(data.get("headline", "")).strip(),
                "caption": str(data.get("caption", "")).strip(),
                "hashtags": str(data.get("hashtags", "")).strip(),
                "call_to_action": str(data.get("call_to_action", "")).strip()
            }
    except Exception:
        pass

    # Extract first JSON object pattern {...}
    match = re.search(r"\{[\s\S]*\}", clean)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return {
                    "headline": str(data.get("headline", "")).strip(),
                    "caption": str(data.get("caption", "")).strip(),
                    "hashtags": str(data.get("hashtags", "")).strip(),
                    "call_to_action": str(data.get("call_to_action", "")).strip()
                }
        except Exception:
            pass

    if strict:
        raise AIResponseValidationError("Could not parse valid JSON from AI provider response.")

    # Graceful fallback: treat raw output as caption
    return {
        "headline": "Campaign Update",
        "caption": clean,
        "hashtags": "",
        "call_to_action": "Learn More"
    }

# --- Base AI Provider ---

class BaseAIProvider(ABC):
    """Abstract base class for all AI marketing content generation providers."""
    def __init__(self, provider_name, default_model=None):
        self.provider_name = provider_name
        self.default_model = default_model

    @abstractmethod
    def generate(self, system_prompt, user_prompt, model=None, temperature=0.7,
                 max_tokens=1000, target_platform="facebook", language="en") -> GenerationResult:
        """Executes content generation and returns a GenerationResult."""
        pass

    def generate_for_campaign(self, brand_info, campaign_info, target_platform,
                              language="en", content_format="post", model=None,
                              temperature=0.7, max_tokens=1000) -> GenerationResult:
        """Convenience method combining prompt construction and generation."""
        return generate_campaign_content(
            self, brand_info, campaign_info, target_platform,
            language=language, content_format=content_format,
            model=model, temperature=temperature, max_tokens=max_tokens
        )

# --- Mock AI Provider ---

class MockAIProvider(BaseAIProvider):
    """
    Deterministic, reliable mock AI provider for automated testing, local development,
    and offline Termux environments. Consumes zero network credits and zero API keys.
    """
    def __init__(self, default_model="mock-v1"):
        super().__init__(provider_name="mock", default_model=default_model)
        self.simulated_error = None
        self.simulate_rate_limit = False
        self.simulate_timeout = False
        self.simulate_invalid_json = False
        self.simulate_empty_response = False

    def generate(self, system_prompt, user_prompt, model=None, temperature=0.7,
                 max_tokens=1000, target_platform="facebook", language="en") -> GenerationResult:
        if self.simulate_rate_limit or self.simulated_error == "rate_limit":
            raise AIRateLimitError("Simulated provider rate limit exceeded (HTTP 429).", provider="mock", status_code=429)
        if self.simulate_timeout or self.simulated_error == "timeout":
            raise AITimeoutError("Simulated request timed out after 30s.", provider="mock")
        if self.simulate_invalid_json or self.simulated_error == "invalid_json":
            raise AIResponseValidationError("Simulated invalid JSON from model.", provider="mock")
        if self.simulate_empty_response or self.simulated_error == "empty_response":
            raise AIResponseValidationError("Simulated empty response from AI model.", provider="mock")
        if self.simulated_error:
            err = self.simulated_error
            if err == "config":
                raise AIConfigurationError("Simulated AI provider API key is missing or invalid.", provider="mock")
            else:
                raise AIProviderError(f"Simulated AI provider error: {err}", provider="mock")

        used_model = model or self.default_model

        # Extract brand and campaign names from user_prompt
        camp_match = re.search(r"Campaign:\s*([^\n]+)", user_prompt)
        camp_name = camp_match.group(1).strip() if camp_match else "Featured Campaign"

        obj_match = re.search(r"Objective:\s*([^\n]+)", user_prompt)
        camp_obj = obj_match.group(1).strip() if obj_match else "Drive customer awareness"

        brief_match = re.search(r"Campaign Brief:\s*([\s\S]+?)(?:\n\nPlatform:|$)", user_prompt)
        camp_brief = brief_match.group(1).strip() if brief_match else "Explore our latest innovations and reliable offerings."

        plat = target_platform.lower()

        if plat == 'linkedin':
            headline = f"Strategic Perspective: {camp_name}"
            caption = (
                f"In an evolving market landscape, achieving {camp_obj.lower()} requires clarity, discipline, and execution.\n\n"
                f"{camp_brief}\n\n"
                f"We are committed to delivering sustainable performance and verified results for our partners."
            )
            hashtags = "#BusinessLeadership #Innovation #GrowthStrategy #PostPilot"
            cta = "Connect with our team to discuss strategic opportunities."
        elif plat == 'instagram':
            headline = f"\u2728 Introducing: {camp_name}"
            caption = (
                f"Ready to level up?\n\n"
                f"{camp_brief}\n\n"
                f"\U0001f4a1 Focused on {camp_obj.lower()}.\n"
                f"Built with precision, engineered for impact."
            )
            hashtags = "#Innovation #CreatorEconomy #SmartGrowth #PostPilotApp #MarketingAI"
            cta = "Tap the link in our bio to get started!"
        elif plat == 'x':
            headline = f"{camp_name} \u2014 Now Live"
            caption = f"{camp_name}: {camp_brief[:160]}... Focused on {camp_obj.lower()}."
            hashtags = "#Innovation #Marketing"
            cta = "Learn more below \u2193"
        elif plat == 'whatsapp':
            headline = f"Update: {camp_name}"
            caption = (
                f"Hello,\n\n"
                f"We wanted to share an update regarding {camp_name}.\n\n"
                f"\u2022 Goal: {camp_obj}\n"
                f"\u2022 Details: {camp_brief}\n\n"
                f"Please reply directly to this message if you have any questions."
            )
            hashtags = ""
            cta = "Reply YES to receive the complete overview."
        else: # facebook
            headline = f"Announcing: {camp_name}"
            caption = (
                f"We are excited to share {camp_name}!\n\n"
                f"{camp_brief}\n\n"
                f"Our primary objective: {camp_obj.lower()}. Discover how our solutions make a difference today."
            )
            hashtags = "#Innovation #BusinessGrowth #PostPilot"
            cta = "Click the link to learn more and get started."

        raw_json = json.dumps({
            "headline": headline,
            "caption": caption,
            "hashtags": hashtags,
            "call_to_action": cta
        }, indent=2)

        return GenerationResult(
            headline=headline,
            caption=caption,
            hashtags=hashtags,
            call_to_action=cta,
            target_platform=plat,
            language=language,
            content_format="post",
            ai_provider="mock",
            ai_model=used_model,
            raw_response=raw_json,
            metadata={"mock": True, "generated_chars": len(caption)}
        )

# --- OpenAI-Compatible Provider (Groq, OpenAI, Together, DeepSeek, Local Ollama) ---

class OpenAICompatibleProvider(BaseAIProvider):
    """
    Universal OpenAI-compatible chat completion provider.
    Connects to any standard /chat/completions endpoint (e.g. Groq, OpenAI).
    Enforces sanitized logging, request timeouts, and clean error classification.
    """
    def __init__(self, provider_name="openai_compatible", base_url=None, api_key=None,
                 default_model=None, timeout_seconds=None, model=None):
        super().__init__(provider_name=provider_name, default_model=model or default_model)
        self.base_url = (base_url or "").rstrip('/')
        self.api_key = api_key
        self.timeout = timeout_seconds or config.AI_TIMEOUT_SECONDS

    def _sanitize_error(self, err_msg):
        """Sanitizes tokens and secrets from exception messages."""
        try:
            import facebook_api
            return facebook_api.sanitize_log_message(str(err_msg))
        except Exception:
            return re.sub(r'Bearer\s+[A-Za-z0-9_\-\.]+', 'Bearer [REDACTED]', str(err_msg))

    def generate(self, system_prompt, user_prompt, model=None, temperature=0.7,
                 max_tokens=1000, target_platform="facebook", language="en") -> GenerationResult:
        if not self.base_url:
            raise AIConfigurationError(
                f"AI Provider '{self.provider_name}' is missing a configured base_url.",
                provider=self.provider_name
            )

        if not self.api_key:
            raise AIConfigurationError(
                f"AI Provider '{self.provider_name}' requires an API key in the environment (e.g. {self.provider_name.upper()}_API_KEY or AI_API_KEY).",
                provider=self.provider_name
            )

        used_model = model or self.default_model
        if not used_model:
            raise AIConfigurationError(
                f"No model specified for provider '{self.provider_name}'.",
                provider=self.provider_name
            )

        endpoint = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": used_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": float(temperature),
            "max_tokens": int(max_tokens)
        }

        try:
            resp = requests.post(endpoint, json=payload, headers=headers, timeout=self.timeout)
        except requests.exceptions.Timeout as e:
            logger.error(f"AI Provider '{self.provider_name}' request timed out: {self._sanitize_error(e)}")
            raise AITimeoutError(
                f"AI Provider '{self.provider_name}' timed out after {self.timeout} seconds.",
                provider=self.provider_name,
                model=used_model
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"AI Provider '{self.provider_name}' network error: {self._sanitize_error(e)}")
            raise AIProviderError(
                f"AI Provider '{self.provider_name}' communication failure: {self._sanitize_error(e)}",
                provider=self.provider_name,
                model=used_model
            )

        if resp.status_code == 429:
            err_text = self._sanitize_error(resp.text)
            logger.warning(f"AI Provider '{self.provider_name}' rate limit reached (HTTP 429): {err_text}")
            raise AIRateLimitError(
                f"AI Provider '{self.provider_name}' rate limit exceeded. Please retry after a brief interval.",
                provider=self.provider_name,
                model=used_model,
                status_code=429
            )
        elif resp.status_code in (401, 403):
            logger.error(f"AI Provider '{self.provider_name}' authentication failed (HTTP {resp.status_code}).")
            raise AIConfigurationError(
                f"AI Provider '{self.provider_name}' authentication failed. Verify configured API credentials.",
                provider=self.provider_name,
                model=used_model,
                status_code=resp.status_code
            )
        elif resp.status_code != 200:
            err_text = self._sanitize_error(resp.text)
            logger.error(f"AI Provider '{self.provider_name}' HTTP error {resp.status_code}: {err_text}")
            raise AIProviderError(
                f"AI Provider '{self.provider_name}' returned HTTP {resp.status_code}: {err_text}",
                provider=self.provider_name,
                model=used_model,
                status_code=resp.status_code
            )

        try:
            res_json = resp.json()
            choices = res_json.get("choices") or []
            if not choices:
                raise AIResponseValidationError(
                    f"AI Provider '{self.provider_name}' returned 200 OK but no choices were present.",
                    provider=self.provider_name,
                    model=used_model
                )
            content = choices[0].get("message", {}).get("content", "")
        except Exception as e:
            raise AIResponseValidationError(
                f"Failed to parse response from '{self.provider_name}': {self._sanitize_error(e)}",
                provider=self.provider_name,
                model=used_model
            )

        parsed = parse_ai_json_response(content, fallback_platform=target_platform)
        usage = res_json.get("usage", {})

        return GenerationResult(
            headline=parsed.get("headline", ""),
            caption=parsed.get("caption", ""),
            hashtags=parsed.get("hashtags", ""),
            call_to_action=parsed.get("call_to_action", ""),
            target_platform=target_platform.lower(),
            language=language,
            content_format="post",
            ai_provider=self.provider_name,
            ai_model=used_model,
            raw_response=content,
            metadata={
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens")
            }
        )

# --- Pre-Configured Provider Classes ---

class GroqProvider(OpenAICompatibleProvider):
    """Pre-configured Groq LLM Provider via OpenAI-compatible endpoints."""
    def __init__(self, api_key=None, model=None):
        super().__init__(
            provider_name="groq",
            base_url=config.GROQ_BASE_URL,
            api_key=api_key or config.GROQ_API_KEY,
            default_model=model or config.GROQ_MODEL
        )

class OpenAIProvider(OpenAICompatibleProvider):
    """Pre-configured OpenAI Provider via standard endpoints."""
    def __init__(self, api_key=None, model=None):
        super().__init__(
            provider_name="openai",
            base_url=config.OPENAI_BASE_URL,
            api_key=api_key or config.OPENAI_API_KEY,
            default_model=model or config.OPENAI_MODEL
        )

# --- High-Level Marketing Generation Orchestrator ---

def generate_campaign_content(provider: BaseAIProvider, brand_info: dict, campaign_info: dict,
                              target_platform: str, language: str = "en", content_format: str = "post",
                              model: str = None, temperature: float = 0.7, max_tokens: int = 1000) -> GenerationResult:
    """
    High-level marketing studio orchestrator:
    1. Builds brand-aware prompts with guardrails and tone guidelines.
    2. Executes generation via the specified AI provider.
    3. Returns validated GenerationResult container.
    """
    system_prompt, user_prompt = build_marketing_prompts(
        brand_info=brand_info,
        campaign_info=campaign_info,
        target_platform=target_platform,
        language=language,
        content_format=content_format
    )
    return provider.generate(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        target_platform=target_platform,
        language=language
    )

# --- Provider Factory & Registry ---

_PROVIDER_REGISTRY = {
    'mock': MockAIProvider,
    'groq': GroqProvider,
    'openai': OpenAIProvider,
    'openai_compatible': OpenAICompatibleProvider
}

def register_ai_provider(name, provider_cls):
    """Registers a custom provider class."""
    _PROVIDER_REGISTRY[name.lower()] = provider_cls

def get_ai_provider(provider_name=None, model=None, api_key=None, base_url=None) -> BaseAIProvider:
    """
    Factory function resolving the requested or configured AI provider instance.
    Never silently substitutes another provider if the requested provider fails configuration.
    """
    resolved_name = (provider_name or config.AI_PROVIDER or 'mock').strip().lower()

    if resolved_name not in _PROVIDER_REGISTRY:
        raise AIConfigurationError(
            f"Unsupported AI provider: '{resolved_name}'. Supported: {', '.join(sorted(_PROVIDER_REGISTRY.keys()))}."
        )

    prov_cls = _PROVIDER_REGISTRY[resolved_name]

    if resolved_name == 'mock':
        return MockAIProvider(default_model=model or 'mock-v1')
    elif resolved_name == 'groq':
        return GroqProvider(api_key=api_key or config.GROQ_API_KEY, model=model or config.GROQ_MODEL)
    elif resolved_name == 'openai':
        return OpenAIProvider(api_key=api_key or config.OPENAI_API_KEY, model=model or config.OPENAI_MODEL)
    else:
        return OpenAICompatibleProvider(
            provider_name=resolved_name,
            base_url=base_url or config.AI_BASE_URL,
            api_key=api_key or config.AI_API_KEY,
            default_model=model or config.AI_MODEL
        )
