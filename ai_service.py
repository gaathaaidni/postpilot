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

    # Guard against prompt inflation and oversized inputs
    max_budget = getattr(config, 'AI_MAX_PROMPT_CHARS', 8000)
    if len(camp_brief) > 3000:
        logger.warning(f"Campaign brief exceeds 3000 chars ({len(camp_brief)}). Truncating.")
        camp_brief = camp_brief[:3000] + "... [truncated]"
    if len(positioning) > 1500:
        logger.warning(f"Brand positioning exceeds 1500 chars ({len(positioning)}). Truncating.")
        positioning = positioning[:1500] + "... [truncated]"
    if len(approved_facts) > 1500:
        approved_facts = approved_facts[:1500] + "... [truncated]"
    if len(prohibited_claims) > 1500:
        prohibited_claims = prohibited_claims[:1500] + "... [truncated]"

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

    total_len = len(system_prompt) + len(user_prompt)
    if total_len > max_budget:
        overflow = total_len - max_budget
        camp_brief = camp_brief[:max(100, len(camp_brief) - overflow - 20)] + "... [truncated]"
        logger.warning(f"Combined prompt length exceeded budget ({total_len} > {max_budget}). Truncated brief to fit.")
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

def build_strategy_prompts(brand_info, campaign_info):
    """
    Constructs high-fidelity system and user prompts for brand-aware campaign strategy generation.
    Strictly enforces factual guardrails and structured 14-section JSON format.
    """
    brand_name = brand_info.get('name', 'Brand')
    positioning = brand_info.get('positioning', '')
    voice_and_tone = brand_info.get('voice_and_tone', 'Professional, authoritative, customer-focused')
    approved_facts = brand_info.get('approved_product_facts', '')
    prohibited_claims = brand_info.get('prohibited_claims', '')
    messaging_guidelines = brand_info.get('messaging_guidelines', '')

    camp_name = campaign_info.get('name', 'Campaign')
    camp_obj = campaign_info.get('objective', '')
    camp_brief = campaign_info.get('brief', '')
    camp_audience = campaign_info.get('target_audience', 'General Target Market')
    camp_markets = campaign_info.get('target_markets', 'Global')
    camp_budget = campaign_info.get('budget', 'Not specified')

    system_prompt = (
        f"You are the Chief Brand Marketing Strategist for '{brand_name}'.\n"
        f"Brand Positioning: {positioning}\n"
        f"Voice & Tone: {voice_and_tone}\n"
        f"{f'Messaging Guidelines: {messaging_guidelines}' if messaging_guidelines else ''}\n\n"
        "FACTUAL GUARDRAILS & TRUTHFULNESS (MANDATORY):\n"
        "- Never invent product capabilities, certifications, partners, client numbers, awards, or legal approvals.\n"
        f"- Approved Product Facts: {approved_facts if approved_facts else 'Rely strictly on facts provided in the campaign brief.'}\n"
        f"- Prohibited Claims: {prohibited_claims if prohibited_claims else 'Do not make unverified claims or false promises.'}\n"
        "- Ground every strategic pillar strictly in the brand's verified facts.\n"
        "- Highlight any assumptions that need verification in the 'risks_and_verification' section.\n\n"
        "RESPONSE FORMAT:\n"
        "You must return ONLY a valid JSON object with the following exact 14 keys:\n"
        "{\n"
        '  "positioning": "Executive positioning of the campaign within the brand portfolio",\n'
        '  "primary_objective": "Primary marketing objective and quantifiable KPIs",\n'
        '  "target_segments": "2-3 distinct audience segments with pain points and motivations",\n'
        '  "pain_points": "Core customer pain points addressed by this campaign",\n'
        '  "value_proposition": "Clear, compelling value proposition and key differentiators",\n'
        '  "core_message": "Narrative arc and central campaign message",\n'
        '  "supporting_messages": "3-4 supporting message pillars",\n'
        '  "content_themes": "Content themes and angles (e.g. Educational, Proof/Case study, Behind-the-scenes)",\n'
        '  "recommended_channels": "Channel distribution strategy and rationale across Facebook, Instagram, LinkedIn, X",\n'
        '  "calls_to_action": "Primary, secondary, and soft calls to action",\n'
        '  "suggested_phases": "Phased execution roadmap: Teaser, Launch, Sustain, Convert",\n'
        '  "posting_frequency": "Recommended posting cadence and best formats per channel",\n'
        '  "success_metrics": "Milestone targets and success metrics",\n'
        '  "risks_and_verification": "Content guardrails, prohibited claims enforcement, and unverified assumptions to confirm"\n'
        "}\n"
        "Do not include markdown code fence formatting (```json) outside the JSON output."
    )

    user_prompt = (
        f"Develop a complete, brand-aware marketing strategy for the following campaign:\n\n"
        f"Campaign: {camp_name}\n"
        f"Objective: {camp_obj}\n"
        f"Target Audience: {camp_audience}\n"
        f"Target Markets / Geography: {camp_markets}\n"
        f"Budget Allocation: {camp_budget}\n\n"
        f"Campaign Brief:\n{camp_brief}\n\n"
        "Produce the 14-section strategy JSON object now:"
    )

    return system_prompt, user_prompt

