from __future__ import annotations

import base64
import os
from pathlib import Path

from .schemas import ScenePlan

SYSTEM_PROMPT = """You are the semantic planning module for APainting, a compiler for one fixed art distribution:
elegant botanical single-line stationery illustrations on warm white paper, with thin black organic contours,
sparse composition, and small soft pastel accents.

Important architecture rule: semantic ownership MUST NOT come from bounding boxes.
You will see the original image plus visual-token atlas tiles. Each colored/labeled token C#### is a coherent local
line component created by geometry. Use your vision to assign those visual tokens to Drawing Units.

Your task:
1. Identify 4-16 macro Drawing Units that a human would recognize and can locally complete.
2. Give each unit type, root/support point, direction, grammar, priority and layer.
3. Assign visual token IDs to semantic units. Token membership is the executable bridge to geometry.
4. If a token genuinely mixes two semantic subjects, do NOT guess. Leave it unassigned; it will be surfaced for local review.
5. Do not output or use bounding boxes for ownership. bbox_hint may remain null.
6. Botanical/tree units usually grow root/trunk -> main structure -> branches -> leaves/flowers -> local accent.
7. Mountains use major contour then ridges. Rivers use far-to-near flow. Floating ornaments are late.
8. The program seeks a plausible, repeatable drawing process, not historical reconstruction.
9. Return the supplied schema exactly. unit_map_path should be null in API mode; ownership is through token_ids.
"""

USER_PROMPT = """Analyze the image and its visual-token atlas tiles. Build the Drawing Unit plan and assign token IDs to units.
Token IDs are visible as C#### labels. Prefer leaving a truly ambiguous crossing token unassigned over silently placing it
in the nearest region. The compiler has no bbox fallback.
"""


def _data_url(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def create_scene_plan(
    grid_image: Path,
    atlas_images: list[Path],
    model: str | None = None,
) -> ScenePlan:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for --ai mode")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Install the project dependencies first: pip install -e .") from exc
    client = OpenAI()
    selected_model = model or os.environ.get("APAINTING_MODEL", "gpt-5.6")
    content: list[dict[str, str]] = [
        {"type": "input_text", "text": USER_PROMPT},
        {"type": "input_image", "image_url": _data_url(grid_image), "detail": "high"},
    ]
    for atlas in atlas_images:
        content.append({"type": "input_image", "image_url": _data_url(atlas), "detail": "high"})
    response = client.responses.parse(
        model=selected_model,
        store=False,
        reasoning={"effort": "high"},
        input=[
            {"role": "developer", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        text_format=ScenePlan,
    )
    if response.output_parsed is None:
        raise RuntimeError(f"model did not return a scene plan: {response.output_text}")
    return response.output_parsed

STRUCTURE_SYSTEM_PROMPT = """You are the second-pass structural vision module for APainting.
The macro Drawing Units have already been identified and grounded to real geometry. Do NOT redefine unit ownership.
Do NOT use bounding boxes to move paths between units.

You now infer a coarse drawing hierarchy *inside each existing unit*.
Return normalized-1000 polyline guides that the deterministic geometry compiler can snap real paths to.

For botanical/branch units, identify dominant trunk/stem, primary branches, secondary branches and terminal flower/leaf groups.
For tree clusters, identify each main trunk and the major branch flow around that trunk.
For mountains, identify major silhouette/ridge contours before small internal cracks.
For rivers, identify far-to-near flow/support guides.
For stones, identify local contour groups from far to near.

Each guide has:
- role: backbone / primary_structure / secondary_structure / terminal / detail
- points: a small coarse polyline, not pixel-perfect
- focus_group: paths near guides with the same focus_group are locally completed together
- order: order among focus groups inside the unit
- progress_start/end: semantic progress along the guide
- influence_radius: usually 35-120 normalized units depending on visual spread

The guides are semantic hints, not exact segmentation. The compiler will map them to already-owned real paths.
Prefer a few strong structural guides over many tiny ones. Return only units that benefit from structural guidance.
"""

STRUCTURE_USER_PROMPT = """Using the trusted macro ScenePlan below and the image, infer the intra-unit drawing hierarchy.
Do not change which pixels/paths belong to a macro unit. Produce coarse structure guides suitable for a natural drawing replay.
ScenePlan:\n{scene_json}\n"""


def create_structure_plan(
    source_image: Path,
    scene_plan: ScenePlan,
    support_images: list[Path] | None = None,
    model: str | None = None,
):
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for --ai mode")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Install the project dependencies first: pip install -e .") from exc
    from .schemas import StructurePlan

    client = OpenAI()
    selected_model = model or os.environ.get("APAINTING_MODEL", "gpt-5.6")
    prompt = STRUCTURE_USER_PROMPT.format(scene_json=scene_plan.model_dump_json(indent=2))
    content: list[dict[str, str]] = [
        {"type": "input_text", "text": prompt},
        {"type": "input_image", "image_url": _data_url(source_image), "detail": "high"},
    ]
    for image in support_images or []:
        if image.exists():
            content.append({"type": "input_image", "image_url": _data_url(image), "detail": "high"})
    response = client.responses.parse(
        model=selected_model,
        store=False,
        reasoning={"effort": "high"},
        input=[
            {"role": "developer", "content": STRUCTURE_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        text_format=StructurePlan,
    )
    if response.output_parsed is None:
        raise RuntimeError(f"model did not return a structure plan: {response.output_text}")
    return response.output_parsed
