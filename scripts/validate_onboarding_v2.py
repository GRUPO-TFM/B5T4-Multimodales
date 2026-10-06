"""Audita entregas existentes sin generar contenido ni llamar a proveedores.

Uso: uv run python scripts/validate_onboarding_v2.py CARPETA [CARPETA ...]
Guarda el resumen en out/validacion_onboarding_v2.json, fuera de Git.
"""
import argparse
import json
from pathlib import Path

from b5t4.agents.onboarding.v2_pipeline import input_signature, validate_resume
from b5t4.agents.onboarding.v2_content import PersonalizedMaterial, cited_passage
from b5t4.agents.onboarding.material import collect_material
from b5t4.agents.onboarding.v2_schemas import OnboardingBrief, FactBank, ReferenceGuide, DirectedStoryboard
from b5t4.models.openrouter import write_json
from b5t4.render.video import inspect_video
from b5t4.config import get_settings


def audit(folder):
    folder = folder.resolve()
    read = lambda name: json.loads((folder / name).read_text(encoding="utf-8"))
    state, usage = read("ejecucion.json"), read("consumo_openrouter.json")
    brief = OnboardingBrief.model_validate(read("brief.json"))
    material = PersonalizedMaterial(**collect_material().__dict__)
    validate_resume(folder, input_signature(brief, material), material)
    assert state["status"] == "complete", state.get("error", state["stage"])
    bank = FactBank.model_validate(read("verificacion.json"))
    guide = ReferenceGuide.model_validate(read("referencia.json"))
    script = DirectedStoryboard.model_validate(read("guion.json"))
    assert all(f.probability >= get_settings().publish_threshold for f in bank.published().values())
    for chapter in guide.chapters:
        for text in [*chapter.paragraphs, *chapter.rows]:
            cited_passage(text.claim_ids, bank)
    for scene in script.scenes:
        cited_passage(scene.claim_ids, bank)
        for item in scene.items: cited_passage(item.claim_ids, bank)
        for edge in scene.edges: cited_passage(edge.claim_ids, bank)
    audio, layout = read("revision_audio.json"), read("validacion_diseno.json")
    assert audio["complete"] and min(audio["clarity"], audio["naturalness"]) >= 4 and not audio["issues"]
    assert layout["deterministic"] and not layout["bounds"]
    assert usage["accounted_usd"] <= brief.budget_usd
    decoded = inspect_video(folder / "video.mp4")
    assert brief.duration_seconds * .9 <= decoded["duration"] <= brief.duration_seconds
    assert (decoded["width"], decoded["height"]) == (get_settings().width, get_settings().height)
    return {"folder": str(folder), "profile": brief.role, "target_seconds": brief.duration_seconds,
        "video": decoded, "openrouter_usd": usage["accounted_usd"], "uncertain_requests": usage["uncertain_requests"],
        "jev": read("consumo_jev.json"), "published_facts": len(bank.published()),
        "minimum_fact_support": min(f.probability for f in bank.published().values()),
        "chapters": [chapter.id for chapter in guide.chapters],
        "reference_words": sum(len(p.text.split()) for chapter in guide.chapters for p in chapter.paragraphs),
        "scenes": len(script.scenes), "scene_kinds": sorted({scene.kind for scene in script.scenes}),
        "narration_words": sum(len(scene.narration.split()) for scene in script.scenes),
        "documents_read": len(material.reads), "audio_naturalness": audio["naturalness"],
        "sources_unchanged": True, "decoded_complete": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folders", nargs="+", type=Path)
    args = parser.parse_args()
    metrics = [audit(folder) for folder in args.folders]
    if len(metrics) == 2:
        common = {"team", "organisation", "rules", "resources"}
        assert all(common <= set(metric["chapters"]) for metric in metrics)
        assert set(metrics[0]["chapters"]) - common != set(metrics[1]["chapters"]) - common
    write_json(get_settings().out_dir / "validacion_onboarding_v2.json", metrics)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
