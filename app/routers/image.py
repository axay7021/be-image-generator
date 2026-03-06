import io
import logging
from datetime import date, datetime, timezone
from typing import Annotated
from uuid import uuid4

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from google import genai
from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.db import get_db
from app.db.schema import ImageLog, User
from app.dependencies.quota import check_quota, increment_quota
from app.dependencies.user_auth import get_current_user_optional

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(tags=["Image Modification"])

# Initialize Gemini Client
if not settings.GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY environment variable not set")
    client = None
else:
    client = genai.Client(api_key=settings.GEMINI_API_KEY)

# Initialize face detector (using OpenCV's DNN model for better accuracy)
face_detector = None
try:
    # Use OpenCV's DNN face detector (more accurate than Haar Cascade)
    face_detector = cv2.FaceDetectorYN.create(
        model="",  # Empty string uses the built-in model
        config="",
        input_size=(320, 320),
        score_threshold=0.85,
        nms_threshold=0.3,
        top_k=5000,
    )
except Exception as e:
    logger.warning(f"Could not initialize FaceDetectorYN, will use Haar Cascade: {e}")
    face_detector = None


def detect_face_mediapipe(image_bytes):
    """Detects if a face is present in the image using OpenCV."""
    try:
        # Convert bytes to numpy array
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return 0

        # Resize for consistency and speed (max 1024 width)
        max_width = 1024
        if img.shape[1] > max_width:
            ratio = max_width / img.shape[1]
            new_height = int(img.shape[0] * ratio)
            img = cv2.resize(img, (max_width, new_height))

        # Try DNN-based detector first
        if face_detector is not None:
            try:
                face_detector.setInputSize((img.shape[1], img.shape[0]))
                _, faces = face_detector.detect(img)
                if faces is not None:
                    return len(faces)
            except Exception as e:
                logger.warning(f"DNN face detection failed: {e}")

        # Fallback to Haar Cascade
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        # Use minSize=(100, 100) on a max 1024px image to ensure we capture the prominent subject
        # and ignore smaller background faces or false positives in complex textures.
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=8, minSize=(100, 100))

        return len(faces)

    except Exception as e:
        logger.error(f"Error in face detection: {e}")
        return 0


