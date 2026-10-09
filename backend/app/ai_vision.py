import base64
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import httpx
from .config import GEMINI_API_KEY, VISION_AI_MODEL, VISION_AI_PROVIDER, VISION_AI_TIMEOUT

logger = logging.getLogger("infrapulse.ai_vision")

VISION_PROMPT_TEMPLATE = """You are an objective infrastructure verification analyst for rural public works monitoring.
Analyze this field photograph against the claimed infrastructure record and the community resident's observation.

CLAIMED DEVELOPMENT RECORD:
- Asset / Project Name: {asset_name}
- Dimension: {dimension}
- Description / Scope: {description}
- Admin Reported Status: {reported_status}

COMMUNITY RESIDENT REPORT:
- Observed Status: {observed_status}
- Resident Notes: {resident_notes}

INSTRUCTIONS:
1. Examine what visual features are clearly identifiable in the image.
2. Compare them against the claim and the user observation.
3. Express honest uncertainty. Do NOT claim the photo proves legal ownership or engineering-grade structural integrity from a single image.
4. Return ONLY a single valid JSON object with the exact keys specified below and NO other markdown formatting or text.

REQUIRED JSON FORMAT:
{{
  "summary": "Brief 1-2 sentence description of what the photograph depicts",
  "visible_elements": ["list", "of", "concrete visual objects or structures observed"],
  "relation_to_claim": "supports | partially_supports | contradicts | inconclusive | not_relevant",
  "apparent_condition": "appears_functional | appears_incomplete | appears_damaged | not_assessable | not_applicable",
  "observations": "Objective remarks comparing the visible site to the reported claim",
  "uncertainties_and_limitations": "Camera angles, weather, partial obstructions, or visual ambiguities",
  "possible_privacy_or_safety_issue": "none_detected | faces_or_bystanders_present | hazardous_condition_visible",
  "recommended_human_review": "standard | recommended | priority_review"
}}
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def analyze_evidence_image_sync(
    image_bytes: bytes,
    claim_details: Dict[str, Any],
    user_observation: Dict[str, Any],
    mime_type: str = "image/jpeg",
) -> Dict[str, Any]:
    """
    Server-side AI image analysis.
    If GEMINI_API_KEY is not configured or fails, returns an honest fallback status
    so the human verification workflow proceeds without error.
    """
    if not GEMINI_API_KEY or VISION_AI_PROVIDER in ("disabled", "none"):
        return {
            "status": "not_configured",
            "provider": VISION_AI_PROVIDER or "gemini",
            "model_name": VISION_AI_MODEL,
            "summary": "Automated vision analysis is currently unconfigured (GEMINI_API_KEY not set).",
            "visible_elements": [],
            "relation_to_claim": "inconclusive",
            "apparent_condition": "not_assessable",
            "observations": "Image saved securely for human reviewer inspection.",
            "uncertainties_and_limitations": "No automated inference was executed.",
            "possible_privacy_or_safety_issue": "none_detected",
            "recommended_human_review": "standard",
            "analyzed_at": _now_iso(),
            "error_message": None,
        }

    # Prepare prompt
    prompt = VISION_PROMPT_TEMPLATE.format(
        asset_name=claim_details.get("asset_or_project_name", "Unknown asset"),
        dimension=claim_details.get("dimension", "General infrastructure"),
        description=claim_details.get("description", "No description provided"),
        reported_status=claim_details.get("reported_status", "Reported status not specified"),
        observed_status=user_observation.get("observed_status", "Unspecified"),
        resident_notes=user_observation.get("notes", "None"),
    )

    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_image,
                        }
                    },
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1024,
            "responseMimeType": "application/json",
        },
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{VISION_AI_MODEL}:generateContent?key={GEMINI_API_KEY}"

    try:
        with httpx.Client(timeout=VISION_AI_TIMEOUT) as client:
            resp = client.post(url, json=payload)
            if resp.status_code != 200:
                logger.warning("Gemini vision API returned non-200: %s %s", resp.status_code, resp.text)
                return {
                    "status": "failed",
                    "provider": "gemini",
                    "model_name": VISION_AI_MODEL,
                    "summary": f"Vision API returned HTTP {resp.status_code}.",
                    "visible_elements": [],
                    "relation_to_claim": "inconclusive",
                    "apparent_condition": "not_assessable",
                    "observations": "Automated analysis encountered an external API error.",
                    "uncertainties_and_limitations": "API error response.",
                    "possible_privacy_or_safety_issue": "none_detected",
                    "recommended_human_review": "priority_review",
                    "analyzed_at": _now_iso(),
                    "error_message": f"HTTP {resp.status_code}",
                }

            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return {
                    "status": "failed",
                    "provider": "gemini",
                    "model_name": VISION_AI_MODEL,
                    "summary": "Vision API returned no candidate response.",
                    "visible_elements": [],
                    "relation_to_claim": "inconclusive",
                    "apparent_condition": "not_assessable",
                    "observations": "Model declined to analyze or safety filter tripped.",
                    "uncertainties_and_limitations": "Empty candidates list.",
                    "possible_privacy_or_safety_issue": "none_detected",
                    "recommended_human_review": "priority_review",
                    "analyzed_at": _now_iso(),
                    "error_message": "No candidates returned",
                }

            raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")

            # Clean JSON markdown if wrapped in ```json ... ```
            cleaned = re.sub(r"^```json\s*", "", raw_text.strip(), flags=re.MULTILINE)
            cleaned = re.sub(r"```$", "", cleaned.strip(), flags=re.MULTILINE)

            parsed = json.loads(cleaned)

            return {
                "status": "complete",
                "provider": "gemini",
                "model_name": VISION_AI_MODEL,
                "summary": str(parsed.get("summary", "Analysis completed.")),
                "visible_elements": list(parsed.get("visible_elements", [])),
                "relation_to_claim": str(parsed.get("relation_to_claim", "inconclusive")),
                "apparent_condition": str(parsed.get("apparent_condition", "not_assessable")),
                "observations": str(parsed.get("observations", "")),
                "uncertainties_and_limitations": str(parsed.get("uncertainties_and_limitations", "")),
                "possible_privacy_or_safety_issue": str(parsed.get("possible_privacy_or_safety_issue", "none_detected")),
                "recommended_human_review": str(parsed.get("recommended_human_review", "standard")),
                "analyzed_at": _now_iso(),
                "error_message": None,
            }
    except Exception as exc:
        logger.error("Vision AI execution exception: %s", exc)
        return {
            "status": "failed",
            "provider": "gemini",
            "model_name": VISION_AI_MODEL,
            "summary": "Vision analysis could not be completed.",
            "visible_elements": [],
            "relation_to_claim": "inconclusive",
            "apparent_condition": "not_assessable",
            "observations": "Analysis failed due to a network or parsing error.",
            "uncertainties_and_limitations": str(exc),
            "possible_privacy_or_safety_issue": "none_detected",
            "recommended_human_review": "priority_review",
            "analyzed_at": _now_iso(),
            "error_message": str(exc),
        }