def parse_strategy_json_response(raw_text, strict=False):
    """
    Parses JSON containing the 14 campaign strategy sections from AI response.
    Returns a dict with all 14 strategy keys.
    """
    if not raw_text or not raw_text.strip():
        raise AIResponseValidationError("Empty strategy response received from AI provider.")

    clean = raw_text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean)
        clean = clean.strip()

    data = None
    try:
        data = json.loads(clean)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", clean)
        if match:
            try:
                data = json.loads(match.group(0))
            except Exception:
                pass

    if not isinstance(data, dict):
        if strict:
            raise AIResponseValidationError("Could not parse valid JSON dictionary from strategy response.")
        data = {
            "positioning": clean[:500],
            "primary_objective": "Drive brand awareness and engagement",
            "target_segments": "Primary audience segment based on campaign brief",
            "pain_points": "Key customer pain points identified in brief",
            "value_proposition": "Unique brand value proposition",
            "core_message": "Central campaign narrative",
            "supporting_messages": "Supporting brand messaging pillars",
            "content_themes": "Educational, Product Focus, Case Studies",
            "recommended_channels": "Facebook, Instagram, LinkedIn, X",
            "calls_to_action": "Learn More, Sign Up, Contact Us",
            "suggested_phases": "Phase 1: Awareness, Phase 2: Engagement, Phase 3: Conversion",
            "posting_frequency": "3-4 posts per week across primary platforms",
            "success_metrics": "Impressions, CTR, Engagement rate, Conversions",
            "risks_and_verification": "Ensure all product claims match approved facts."
        }

    keys = [
        'positioning', 'primary_objective', 'target_segments', 'pain_points',
        'value_proposition', 'core_message', 'supporting_messages', 'content_themes',
        'recommended_channels', 'calls_to_action', 'suggested_phases',
        'posting_frequency', 'success_metrics', 'risks_and_verification'
    ]
    res = {}
    for k in keys:
        val = data.get(k) or data.get(k.replace('_', ' ')) or ""
        if isinstance(val, (dict, list)):
            res[k] = json.dumps(val)
        else:
            res[k] = str(val).strip()
    return res

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

    def generate_strategy(self, brand_info, campaign_info, model=None, temperature=0.7, max_tokens=2500) -> dict:
        if self.simulate_rate_limit or self.simulated_error == "rate_limit":
            raise AIRateLimitError("Simulated provider rate limit exceeded (HTTP 429).", provider="mock", status_code=429)
        if self.simulate_timeout or self.simulated_error == "timeout":
            raise AITimeoutError("Simulated request timed out after 30s.", provider="mock")
        if self.simulate_invalid_json or self.simulated_error == "invalid_json":
            raise AIResponseValidationError("Simulated invalid JSON from model.", provider="mock")
        if self.simulated_error:
            err = self.simulated_error
            if err == "config":
                raise AIConfigurationError("Simulated AI provider API key is missing or invalid.", provider="mock")
            else:
                raise AIProviderError(f"Simulated AI provider error: {err}", provider="mock")

        brand_name = brand_info.get('name', 'GAATHA')
        camp_name = campaign_info.get('name', 'Campaign')
        camp_obj = campaign_info.get('objective', 'Market Expansion')
        camp_brief = campaign_info.get('brief', 'Deliver high-impact digital value.')
        camp_aud = campaign_info.get('target_audience', 'Enterprise & Professional Leaders')

        return {
            "positioning": f"Positions {brand_name} as the verified market leader in reliable, high-performance solutions via '{camp_name}'.",
            "primary_objective": f"Achieve '{camp_obj}' with measurable 25% lift in qualified pipeline and multi-channel brand recall.",
            "target_segments": f"1. Decision Makers ({camp_aud}): Seeking operational reliability and proven ROI.\n2. Operators & Teams: Focused on seamless workflows and practical efficiency.\n3. Industry Innovators: Looking for modern technological advantage.",
            "pain_points": "Fragmented tools, unpredictable delivery, lack of verifiable data, and high friction in team execution.",
            "value_proposition": f"{brand_name} delivers robust, end-to-end execution with verifiable performance and dependable customer outcomes.",
            "core_message": f"Empower your organization with {brand_name}: where precision engineering meets reliable execution.",
            "supporting_messages": "1. Verifiable reliability and transparent architecture.\n2. Built for scale from single operators to global teams.\n3. Frictionless adoption with immediate time-to-value.",
            "content_themes": "1. Educational & Thought Leadership: Industry deep-dives.\n2. Proof & Validation: Demonstrable workflows and real use cases.\n3. Product Spotlight: Feature capabilities grounded strictly in approved facts.\n4. Behind the Scenes: Engineering excellence and team ethos.",
            "recommended_channels": "LinkedIn (B2B executive perspective and case studies), Instagram (visual architecture and culture), X (real-time announcements and technical discussions), Facebook (community and long-form updates).",
            "calls_to_action": "Primary: Request an executive briefing. Secondary: Explore the interactive demo. Soft: Join our technical community.",
            "suggested_phases": "Phase 1 (Teaser, Week 1): Reveal industry challenges and teaser insights.\nPhase 2 (Launch, Weeks 2-3): Announce core campaign message with feature spotlights.\nPhase 3 (Sustain, Weeks 4-6): Release customer proof points and educational deep-dives.\nPhase 4 (Convert, Weeks 7-8): Targeted CTA drive for qualified consultations.",
            "posting_frequency": "LinkedIn: 3x/week; Instagram: 4x/week (carousels & reels); X: 5x/week (threads & updates); Facebook: 2x/week.",
            "success_metrics": "Impressions (50k+), Engagement rate (>3.5%), Demo requests (+40%), Marketing qualified leads (+25%).",
            "risks_and_verification": "Strictly enforce prohibited claims: do not cite unverified client numbers or unapproved certifications. All technical statements must align with official documentation."
        }

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

    def generate_strategy(self, brand_info, campaign_info, model=None, temperature=0.7, max_tokens=2500) -> dict:
        system_prompt, user_prompt = build_strategy_prompts(brand_info, campaign_info)
        used_model = model or self.default_model

        if not self.base_url:
            raise AIConfigurationError(f"AI Provider '{self.provider_name}' is missing a configured base_url.", provider=self.provider_name)
        if not self.api_key:
            raise AIConfigurationError(f"AI Provider '{self.provider_name}' requires an API key.", provider=self.provider_name)

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
            raise AITimeoutError(f"AI Provider '{self.provider_name}' timed out after {self.timeout}s: {self._sanitize_error(e)}", provider=self.provider_name, model=used_model)
        except requests.exceptions.RequestException as e:
            raise AIProviderError(f"AI Provider '{self.provider_name}' network error: {self._sanitize_error(e)}", provider=self.provider_name, model=used_model)

        if resp.status_code == 429:
            raise AIRateLimitError("AI Provider rate limit reached.", provider=self.provider_name, model=used_model, status_code=429)
        elif resp.status_code in (401, 403):
            raise AIConfigurationError("AI Provider authentication failed.", provider=self.provider_name, model=used_model, status_code=resp.status_code)
        elif resp.status_code != 200:
            raise AIProviderError(f"AI Provider returned HTTP {resp.status_code}: {self._sanitize_error(resp.text)}", provider=self.provider_name, model=used_model, status_code=resp.status_code)

        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            raise AIResponseValidationError(f"Failed to parse choices from response: {self._sanitize_error(e)}", provider=self.provider_name, model=used_model)

        parsed = parse_strategy_json_response(content)
        parsed["raw_response"] = content
        return parsed

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
    1. Builds brand-aware prompts with guardrails, tone guidelines, and prompt budget controls.
    2. Capping output tokens to configured ceiling.
    3. Executes generation via the specified AI provider.
    4. Returns validated GenerationResult container.
    """
    token_cap = getattr(config, 'AI_MAX_OUTPUT_TOKENS', 1500)
    effective_max_tokens = min(int(max_tokens or 1000), token_cap)

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
        max_tokens=effective_max_tokens,
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

def generate_campaign_strategy(provider, brand_info, campaign_info, model=None, temperature=0.7):
    """
    Orchestrates brand-aware campaign strategy generation.
    Returns a dict containing the 14 strategy sections and raw response.
    """
    if hasattr(provider, 'generate_strategy'):
        res = provider.generate_strategy(brand_info, campaign_info, model=model, temperature=temperature)
    else:
        system_prompt, user_prompt = build_strategy_prompts(brand_info, campaign_info)
        gen_res = provider.generate(system_prompt, user_prompt, model=model, temperature=temperature, max_tokens=2500)
        res = parse_strategy_json_response(gen_res.raw_response or gen_res.caption)

    if 'raw_response' not in res:
        res['raw_response'] = json.dumps(res)
    return res