def is_real_human_face(image_bytes: bytes) -> bool:
    """
    Multi-signal heuristic to detect if an image is a real photograph vs. a cartoon,
    illustrated image, or a completely unrelated image (e.g. a UI screenshot).

    Measured signal values derived from actual test images:

    Signal              | Cartoon | Mobile UI | Real Photo
    --------------------|---------|-----------|------------
    flat_ratio (< 5px)  | 0.934   | 0.756     | ~0.75-0.80
    mean_gradient       | 42.5    | 107.5     | ~30-55

    Strategy:
    - Cartoon veto:     flat_ratio > 0.90  (cartoon=0.93 vs real~0.75 — clear gap)
    - UI veto:          mean_gradient > 80  (UI=107 vs real~35-55 — clear gap)
    - Soft gate:        2+ of (low saturation, low laplacian, low skin) for remaining cases

    Returns True if image appears to be a real photograph, False otherwise.
    Fails open (returns True) on errors to avoid false-negatives.
    """
    # Hard-veto thresholds (each strong enough to reject a specific class alone)
    MAX_FLAT_RATIO = 0.90  # Cartoon veto: >90% adjacent pixels identical → solid fills
    MAX_MEAN_GRADIENT = 80.0  # UI/screenshot veto: sharp hard edges throughout image

    # Soft-gate thresholds (multi-signal scoring for remaining edge cases)
    MIN_SATURATION_STD = 22.0
    MIN_LAPLACIAN_VAR = 120.0
    MIN_SKIN_RATIO = 0.03
    CARTOON_SIGNAL_THRESHOLD = 2

    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return True  # Fail open

        analysis_img = cv2.resize(img, (256, 256))
        total_pixels = 256 * 256

        # Keep gray as uint8 — OpenCV Sobel/Laplacian require uint8 or specific dtypes.
        # Cast to float32 only for numpy diff operations that need signed arithmetic.
        gray_uint8 = cv2.cvtColor(analysis_img, cv2.COLOR_BGR2GRAY)
        gray_float = gray_uint8.astype(np.float32)

        # Flat-region ratio: fraction of adjacent pixel pairs with intensity diff < 5.
        # Cartoons have large solid-fill areas → very high flat_ratio (~0.93).
        # Real photos have skin-tone gradients → lower flat_ratio (~0.75).
        FLAT_DIFF_THRESHOLD = 5
        h_diff = np.abs(np.diff(gray_float, axis=1))
        v_diff = np.abs(np.diff(gray_float, axis=0))
        flat_ratio = float((np.mean(h_diff < FLAT_DIFF_THRESHOLD) + np.mean(v_diff < FLAT_DIFF_THRESHOLD)) / 2)

        # Mean Sobel gradient magnitude.
        # UI screenshots have many sharp hard edges → high mean_gradient (~107).
        # Real photos and cartoons score much lower (~30-55).
        sobelx = cv2.Sobel(gray_uint8, cv2.CV_32F, 1, 0, ksize=3)
        sobely = cv2.Sobel(gray_uint8, cv2.CV_32F, 0, 1, ksize=3)
        mean_gradient = float(np.mean(np.sqrt(sobelx**2 + sobely**2)))

        # Saturation std-dev (soft gate signal 1)
        hsv = cv2.cvtColor(analysis_img, cv2.COLOR_BGR2HSV)
        sat_std = float(np.std(hsv[:, :, 1].astype(np.float32)))

        # Laplacian variance (soft gate signal 2)
        laplacian_var = float(cv2.Laplacian(gray_uint8, cv2.CV_32F).var())

        # Skin-tone ratio via YCrCb (soft gate signal 3)
        ycrcb = cv2.cvtColor(analysis_img, cv2.COLOR_BGR2YCrCb)
        skin_mask = cv2.inRange(
            ycrcb,
            np.array([0, 133, 77], dtype=np.uint8),
            np.array([255, 173, 127], dtype=np.uint8),
        )
        skin_ratio = float(np.count_nonzero(skin_mask)) / total_pixels

        logger.debug(
            f"Realism check — flat_ratio={flat_ratio:.4f}, mean_gradient={mean_gradient:.2f}, "
            f"sat_std={sat_std:.2f}, laplacian_var={laplacian_var:.2f}, skin_ratio={skin_ratio:.4f}"
        )

        # --- Hard veto 1: cartoon / flat-fill illustration ---
        if flat_ratio > MAX_FLAT_RATIO:
            logger.info(f"Image rejected (cartoon veto): flat_ratio={flat_ratio:.4f}")
            return False

        # --- Hard veto 2: UI screenshot / non-photo image ---
        if mean_gradient > MAX_MEAN_GRADIENT:
            logger.info(f"Image rejected (UI veto): mean_gradient={mean_gradient:.2f}")
            return False

        # --- Soft gate for remaining edge cases ---
        cartoon_signals = 0
        if sat_std < MIN_SATURATION_STD:
            cartoon_signals += 1
        if laplacian_var < MIN_LAPLACIAN_VAR:
            cartoon_signals += 1
        if skin_ratio < MIN_SKIN_RATIO:
            cartoon_signals += 1

        if cartoon_signals >= CARTOON_SIGNAL_THRESHOLD:
            logger.info(f"Image rejected (soft gate): {cartoon_signals}/3 soft signals failed")
            return False

        return True

    except Exception as e:
        logger.error(f"Error in animated/cartoon face detection: {e}")
        return True  # Fail open on error


