"""
PostPilot Creative Validation & Platform Publishing Rules
Enforces platform-specific media constraints, character limits, hashtag counts,
and content format rules for Instagram, X (Twitter), LinkedIn, and Facebook.
"""
import re

PLATFORM_LIMITS = {
    'instagram': {
        'max_caption_length': 2200,
        'max_hashtags': 30,
        'requires_media': True,
        'allowed_file_types': {'image', 'video'}
    },
    'x': {
        'max_caption_length': 280,
        'max_hashtags': 10,
        'requires_media': False,
        'allowed_file_types': {'image', 'video'}
    },
    'twitter': {
        'max_caption_length': 280,
        'max_hashtags': 10,
        'requires_media': False,
        'allowed_file_types': {'image', 'video'}
    },
    'linkedin': {
        'max_caption_length': 3000,
        'max_hashtags': 30,
        'requires_media': False,
        'allowed_file_types': {'image', 'video', 'document'}
    },
    'facebook': {
        'max_caption_length': 63206,
        'max_hashtags': 30,
        'requires_media': False,
        'allowed_file_types': {'image', 'video'}
    }
}

def validate_platform_creative(platform, caption="", headline="", hashtags="", media_asset=None, content_format="post"):
    """
    Validates marketing content against platform-specific publication constraints.
    Returns (is_valid: bool, issues: list[str])
    """
    clean_platform = str(platform or 'facebook').strip().lower()
    limits = PLATFORM_LIMITS.get(clean_platform, PLATFORM_LIMITS['facebook'])
    issues = []

    text_content = str(caption or "").strip()
    if not text_content:
        issues.append("Post caption/body cannot be empty.")

    max_len = limits['max_caption_length']
    if len(text_content) > max_len:
        issues.append(f"{clean_platform.capitalize()} caption exceeds {max_len} character limit ({len(text_content)} chars).")

    # Hashtags count
    combined_tags = f"{text_content} {str(hashtags or '')}"
    found_tags = set(re.findall(r'#\w+', combined_tags))
    max_tags = limits['max_hashtags']
    if len(found_tags) > max_tags:
        issues.append(f"{clean_platform.capitalize()} allows at most {max_tags} hashtags ({len(found_tags)} detected).")

    # Media requirements
    if limits['requires_media'] and not media_asset:
        issues.append(f"{clean_platform.capitalize()} publishing requires an attached image or video asset.")

    if media_asset:
        file_type = str(media_asset.get('file_type') or 'image').lower()
        if file_type not in limits['allowed_file_types']:
            issues.append(f"{clean_platform.capitalize()} does not support '{file_type}' assets. Allowed: {sorted(list(limits['allowed_file_types']))}.")

    return (len(issues) == 0, issues)
