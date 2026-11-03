"""
Unit tests for PostPilot AI Marketing Studio Service Layer (ai_service.py).
Tests mock provider, OpenAI-compatible provider with mocks, error classification,
prompt generation, and credential protection.
"""
import unittest
from unittest.mock import patch, MagicMock
import json
import requests

from ai_service import (
    AIProviderError,
    AIConfigurationError,
    AIRateLimitError,
    AITimeoutError,
    AIResponseValidationError,
    GenerationResult,
    build_marketing_prompts,
    parse_ai_json_response,
    generate_campaign_content,
    generate_campaign_strategy,
    MockAIProvider,
    OpenAICompatibleProvider,
    GroqProvider,
    OpenAIProvider,
    get_ai_provider,
)

class TestAIService(unittest.TestCase):
    def setUp(self):
        self.brand_info = {
            "name": "Global VISA Services",
            "positioning": "Expert visa consultancy for students and professionals worldwide.",
            "voice_and_tone": "Authoritative, reassuring, empathetic, transparent",
            "messaging_guidelines": "Focus on legal compliance, high success rates, and transparent pricing.",
            "approved_product_facts": "Over 10,000 successful visa approvals. 15 years in industry.",
            "prohibited_claims": "Never guarantee visa issuance. Never give unlawful advice.",
            "preferred_ctas": "Book a Free Profile Assessment today."
        }
        self.campaign_info = {
            "name": "Fall 2027 Student Visa Drive",
            "objective": "Lead Generation",
            "brief": "Promote university admissions and study permit assistance for top destinations.",
            "target_audience": "Prospective international students and parents",
            "target_markets": "India, Nepal, Bangladesh, UAE",
            "preferred_language": "en"
        }

    def test_build_marketing_prompts(self):
        system_prompt, user_prompt = build_marketing_prompts(
            self.brand_info,
            self.campaign_info,
            target_platform="linkedin",
            language="en"
        )
        self.assertIn("Global VISA Services", system_prompt)
        self.assertIn("Never guarantee visa issuance", system_prompt)
        self.assertIn("Over 10,000 successful visa approvals", system_prompt)
        self.assertIn("Fall 2027 Student Visa Drive", user_prompt)
        self.assertIn("linkedin", user_prompt.lower())

    def test_build_marketing_prompts_whatsapp(self):
        system_prompt, user_prompt = build_marketing_prompts(
            self.brand_info,
            self.campaign_info,
            target_platform="whatsapp",
            language="en"
        )
        self.assertIn("WhatsApp Business Messaging Draft", user_prompt)
        self.assertIn("NOT an automated WhatsApp Status post", user_prompt)
        self.assertIn("whatsapp", user_prompt.lower())

    def test_parse_ai_json_response_clean(self):
        data = {
            "headline": "Plan Your Future",
            "caption": "Get your study visa with trusted experts.",
            "hashtags": "#StudyAbroad #VisaSuccess",
            "call_to_action": "Apply now"
        }
        raw = json.dumps(data)
        parsed = parse_ai_json_response(raw)
        self.assertEqual(parsed["headline"], "Plan Your Future")
        self.assertEqual(parsed["caption"], "Get your study visa with trusted experts.")

    def test_parse_ai_json_response_markdown_blocks(self):
        raw = "```json\n{\"headline\": \"Headline Here\", \"caption\": \"Caption here\", \"hashtags\": \"#test\", \"call_to_action\": \"Click\"}\n```"
        parsed = parse_ai_json_response(raw)
        self.assertEqual(parsed["headline"], "Headline Here")

    def test_parse_ai_json_response_invalid_raises(self):
        with self.assertRaises(AIResponseValidationError):
            parse_ai_json_response("This is not JSON at all.", strict=True)
        with self.assertRaises(AIResponseValidationError):
            parse_ai_json_response("", strict=False)

    def test_mock_provider_all_platforms(self):
        provider = MockAIProvider()
        platforms = ["facebook", "instagram", "linkedin", "x", "whatsapp"]
        for plat in platforms:
            res = provider.generate_for_campaign(
                brand_info=self.brand_info,
                campaign_info=self.campaign_info,
                target_platform=plat,
                language="en"
            )
            self.assertIsInstance(res, GenerationResult)
            self.assertTrue(len(res.headline) > 0)
            self.assertTrue(len(res.caption) > 0)
            self.assertEqual(res.target_platform, plat)
            self.assertEqual(res.ai_provider, "mock")
            d = res.to_dict()
            self.assertIn("headline", d)
            self.assertIn("caption", d)

    def test_mock_provider_simulated_errors(self):
        provider = MockAIProvider()
        
        # Rate limit simulation
        provider.simulate_rate_limit = True
        with self.assertRaises(AIRateLimitError):
            provider.generate_for_campaign(self.brand_info, self.campaign_info, "facebook")
        provider.simulate_rate_limit = False

        # Timeout simulation
        provider.simulate_timeout = True
        with self.assertRaises(AITimeoutError):
            provider.generate_for_campaign(self.brand_info, self.campaign_info, "facebook")
        provider.simulate_timeout = False

        # Invalid JSON simulation
        provider.simulate_invalid_json = True
        with self.assertRaises(AIResponseValidationError):
            provider.generate_for_campaign(self.brand_info, self.campaign_info, "facebook")
        provider.simulate_invalid_json = False

    def test_openai_compatible_missing_key_raises(self):
        provider = OpenAICompatibleProvider(api_key=None, base_url="https://api.example.com/v1", model="test-model")
        with self.assertRaises(AIConfigurationError):
            provider.generate_for_campaign(self.brand_info, self.campaign_info, "linkedin")

    @patch("requests.post")
    def test_openai_compatible_successful_call(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "headline": "Realize Your Dream",
                            "caption": "Join thousands who achieved their dream visas.",
                            "hashtags": "#Visas #Immigration",
                            "call_to_action": "Contact us today"
                        })
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 60,
                "total_tokens": 180
            }
        }
        mock_post.return_value = mock_response

        provider = OpenAICompatibleProvider(
            api_key="sk-test-secret-key-12345",
            base_url="https://api.groq.com/openai/v1",
            model="llama-3.3-70b-versatile"
        )
        res = provider.generate_for_campaign(self.brand_info, self.campaign_info, "linkedin")

        self.assertEqual(res.headline, "Realize Your Dream")
        self.assertEqual(res.call_to_action, "Contact us today")
        self.assertEqual(res.target_platform, "linkedin")
        self.assertEqual(res.metadata.get("total_tokens"), 180)

        # Verify correct headers sent
        args, kwargs = mock_post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer sk-test-secret-key-12345")
        self.assertIn("https://api.groq.com/openai/v1/chat/completions", args[0])

    @patch("requests.post")
    def test_openai_compatible_rate_limit_handling(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        mock_post.return_value = mock_response

        provider = OpenAICompatibleProvider(api_key="test-key", base_url="https://api.openai.com/v1", model="gpt-4o-mini")
        with self.assertRaises(AIRateLimitError):
            provider.generate_for_campaign(self.brand_info, self.campaign_info, "facebook")

    @patch("requests.post")
    def test_openai_compatible_timeout_handling(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")

        provider = OpenAICompatibleProvider(api_key="test-key", base_url="https://api.openai.com/v1", model="gpt-4o-mini")
        with self.assertRaises(AITimeoutError):
            provider.generate_for_campaign(self.brand_info, self.campaign_info, "facebook")

    @patch("requests.post")
    def test_openai_compatible_token_not_leaked_in_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 401
        secret_key = "super-sensitive-secret-token-abcdef"
        mock_response.text = f"Invalid API Key provided: {secret_key}"
        mock_post.return_value = mock_response

        provider = OpenAICompatibleProvider(api_key=secret_key, base_url="https://api.openai.com/v1", model="gpt-4o-mini")
        with self.assertRaises(AIProviderError) as ctx:
            provider.generate_for_campaign(self.brand_info, self.campaign_info, "facebook")
        
        # Verify secret token is NOT leaked in string representation
        self.assertNotIn(secret_key, str(ctx.exception))

    def test_factory_get_ai_provider(self):
        mock_p = get_ai_provider("mock")
        self.assertIsInstance(mock_p, MockAIProvider)

        groq_p = get_ai_provider("groq", api_key="groq-key")
        self.assertIsInstance(groq_p, GroqProvider)
        self.assertEqual(groq_p.base_url, "https://api.groq.com/openai/v1")

        openai_p = get_ai_provider("openai", api_key="openai-key")
        self.assertIsInstance(openai_p, OpenAIProvider)
        self.assertEqual(openai_p.base_url, "https://api.openai.com/v1")

        with self.assertRaises(AIConfigurationError):
            get_ai_provider("non_existent_provider_foo_bar")

    def test_prompt_length_budget_truncation(self):
        # Create oversized campaign brief and positioning
        huge_brief = "Huge marketing brief detail sentence. " * 300  # ~11,000 chars
        huge_camp = dict(self.campaign_info)
        huge_camp['brief'] = huge_brief

        huge_brand = dict(self.brand_info)
        huge_brand['positioning'] = "Brand position statement. " * 100 # ~2,600 chars

        sys_prompt, usr_prompt = build_marketing_prompts(
            brand_info=huge_brand,
            campaign_info=huge_camp,
            target_platform="facebook"
        )
        total_len = len(sys_prompt) + len(usr_prompt)
        import config
        self.assertLessEqual(total_len, getattr(config, 'AI_MAX_PROMPT_CHARS', 8000))
        self.assertIn("[truncated]", usr_prompt)

    def test_generate_content_token_capping(self):
        provider = MockAIProvider()
        with patch.object(provider, 'generate', wraps=provider.generate) as mock_gen:
            generate_campaign_content(
                provider=provider,
                brand_info=self.brand_info,
                campaign_info=self.campaign_info,
                target_platform="facebook",
                max_tokens=99999
            )
            import config
            _, kwargs = mock_gen.call_args
            self.assertEqual(kwargs['max_tokens'], getattr(config, 'AI_MAX_OUTPUT_TOKENS', 1500))

    def test_campaign_strategy_generation(self):
        provider = MockAIProvider()
        strat = generate_campaign_strategy(
            provider=provider,
            brand_info=self.brand_info,
            campaign_info=self.campaign_info
        )
        required_keys = [
            'positioning', 'primary_objective', 'target_segments', 'pain_points',
            'value_proposition', 'core_message', 'supporting_messages', 'content_themes',
            'recommended_channels', 'calls_to_action', 'suggested_phases',
            'posting_frequency', 'success_metrics', 'risks_and_verification'
        ]
        for k in required_keys:
            self.assertIn(k, strat)
            self.assertTrue(len(strat[k]) > 0)
        self.assertIn(self.brand_info['name'], strat['positioning'])

if __name__ == "__main__":
    unittest.main()