def process_gemini_image(input_image_bytes, prompt):
    """Sends image and prompt to Gemini and returns (modified_image_bytes, cost_info, error_message)."""
    if not client:
        raise ValueError("GEMINI_API_KEY not set")

    response = client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=[
            types.Part.from_bytes(data=input_image_bytes, mime_type="image/jpeg"),
            prompt,
        ],
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )

    cost_info = {"tokens": 0, "cost_usd": 0.0, "cost_inr": 0.0}

    # Calculate and log cost
    try:
        if response.usage_metadata:
            # Pricing logic (simplified from POC)
            USD_TO_INR = 85.0
            COST_PER_1M_INPUT_TOKENS = 0.075
            COST_PER_1M_OUTPUT_TOKENS = 0.30

            input_tokens = response.usage_metadata.prompt_token_count or 0
            output_tokens = response.usage_metadata.candidates_token_count or 0

            input_cost_usd = (input_tokens / 1_000_000) * COST_PER_1M_INPUT_TOKENS
            output_cost_usd = (output_tokens / 1_000_000) * COST_PER_1M_OUTPUT_TOKENS
            total_cost_usd = input_cost_usd + output_cost_usd
            total_cost_inr = total_cost_usd * USD_TO_INR

            cost_info = {"tokens": input_tokens + output_tokens, "cost_usd": total_cost_usd, "cost_inr": total_cost_inr}

    except Exception as e:
        logger.error(f"Error calculating cost: {e}")

    # Extract the image from the response parts
    if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                return part.inline_data.data, cost_info, None

    # Map Gemini finish reasons to user-friendly messages.
    # These are policy/safety refusals — expose a clear message without leaking internals.
    FINISH_REASON_MESSAGES = {
        "NO_IMAGE": (
            "The image could not be processed due to content policy restrictions. "
            "Please try a different image or adjust your request."
        ),
        "SAFETY": (
            "Your request was blocked by content safety filters. "
            "Please ensure the image and instructions do not contain restricted content."
        ),
        "RECITATION": (
            "The request was rejected to prevent reproduction of restricted content. "
            "Please modify your instructions and try again."
        ),
        "OTHER": ("The image generation was declined. Please try a different image or simplify your request."),
        "MAX_TOKENS": ("The request was too complex to process. Please simplify your instructions and try again."),
        "BLOCKLIST": (
            "Your request contains terms that are not permitted. Please revise your instructions and try again."
        ),
        "PROHIBITED_CONTENT": (
            "The request contains prohibited content and cannot be processed. "
            "Please use an appropriate image and instructions."
        ),
        "SPII": (
            "The request was blocked because it may contain sensitive personal information. "
            "Please remove any personal identifiers from your instructions."
        ),
    }

    finish_reason_str = None
    is_policy_violation = False

    if response.candidates:
        candidate = response.candidates[0]
        if candidate.finish_reason:
            # FinishReason enum → strip prefix, e.g. "FinishReason.NO_IMAGE" → "NO_IMAGE"
            raw = f"{candidate.finish_reason}"
            finish_reason_str = raw.split(".")[-1] if "." in raw else raw
            is_policy_violation = finish_reason_str in FINISH_REASON_MESSAGES
            logger.warning(f"Gemini Refusal: finish_reason={finish_reason_str}")

    logger.error(f"No image found in response. Full Response: {response}")

    user_message = FINISH_REASON_MESSAGES.get(
        finish_reason_str,
        "Failed to process image. Please try again with a different image.",
    )
    return None, cost_info, {"user_message": user_message, "is_policy_violation": is_policy_violation}


@router.post("/validate-image")
async def validate_image(file: UploadFile = File(...)):
    try:
        image_bytes = await file.read()
        face_count = detect_face_mediapipe(image_bytes)

        logger.info(f"Face count: {face_count}")

        if face_count == 0:
            return {
                "valid": False,
                "message": "No human face detected. Please upload a photo with a visible face.",
                "debug_count": face_count,
            }

        if face_count > 1:
            return {
                "valid": False,
                "message": "Multiple faces detected. Please upload a photo with only one face.",
                "debug_count": face_count,
            }

        logger.info("Real face detected")
        logger.info(is_real_human_face(image_bytes))

        if not is_real_human_face(image_bytes):
            return {
                "valid": False,
                "message": "Animated or illustrated images are not supported. Please upload a real photograph.",
                "debug_count": face_count,
            }

        return {"valid": True, "message": "Face detected.", "debug_count": face_count}
    except Exception as e:
        logger.error(f"Validation error: {e}")
        return {"valid": False, "message": "Error validating image."}


@router.post("/upscale")
async def upscale_image(
    request: Request,
    file: UploadFile = File(...),
    target_resolution: str | None = Form(None, description="Target resolution: '2K' or '4K'"),
    target_width: str | None = Form(None, description="Target width in pixels (e.g. '2560')"),
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    user: Annotated[User | None, Depends(get_current_user_optional)] = None,
):
    try:
        # 1. Resolve Resolution/Width Input
        # Frontend may send 'target_width' (2560/3840) instead of 'target_resolution'
        resolved_resolution = target_resolution

        if not resolved_resolution and target_width:
            if str(target_width) == "2560":
                resolved_resolution = "2K"
            elif str(target_width) == "3840":
                resolved_resolution = "4K"
            elif str(target_width).lower() == "original":
                resolved_resolution = "Original"
            else:
                # Fallback for custom widths if we ever support them, or treat as error
                pass

        if not resolved_resolution:
            # If neither is provided (or successfully mapped)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Missing 'target_resolution' or valid 'target_width'.",
            )

        # 2. Resolution & Cost Logic
        target_width_val = 0
        cost = 0
        is_original = False

        if resolved_resolution == "Original":
            cost = 0
            is_original = True
        elif resolved_resolution == "2K":
            target_width_val = 2560
            cost = 2
        elif resolved_resolution == "4K":
            target_width_val = 3840
            cost = 4
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid resolution. Supported options: 'Original', '2K', '4K'.",
            )

        # 1. Access Control: Paid Users Only (SKIP for Original)
        if not is_original and not user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Upscaling is a premium feature. Please sign in and subscribe to a plan. You can download the Original for free.",
            )

        # 3. Check Quota (pre-deduction check)
        await check_quota(request, db, user, cost=cost)

        image_bytes = await file.read()
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise ValueError("Could not decode image")

        final_img = img

        if not is_original:
            # Calculate height to maintain aspect ratio
            original_height, original_width = img.shape[:2]
            aspect_ratio = original_height / original_width
            target_height = int(target_width_val * aspect_ratio)

            # High Quality Upscaling (Lanczos)
            upscaled_img = cv2.resize(img, (target_width_val, target_height), interpolation=cv2.INTER_LANCZOS4)

            # Apply Sharpening
            gaussian = cv2.GaussianBlur(upscaled_img, (0, 0), 2.0)
            sharpened = cv2.addWeighted(upscaled_img, 1.5, gaussian, -0.5, 0)
            final_img = sharpened
        _, encoded_img = cv2.imencode(".png", final_img)

        # 4. Deduct Quota
        await increment_quota(request, db, user, cost=cost)

        # Log to ImageLog
        log_entry = ImageLog(
            user_id=str(user.id) if user else None,
            action="upscale",
            gemini_tokens_used=0,  # Local processing
            cost_inr=0.0,  # Free for now? Or calc server cost? Assuming 0 API cost.
        )
        db.add(log_entry)
        await db.commit()

        return Response(content=encoded_img.tobytes(), media_type="image/png")

    except Exception as e:
        logger.error(f"Upscaling error: {e}")
        raise HTTPException(status_code=500, detail="Failed to upscale image") from e


@router.post("/modify-image/{action}")
async def modify_image(
    action: str,
    request: Request,
    file: UploadFile = File(...),
    extra_context: str = Form(None),
    passport_mode: str = Form(None),
    suit_color: str = Form(None),
    tie_color: str = Form(None),
    style: str = Form(None),
    category: str = Form(None),  # Alias for style
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    user: Annotated[User | None, Depends(get_current_user_optional)] = None,
    quota_remaining: int = Depends(check_quota),  # Check quota first
):
    try:
        image_bytes = await file.read()

        # Face validation is only required for actions that specifically modify a person's portrait.
        # Actions like remove-object, remove-bg, change-bg, and custom-edit work on general images.
        FACE_REQUIRED_ACTIONS = {"passport-size", "linkedin-profile"}

        if action in FACE_REQUIRED_ACTIONS:
            face_count = detect_face_mediapipe(image_bytes)

            if face_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No human face detected. Please upload a photo with a visible face.",
                )

            if face_count > 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Multiple faces detected. Only one face is allowed per image.",
                )

            if not is_real_human_face(image_bytes):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Animated or illustrated images are not supported. Please upload a real photograph.",
                )

        # Prompt construction (Simplified from POC for brevity, ideally share logic)
        # Using POC logic copy-paste where possible

        prompt = ""
        safety_instruction = (
            " CRITICAL INSTRUCTION: Preserve the person's face exactly as is. Do not alter facial features."
        )

        if action == "remove-bg":
            prompt = "Remove the background of this image. Keep only the main subject."
            if extra_context:
                prompt += f" Additional requirements: {extra_context}"

        elif action == "passport-size":
            # Enhanced Prompt for Realism and Pose Correction
            base_prompt = (
                "Transform this image into a photorealistic, professional passport photo. "
                "1. COMPOSITION: Create a standard head-and-shoulders crop. If the person is sitting or in an awkward pose, "
                "reframe strictly by cropping and alignment ONLY to a straight, upright portrait view. "
                "NO facial reshaping or perspective correction is allowed. "
                "2. TEXTURE & REALISM: CRITICAL. The face must look 100% natural and human. "
                "Skin must appear exactly like a real camera photograph, not filtered or processed. "
                "Retain real skin pores, uneven texture, micro-contrast, fine lines, blemishes, shadows, and camera grain. "
                "Do NOT smooth, denoise, blur, beautify, polish, stylize, or enhance skin in any way. "
                "The skin must NOT look waxy, plastic, airbrushed, CGI, AI-generated, or beauty-filtered. "
                "3. LIGHTING: Use soft, studio-quality lighting with natural falloff. "
                "Lighting adjustments are limited to exposure and white balance ONLY. "
                "Lighting must NOT alter skin texture or facial shape. "
                "4. REQUIREMENTS: Front-facing, neutral-professional expression with a slight natural closed-lip smile. "
                "Pure white background."
            )

            # Absolute skin + geometry realism lock (Gemini Flash hard constraint)
            skin_realism_block = (
                "ABSOLUTE SKIN & FACE GEOMETRY LOCK (HIGHEST PRIORITY): "
                "The facial skin AND facial structure MUST be directly inherited pixel-for-pixel from the source image. "
                "The model is NOT allowed to regenerate, reinterpret, or reconstruct the face. "
                "Preserve original skin texture, pores, noise, contrast, shadows, and imperfections exactly as captured. "
                "NO denoising, NO smoothing, NO beauty filters, NO AI enhancement, NO texture averaging. "
                "FACE SHAPE LOCK: "
                "Facial proportions MUST remain IDENTICAL to the source image. "
                "Do NOT slim, widen, round, squeeze, sharpen, or reshape the face in any way. "
                "Oval, round, jawline, cheek width, chin shape, forehead height, and face length MUST remain unchanged. "
                "ANTI-AI CONSTRAINT: "
                "The result must look indistinguishable from a real passport photo taken with a DSLR or smartphone camera. "
                "It must NOT resemble an AI portrait, illustration, retouched photo, or beauty-shot. "
                "EDIT BOUNDARY RULE: "
                "You may ONLY perform the following edits: "
                "crop, rotation, background replacement (pure white), exposure correction, hair grooming, clothing changes. "
                "You are STRICTLY FORBIDDEN from redrawing, repainting, reshaping, or re-texturing the face. "
                "FAIL CONDITION: "
                "If exact human skin texture OR exact face shape cannot be preserved, "
                "you MUST keep the original face unchanged and apply ONLY cropping and background replacement."
            )

            # Strict preservation for composite tasks (Suit/Custom)
            # We want to edit the clothes/hair but keep the face RAW.

            if passport_mode == "suit":
                prompt = (
                    f"{base_prompt} "
                    f"{skin_realism_block} "
                    f"IDENTITY LOCK: "
                    f"Eyes, nose, mouth size, jawline, cheekbones, and overall face proportions must remain EXACTLY the same. "
                    f"EDIT LIMITATION: "
                    f"Only a minimal mouth adjustment for a closed-lip smile is allowed, "
                    f"and it MUST NOT affect surrounding skin or face geometry. "
                    f"OUTFIT: Realistic {suit_color} suit, {tie_color} tie, white shirt."
                )

            elif passport_mode == "custom":
                prompt = (
                    f"{base_prompt} "
                    f"{skin_realism_block} "
                    f"CRITICAL: Facial identity, face shape, and skin texture must remain EXACTLY as the source image. "
                    f"Allowed changes are limited strictly to hair styling and expression. "
                    f"CUSTOM INSTRUCTION: {extra_context}"
                )

            else:  # Standard Mode - Now focuses on QUALITY RESTORATION and POSE CORRECTION
                # We REMOVE the skin_realism_block here because we WANT enhancement (de-blurring).
                prompt = (
                    f"{base_prompt} "
                    "QUALITY ENHANCEMENT INSTRUCTIONS: "
                    "1. POSE CORRECTION: If the person is standing sideways, cross-legged, or angled, you MUST re-generate the body and head to be perfectly FRONT-FACING. "
                    "The final result must be a standard, straight passport portrait. "
                    "2. DE-BLUR & UPSCALE: If the source image is blurry, low-resolution, or noisy, you MUST fix it. "
                    "Restore definition to the eyes, hair, and skin. Sharpen details to create a high-quality professional photo. "
                    "3. IDENTITY PRESERVATION: While creating clarity, ensure the person is recognizable as the same individual. "
                    "4. OUTFIT: Keep the original clothing style but straighten it, clean it up, and make it look neat and professional."
                )
                if extra_context:
                    prompt += f" Additional requirements: {extra_context}"

        elif action == "change-bg":
            bg_style_configs = {
                "white": "pure plain white background (Hex #FFFFFF), no shadows, no gradients",
                "black": "pure solid black background (Hex #000000)",
                "grey": "solid neutral grey background (Hex #808080)",
                "warm_grey": "solid warm grey background (Hex #A9A9A9)",
                "cool_grey": "solid cool grey background (Hex #708090)",
                "blue": "solid deep corporate blue background (Hex #2d4d74), matte finish",
                "gradient_blue": "professional radial gradient background, dark blue to lighter blue (linear-gradient #00c6ff to #0072ff)",
                "gradient_grey": "professional radial gradient background, dark grey to lighter grey (linear-gradient #bdc3c7 to #2c3e50)",
                # "office": "blurred modern office background, professional corporate setting",
                "plain": "solid flat color background (Hex #E0E0E0)",
                "studio": "professional dark grey studio background (Hex #333333) with rim lighting",
            }

            # Resolve background request
            bg_input = category or style
            bg_description = "pure plain white background"  # Default fallback

            if bg_input:
                normalized_bg = bg_input.lower().replace(" ", "_").replace("-", "_")

                if normalized_bg in bg_style_configs:
                    bg_description = bg_style_configs[normalized_bg]
                elif (normalized_bg == "custom" or normalized_bg not in bg_style_configs) and extra_context:
                    # Fallback to extra_context if category is custom/unknown but context is provided
                    bg_description = extra_context
            elif extra_context:
                # No category specified, but context provided
                bg_description = extra_context

            # Log resolved description
            logger.info(f"DEBUG: Resolved Background Description: '{bg_description}' from input '{bg_input}'")

            prompt = (
                f"Extract the main subject from this image with high-precision edge detection. "
                f"Replace the ENTIRE background with: {bg_description}. "
                f"CRITICAL: The background must be exactly '{bg_description}'. "
                f"Adjust the subject's lighting, shadows, and color temperature to perfectly match the new environment "
                f"so the integration looks photorealistic and seamless. Do not alter the subject's appearance."
            )
        elif action == "remove-object":
            if not extra_context or not extra_context.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="'extra_context' is required for 'remove-object'. Please specify what object to remove (e.g. 'the red chair in the background').",
                )
            prompt = f"Identify and completely remove the {extra_context.strip()} from this image. Reconstruct the missing area by realistically extending the surrounding textures, patterns, and lighting. The final result must show no traces of the original object and should look like a clean, untouched photograph."
        elif action == "custom-edit":
            prompt = extra_context if extra_context else "Modify this image."
        elif action == "linkedin-profile":
            # Advanced Prompt Architecture for Realism & Pose Adaptation
            # 1. We define the specific visual target for each style (Background + Outfit + Pose)
            # 2. We add a "Photorealism & Integration" block to force the model to blend the subject.
            # 3. We add a "Face Lock" block to strictly preserve identity.

            style_configs = {
                "classic_corporate": {
                    "setting": "A high-end executive boardroom; floor-to-ceiling glass windows with realistic city reflections; natural soft-box interior lighting; depth of field (f/1.8) creating a genuine optical bokeh that separates the subject from the architectural background.",
                    "outfit": "Bespoke navy blue suit in textured wool-crepe fabric; a crisp white cotton shirt showing fine weave detail; silk tie with authentic dimple and natural shadows; fabric shows realistic tension and soft creases at the joints.",
                    "pose": "Professional three-quarter view; relaxed but structured posture; hands resting naturally; eyes focused with a genuine, slight 'smize' (smiling with eyes) for approachable authority.",
                    "vibe": "Senior leadership, authentic, approachable, high-level corporate credibility.",
                    "photography": "Hyper-realistic 85mm portrait; sharp focus on the iris and eyelashes; sub-surface scattering on skin (realistic light penetration); visible skin pores, fine lines, and natural skin follicles; absolutely no digital airbrushing; Rembrandt lighting setup to define facial structure; Shot on 35mm full-frame camera.",
                    "facial_fidelity": "Exact facial geometry mapping; maintain unique birthmarks, subtle skin tone variations, and authentic facial hair texture; preserve the specific jawline and eye-shape of the reference subject; high-fidelity facial reconstruction.",
                },
                "casual_professional": {
                    "setting": "a genuine modern open-plan office with real desks, plants, and ambient daylight coming from large windows; background softly out of focus with realistic depth and light falloff",
                    "outfit": "high-quality smart-casual blazer layered over a premium cotton t-shirt or textured knit sweater with natural fabric creases",
                    "pose": "relaxed posture with slight forward lean, natural arm placement, candid professional body language",
                    "vibe": "approachable, modern, innovative",
                    "photography": "natural window light mixed with soft fill light, 50mm lens look, accurate color grading, realistic shadows, skin imperfections preserved",
                },
                "creative": {
                    "setting": "a real artistic studio space with practical lights, textured walls, and subtle abstract elements in the background rendered through shallow depth of field",
                    "outfit": "black turtleneck or minimalist fashion-forward attire with real fabric texture, optional statement eyewear with realistic reflections",
                    "pose": "expressive yet believable pose, slight head tilt, relaxed facial muscles, natural eye focus",
                    "vibe": "visionary, artistic, confident",
                    "photography": "cinematic lighting with controlled contrast, realistic color science, fine skin detail, no painterly effects or stylization",
                },
                "founder_leader": {
                    "setting": "a minimalist Silicon Valley–style office with floor-to-ceiling windows, natural daylight, subtle city or skyline blur created by real optical depth",
                    "outfit": "premium quarter-zip sweater or modern tech vest layered over a shirt, realistic stitching and fabric weight",
                    "pose": "calm, confident stance with arms crossed or hands gently clasped, relaxed shoulders, direct but natural gaze",
                    "vibe": "visionary leadership, confidence, success",
                    "photography": "natural daylight key light, soft shadow transitions, professional color grading, realistic facial proportions and textures",
                },
                "friendly_approachable": {
                    "setting": "a real café or home-office environment with warm ambient lighting, natural background blur, and authentic interior elements",
                    "outfit": "soft-textured clothing in pastel or warm earth tones, natural drape and fabric folds",
                    "pose": "relaxed shoulders, slight head tilt, genuine smile with natural asymmetry",
                    "vibe": "kind, approachable, trustworthy",
                    "photography": "warm color temperature, shallow depth of field, visible skin texture, realistic teeth and eye reflections",
                },
                "monochrome_bw": {
                    "setting": "a real dark studio backdrop with controlled rim lighting and true shadow falloff, captured in black-and-white photography style",
                    "outfit": "classic dark clothing made of wool, cotton, or leather with visible texture",
                    "pose": "serious, composed pose with strong facial structure emphasis, either cinematic profile or direct gaze",
                    "vibe": "timeless, dramatic, intense",
                    "photography": "high-contrast monochrome grading, preserved skin grain, film-like noise, no artificial smoothing or HDR artifacts",
                },
                "studio_look": {
                    "setting": "a professional photography studio with a seamless dark grey backdrop, evenly lit with real studio light modifiers",
                    "outfit": "perfectly fitted formal wear with realistic tailoring details and natural fabric response to light",
                    "pose": "upright yet relaxed posture, subtle natural asymmetry, calm facial expression",
                    "vibe": "polished, magazine-quality, high-end",
                    "photography": "medium-format look, tack-sharp focus on eyes, realistic skin texture, no plastic or CGI appearance",
                },
                "outdoor_natural": {
                    "setting": "a real outdoor park environment during golden hour, natural sunlight filtering through trees, authentic background blur",
                    "outfit": "business-casual attire with light jacket or blazer, weather-appropriate and naturally worn",
                    "pose": "casual standing pose with relaxed arms, candid and natural body language",
                    "vibe": "fresh, energetic, authentic",
                    "photography": "golden-hour natural light, soft highlights, realistic shadows, accurate skin tones",
                },
                "tech_modern": {
                    "setting": "a real tech workspace or server room with practical LED lighting, subtle blue accents, and realistic depth of field",
                    "outfit": "modern tech fleece or minimalist smart shirt with clean lines and real fabric texture",
                    "pose": "focused, intelligent posture, natural hand placement, engaged expression",
                    "vibe": "future-focused, analytical, tech-savvy",
                    "photography": "cool color balance with accurate skin tones, realistic reflections, no neon glow or synthetic lighting artifacts",
                },
            }

            # Resolve effective style (handle alias)
            style_input = style or category

            # Normalize style input
            normalized_style = (
                style_input.lower().replace(" ", "_").replace("-", "_") if style_input else "classic_corporate"
            )
            logger.info(f"Received style: '{style}', category: '{category}'. Normalized to: '{normalized_style}'")

            if normalized_style not in style_configs:
                logger.warning(
                    f"Style '{normalized_style}' not found in configs. Falling back to 'classic_corporate'. Available keys: {list(style_configs.keys())}"
                )
                normalized_style = "classic_corporate"

            config = style_configs.get(normalized_style, style_configs["classic_corporate"])

            prompt = (
                f"Generate a hyper-realistic LinkedIn headshot of this person. "
                f"STYLE: {normalized_style.replace('_', ' ').title()}. "
                f"SETTING: {config['setting']}. "
                f"OUTFIT: {config['outfit']}. "
                f"POSE: {config['pose']}. "
                f"VIBE: {config['vibe']}. "
                f"PHOTOGRAPHY: {config['photography']}. "
                # "CRITICAL EXECUTION STEPS: "
                # "1. POSE ADAPTATION: You MUST re-generate the subject's body and posture to match the description above. "
                # "Do NOT just paste the original head onto a new background. The head position and neck must align naturally with the new pose. "
                # "2. LIGHTING INTEGRATION: The lighting on the subject's face MUST adapt to the environment. "
                # "If the background is 'warm golden hour', the face must have warm highlights. "
                # "If the background is 'cool tech office', the face must have cool rim lighting. "
                # "Avoid the 'cut-out' or 'sticker' look where the subject looks separate from the background. "
                # "3. FACE ID LOCK: The facial features (eyes, nose, mouth, unique structure) must remain EXACTLY the same as the source image. "
                # "4. SKIN TEXTURE: Preserve natural skin pores, imperfections, and texture. Do NOT use 'beauty filter' smoothing. "
                # "The skin must look like raw, high-end photography, not digital art. "
                # "5. PHOTOREALISM: Use a shallow depth of field (bokeh) to separate the subject from the background realistically. "
                # "Ensure correct ambient occlusion (shadows) where the collar meets the neck and where hair meets the background."
            )

            if extra_context:
                prompt += f" ADDITIONAL USER REQUIREMENTS: {extra_context}"

        prompt += safety_instruction

        # Global Negative Prompt / Brand Safety
        prompt += (
            " FINAL STYLIZATION RULE: The output image must be completely clean and strictly photorealistic. "
            "ABSOLUTELY NO watermarks, logos, text overlays, brand identifiers, icons, or graphic elements of any kind. "
            "SPECIFICALLY: Do NOT include any 'Gemini' logo, Google branding, or AI generation watermarks. "
            "The image must appear exactly like a photo taken with a camera, with zero digital artifacts or signatures. "
            "If any such elements are detected in the source, they must be seamlessly removed."
        )

        print(prompt)
        print("default prompt")

        modified_image_data, cost_info, error_msg = process_gemini_image(image_bytes, prompt)

        if modified_image_data:
            # Increment quota and Log usage
            await increment_quota(request, db, user)

            # Log to ImageLog
            log_entry = ImageLog(
                user_id=str(user.id) if user else None,
                action=f"modify-image-{action}",
                gemini_tokens_used=cost_info["tokens"],
                cost_inr=cost_info["cost_inr"],
            )
            db.add(log_entry)
            await db.commit()

            response = StreamingResponse(io.BytesIO(modified_image_data), media_type="image/png")

            # For anonymous users: set a stable session cookie so the quota is
            # enforced even when Cloudflare rotates the edge IP between requests.
            if not user:
                session_id = request.cookies.get("anon_session") or str(uuid4())
                # Expire at midnight UTC today so it resets with the daily quota
                midnight_utc = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
                midnight_ts = int(midnight_utc.timestamp()) + 86400  # next midnight
                response.set_cookie(
                    key="anon_session",
                    value=session_id,
                    httponly=True,
                    samesite="lax",
                    max_age=midnight_ts - int(datetime.now(timezone.utc).timestamp()),
                )

            return response

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
            if error_msg and error_msg.get("is_policy_violation")
            else status.HTTP_400_BAD_REQUEST,
            detail=error_msg["user_message"] if error_msg else "Failed to process image (no output from model)",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error processing image")
        raise HTTPException(status_code=500, detail=str(e)) from e
