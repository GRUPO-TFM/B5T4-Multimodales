"""Onboarding v2: etapas persistentes, presupuesto y controles editoriales/audiovisuales."""
from __future__ import annotations
import datetime as dt
import hashlib
import inspect
import json
import math
import os
import shutil
from pathlib import Path
from uuid import uuid4

from ...config import get_settings
from ...models.openrouter import OpenRouter, write_json
from ...render import video, onboarding as renderer
from ...render.brand import signature as brand_signature, illustration_prompt
from .material import collect_material
from .schemas import SourceSelection
from .v2_schemas import (OnboardingBrief, ResearchPlan, ResearchDraft, FactChapter, FactBank, GuideChapter,
                         ReferenceGuide, Review, Direction, DirectedStoryboard)
from .v2_content import (PersonalizedMaterial, Checks, SYSTEM, plan_research, research_topic, verify_research,
                         validate_references, validate_plan, write_chapter, validate_guide, editorial_review, direct,
                         validate_modules, storyboard, validate_storyboard, revise_narration)
from .v2_media import common_storyboard, narrate, audit_audio, previews, visual_review, repair_visuals, fit_audio_tempo, cached_timeline


def _hash(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def input_signature(brief, material):
    s = get_settings()
    return {"schema_version": 2, "brief": brief.model_dump(exclude={"conversation_id"}),
            "contexts": dict(material.hashes), "manifest": hashlib.sha256(s.manifest_path.read_bytes()).hexdigest(),
            "models": [s.model_main, s.model_vision, s.model_image, s.model_tts, s.jev_model],
            "voice": s.voice_v2, "threshold": s.publish_threshold, "brand": brand_signature(),
            "video": [s.width, s.height, s.fps]}


def recipe_signature():
    files = list(Path(__file__).parent.glob("v2_*.py")) + [Path(__file__).parents[2] / "models" / "openrouter.py"]
    files += list(get_settings().templates_dir.glob("*v2*"))
    return _hash({file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in files})


class ExecutionLease:
    """El bloqueo del sistema operativo se libera también si termina el proceso."""
    def __init__(self,out):
        self.file = (out / ".execution.lock").open("a+b")
        if self.file.seek(0,2)==0: self.file.write(b"0"); self.file.flush()
        self.file.seek(0)
        try:
            if os.name=="nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError("Esta carpeta ya tiene una ejecución en curso; espera a que termine antes de reanudar") from None

    def close(self):
        self.file.close()


class StageArtifacts:
    """Contratos ligados a sus dependencias; el adaptador HTTP no invalida hechos.

    Las primeras ejecuciones usaban una huella global. Su migración se limita a
    investigación con referencias revalidadas; conserva la procedencia original.
    """
    def __init__(self, out, previous_recipe, current_recipe, lock=False):
        self.lease = ExecutionLease(out) if lock else None
        self.out, self.previous_recipe, self.current_recipe = out, previous_recipe, current_recipe
        self.path = out / "etapas.json"
        self.metadata = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def close(self):
        if self.lease: self.lease.close()

    def get(self, name, schema, create, validate=None, dependencies=None):
        functions = (plan_research, validate_plan) if name == "indice.json" else (
            (research_topic,) if name.startswith(("investigacion_", "ampliado_")) else
            (verify_research, validate_references) if name.startswith("verificado_") else
            (write_chapter, validate_guide) if name.startswith("referencia_") else
            (editorial_review,) if name.startswith("revision_editorial_") else
            (direct, validate_modules) if name == "direccion.json" else
            (storyboard, validate_storyboard) if name == "guion.json" else ())
        recipe_parts = {function.__name__: inspect.getsource(function) for function in functions}
        recipe_parts["system"] = SYSTEM
        content_files = []
        if name.startswith(("revision_visual", "revision_ilustracion")):
            content_files += [Path(__file__).with_name("v2_media.py"), *get_settings().templates_dir.glob("*v2*")]
        recipe_parts.update({file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in content_files})
        recipe = _hash(recipe_parts)
        stamp = _hash([recipe, schema.model_json_schema(), dependencies])
        record = self.metadata.get(name)
        early = name.startswith(("indice", "investigacion_", "ampliacion_", "ampliado_", "verificado_", "referencia_")) or name in ("direccion.json", "guion.json")
        legacy = (early and ((isinstance(record, str) and self.previous_recipe and
                  record == _hash([self.previous_recipe, dependencies])) or
                  (isinstance(record, dict) and validate and ("dependency_hash" not in record or
                   record["dependency_hash"] == _hash(dependencies)))))
        path = self.out / name
        reusable = isinstance(record, dict) and record.get("stamp") == stamp
        if path.exists() and (reusable or legacy):
            try:
                result = schema.model_validate_json(path.read_text(encoding="utf-8"))
                if validate: validate(result)
            except ValueError:
                # Cambios en hechos publicados pueden invalidar un capítulo antiguo.
                # Se reconstruye el contrato afectado, no se entrega ni se borra el expediente.
                result = create()
                reusable = legacy = False
        else:
            result = create()
        if validate: validate(result)
        write_json(path, result)
        self.metadata[name] = {"stamp": stamp, "dependency_hash": _hash(dependencies), "recipe_hash": self.current_recipe,
                               "origin_recipe_hash": record.get("origin_recipe_hash", record.get("recipe_hash"))
                                   if isinstance(record, dict) and (reusable or legacy) else self.previous_recipe if legacy else self.current_recipe}
        write_json(self.path, self.metadata)
        return result


def validate_resume(out, signature, material):
    state = json.loads((out / "ejecucion.json").read_text(encoding="utf-8"))
    if state["inputs"] != signature:
        raise ValueError("Han cambiado el encargo, los contextos, el manifiesto, los modelos o la marca; inicia una ejecución nueva")
    sources = json.loads((out / "fuentes.json").read_text(encoding="utf-8"))
    for rel, digest in sources["sha256"].items():
        path = (material.settings.data_dir / rel).resolve()
        path.relative_to(material.settings.data_dir.resolve())
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Ha cambiado la fuente {rel}; inicia una ejecución nueva")
    for rel in sources["documents_read"]:
        material.read_document(rel)
    return state


def validate_selection(value, catalog):
    if set(value.document_paths) - {record["path"] for record in catalog}:
        raise ValueError("Usa rutas exactas del catálogo")


def run(brief: OnboardingBrief | dict, out_root=None, log=print, *, resume=None, report_only=False):
    brief = brief if isinstance(brief, OnboardingBrief) else OnboardingBrief.model_validate(brief)
    s = get_settings()
    if not s.has_llm or not s.has_verifier:
        raise RuntimeError("Onboarding v2 requiere OPENROUTER_API_KEY y JEV_API_KEY")
    if not report_only:
        from playwright.sync_api import sync_playwright
        if not (shutil.which(video._ffmpeg()) or Path(video._ffmpeg()).is_file()):
            raise FileNotFoundError("No se encuentra ffmpeg")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(); browser.close()
    material = PersonalizedMaterial(**collect_material().__dict__)
    inputs = input_signature(brief, material)
    if resume:
        out = Path(resume).resolve()
        previous = validate_resume(out, inputs, material)
    else:
        out = Path(out_root or s.out_dir / "onboarding") / (dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-v2-" + uuid4().hex[:4])
        out.mkdir(parents=True, exist_ok=False); previous = {}
        if brief.conversation_id:
            draft = s.out_dir / "onboarding" / "drafts" / brief.conversation_id
            for name in ("consumo_openrouter.json", "conversacion.json"):
                if (draft / name).is_file(): shutil.copy2(draft / name, out / name)
    log(f"Salida: {out}")
    state = {"inputs": inputs, "started_at": previous.get("started_at", dt.datetime.now().isoformat()),
             "status": "running", "stage": "Preparación", "recipe_hash": recipe_signature()}
    artifacts = StageArtifacts(out, previous.get("recipe_hash"), state["recipe_hash"], lock=True)
    write_json(out / "brief.json", brief)
    client = OpenRouter(out, brief.budget_usd, log)
    checks = Checks(out, s.out_dir / "onboarding" / "cache" / "comprobaciones.json", log)

    def stage(name):
        checks.save()
        state.update(stage=name, updated_at=dt.datetime.now().isoformat(), openrouter_usd=round(client.ledger.spent, 6))
        write_json(out / "ejecucion.json", state); log(name)

    def cached(name, schema, create, validate=None, dependencies=None):
        return artifacts.get(name, schema, create, validate, dependencies)

    try:
        client.ledger.reconcile(client.generation_cost)
        stage("1 · Encargo y contextos completos")
        material.save(out)
        stage("2 · Plan personalizado y selección de fuentes")
        plan = cached("indice.json", ResearchPlan, lambda: plan_research(brief, material, client),
                      lambda p: validate_plan(p, material), dependencies=brief.model_dump())
        chapters = []
        for topic in plan.chapters:
            stage("3 · Investigación y verificación: " + topic.title)
            evidence = material.for_block(topic)
            draft = cached("investigacion_" + topic.id + ".json", ResearchDraft,
                lambda: research_topic(topic, brief, evidence, client, checks),
                lambda d: validate_references(d.facts, evidence), dependencies=[topic.model_dump(), brief.model_dump()])
            if draft.gaps:
                catalog = material.catalog()
                def selection():
                    def valid(value):
                        if set(value.document_paths) - {record["path"] for record in catalog}:
                            raise ValueError("Usa rutas exactas del catálogo")
                    return client.json(SourceSelection, SYSTEM,
                        "Selecciona hasta tres documentos vigentes para resolver estas lagunas; lista vacía si "
                        "no hay candidatos útiles. No repitas documentos seleccionados.\n"
                        + json.dumps({"gaps": draft.gaps, "read": topic.document_paths, "catalog": catalog}, ensure_ascii=False),
                        validate=valid, stage="ampliación " + topic.id, max_output=1500)
                extra = cached("ampliacion_" + topic.id + ".json", SourceSelection, selection,
                               lambda value: validate_selection(value, catalog),
                               dependencies=[topic.model_dump(), draft.model_dump()])
                more = [record for path in extra.document_paths for record in material.read_document(path)]
                if more:
                    evidence = list({e.id: e for e in evidence + more}.values())
                    draft = cached("ampliado_" + topic.id + ".json", ResearchDraft,
                        lambda: research_topic(topic, brief, evidence, client, checks),
                        lambda d: validate_references(d.facts, evidence), dependencies=[draft.model_dump(), extra.model_dump()])
            material.save(out)
            verified = cached("verificado_" + topic.id + ".json", FactChapter,
                lambda: verify_research(topic, draft, evidence, client, checks),
                lambda value: validate_references(value.facts, evidence), dependencies=draft.model_dump())
            # Las decisiones se recalculan incluso en caché; referencias y umbral siguen siendo obligatorios.
            lookup = {record.id: record for record in evidence}
            validate_references(verified.facts, evidence)
            for fact in verified.facts:
                passage = "\n\n".join(f"[{sid}] {lookup[sid].heading}\n{lookup[sid].text}" for sid in fact.source_ids)
                fact.probability = checks.check(fact.text, passage)
                fact.status = "publicar" if fact.probability >= s.publish_threshold else "revisar" if fact.probability >= s.discard_threshold else "descartar"
            write_json(out / ("verificado_" + topic.id + ".json"), verified)
            chapters.append(verified)
        bank = FactBank(title=plan.title, chapters=chapters)
        write_json(out / "verificacion.json", bank)
        weak = [chapter.id for chapter in chapters if sum(f.status == "publicar" for f in chapter.facts) < 3]
        if weak:
            raise ValueError("Falta cobertura verificada para el informe: " + ", ".join(weak))
        stage("4 · Documento completo de referencia")
        guide_chapters = [cached("referencia_" + chapter.id + ".json", GuideChapter,
                         lambda chapter=chapter: write_chapter(chapter, brief, bank, client, checks),
                         lambda value: validate_guide(value, bank, checks), dependencies=[chapter.model_dump(), brief.model_dump()])
                          for chapter in chapters]
        guide = ReferenceGuide(title=bank.title, chapters=guide_chapters)
        for attempt in range(3):
            renderer.write_reference(guide, bank, brief, material, out)
            stage("5 · Revisión editorial independiente")
            review = cached(f"revision_editorial_{attempt}.json", Review,
                            lambda: editorial_review(guide, brief, client), dependencies=guide.model_dump())
            if review.passes(): break
            if attempt == 2: raise ValueError("El documento requiere revisión editorial: " + "; ".join(review.issues))
            affected = set(review.affected_ids) or {chapter.id for chapter in guide.chapters}
            for index, chapter in enumerate(guide.chapters):
                if chapter.id in affected:
                    source = next(c for c in bank.chapters if c.id == chapter.id)
                    updated = write_chapter(source, brief, bank, client, checks, "\n".join(review.issues))
                    guide.chapters[index] = updated
                    write_json(out / ("referencia_" + chapter.id + ".json"), updated)
        write_json(out / "referencia.json", guide)
        if report_only:
            state.update(status="report_ready", stage="Documento de referencia completo", openrouter_usd=client.ledger.spent)
            write_json(out / "ejecucion.json", state); return out
        stage("6 · Dirección narrativa e infografía")
        direction = cached("direccion.json", Direction, lambda: direct(brief, guide, bank, client, checks),
                           lambda d: validate_modules(d.modules, bank, checks), dependencies=[guide.model_dump(), brief.model_dump()])
        images = {}
        renderer.write_reference(guide, bank, brief, material, out, direction, images)
        for attempt in range(3):
            renderer.write_infographic(direction, bank, brief, material, out)
            review = cached(f"revision_infografia_{attempt}.json", Review,
                lambda: client.vision(Review, SYSTEM,
                    "Revisa esta infografía interna a su tamaño de lectura original de 1600 px de ancho. "
                    "Evalúa legibilidad, jerarquía, claridad y síntesis. Nota 4 es apto. issues solo fallos "
                    "que impiden entregar: texto cortado, nodos solapados, falta de contraste o elementos "
                    "que pierden sentido. No penalices que sea una pieza vertical larga ni añadas preferencias "
                    "de estilo. Debe conservar la identidad Andbank y servir de mapa del informe de referencia.",
                    [out / "infografia.png"], stage="revisión de infografía", max_output=2200),
                dependencies=hashlib.sha256((out / "infografia.png").read_bytes()).hexdigest())
            if review.passes(): break
            if attempt == 2: raise ValueError("La infografía requiere corrección: " + "; ".join(review.issues))
            def repair_direction():
                def valid(value):
                    if value.illustrations != direction.illustrations or value.narrative_arc != direction.narrative_arc:
                        raise ValueError("Conserva las ilustraciones y el arco narrativo")
                    validate_modules(value.modules, bank, checks)
                return client.json(Direction, SYSTEM,
                    "Corrige únicamente composición, títulos, etiquetas y detalles de los módulos de esta "
                    "infografía según los problemas. Conserva illustrations y narrative_arc exactamente. "
                    "No inventes hechos ni relaciones; puedes simplificar nodos.\nPROBLEMAS:\n"
                    + json.dumps(review.issues, ensure_ascii=False) + "\nDIRECCIÓN:\n" + direction.model_dump_json()
                    + "\nHECHOS:\n" + json.dumps({key: fact.text for key, fact in bank.published().items()}, ensure_ascii=False),
                    validate=valid, stage="reparación de infografía", max_output=6500)
            direction = repair_direction()
            write_json(out / "direccion.json", direction)
        renderer.write_reference(guide, bank, brief, material, out, direction, images)
        write_json(out / "infografia.json", direction)
        stage("7 · Guion, storyboard y respaldo documental")
        target_words = round((brief.duration_seconds * .95 - 6) * 2.35)
        plan_video = cached("guion.json", DirectedStoryboard,
            lambda: storyboard(brief, bank, direction, client, checks, target_words),
            lambda p: validate_storyboard(p, bank, direction, checks), dependencies=[direction.model_dump(), bank.model_dump(), brief.model_dump()])
        stage("8 · Ilustraciones, voz expresiva y duración real")
        needed_images = {scene.image_id for scene in plan_video.scenes if scene.image_id}
        for illustration in direction.illustrations:
            if illustration.id not in needed_images: continue
            image_key = _hash([illustration.model_dump(), s.model_image, inputs["brand"]])[:12]
            target = out / "ilustraciones" / (illustration.id + "-" + image_key + ".png")
            for attempt in range(3):
                if not target.exists(): client.image(illustration_prompt(illustration.subject), target, stage="ilustración " + illustration.id)
                review = cached(f"revision_ilustracion_{illustration.id}_{attempt}.json", Review,
                    lambda: client.vision(Review, SYSTEM,
                        "Evalúa esta ilustración conceptual corporativa. Debe ser limpia, blanca, con trazos "
                        "negros/grises y acentos rojos discretos, sin texto, logos ni retratos identificables. "
                        "Nota 4 es apta. issues solo errores que impiden entregarla.\nPropósito: " + illustration.purpose,
                        [target], stage="revisión de ilustración", max_output=1800),
                    dependencies=hashlib.sha256(target.read_bytes()).hexdigest())
                if review.passes(): break
                if attempt == 2: raise ValueError("La ilustración requiere corrección: " + "; ".join(review.issues))
                client.image(illustration_prompt(illustration.subject) + " Correct these issues: " + "; ".join(review.issues), target)
            images[illustration.id] = target
        renderer.write_reference(guide, bank, brief, material, out, direction, images)
        saved_audio = cached_timeline(plan_video,out) if resume else None
        words = sum(len(scene.narration.split()) for scene in plan_video.scenes)
        pre_adjusted = not saved_audio and (words > target_words * 1.08 or words < target_words * .85)
        if pre_adjusted:
            plan_video = revise_narration(plan_video, bank, brief, client, checks, target_words)
            write_json(out / "guion.json", plan_video)
        rounds = 3-int(pre_adjusted)
        for attempt in range(rounds):
            timeline = saved_audio if attempt==0 and saved_audio else narrate(plan_video, brief, client, out, log)
            frame_duration = math.ceil(timeline["total"] * s.fps) / s.fps
            if brief.duration_seconds * .9 <= frame_duration <= brief.duration_seconds - .1: break
            if saved_audio and attempt==0:
                try:
                    timeline = fit_audio_tempo(timeline,out,brief.duration_seconds,log); break
                except ValueError: pass
            if attempt == rounds-1:
                timeline = fit_audio_tempo(timeline, out, brief.duration_seconds, log)
                break
            count = sum(len(scene.narration.split()) for scene in plan_video.scenes)
            target_words = round(count * (brief.duration_seconds * .955 - len(plan_video.scenes)*.6) /
                                 max(1, timeline["total"]-len(plan_video.scenes)*.6))
            plan_video = revise_narration(plan_video, bank, brief, client, checks, target_words)
            write_json(out / "guion.json", plan_video)
        stage("9 · Revisión del audio y las composiciones")
        for attempt in range(3):
            try:
                audit_audio(plan_video, client, out, checks); break
            except ValueError as error:
                if attempt == 2: raise
                log("  Revisión del audio: " + str(error)[:240])
                timeline = narrate(plan_video, brief, client, out, log, voice_feedback=str(error))
                if not brief.duration_seconds*.9 <= timeline["total"] <= brief.duration_seconds-.1:
                    try:
                        timeline = fit_audio_tempo(timeline,out,brief.duration_seconds,log)
                        continue
                    except ValueError: pass
                    count = sum(len(scene.narration.split()) for scene in plan_video.scenes)
                    target_words = round(count * (brief.duration_seconds * .95) / timeline["total"])
                    plan_video = revise_narration(plan_video, bank, brief, client, checks, target_words)
                    write_json(out / "guion.json", plan_video)
                    timeline = narrate(plan_video, brief, client, out, log)
        _, source_map = renderer.source_index(bank, material)
        for attempt in range(3):
            common = common_storyboard(plan_video, brief, bank, source_map, images)
            write_json(out / "storyboard.json", common)
            samples, bounds = previews(common, timeline, out)
            review = cached(f"revision_visual_{attempt}.json", Review,
                lambda: visual_review(common, samples, client, brief), dependencies=plan_video.model_dump())
            if not bounds and review.passes(): break
            if attempt == 2: raise ValueError("Las composiciones requieren corrección: " + json.dumps(bounds) + "; ".join(review.issues))
            plan_video = repair_visuals(plan_video, direction, bank, brief, client, checks, [*bounds, *review.issues])
            write_json(out / "guion.json", plan_video)
        if not brief.duration_seconds*.9 <= math.ceil(timeline["total"]*s.fps)/s.fps <= brief.duration_seconds-.1:
            raise ValueError("La duración final no cumple el encargo")
        stage("10 · Montaje y validación del MP4 completo")
        video.render(common, timeline, out, log=log)
        validation = video.inspect_video(out / "video.mp4")
        if validation["duration"] > brief.duration_seconds or (validation["width"], validation["height"]) != (s.width,s.height):
            raise ValueError("El MP4 no cumple duración o dimensiones")
        write_json(out / "validacion_video.json", validation)
        client.ledger.reconcile(client.generation_cost)
        state.update(status="complete", stage="Onboarding personalizado completo", video=validation,
                     finished_at=dt.datetime.now().isoformat(), openrouter_usd=round(client.ledger.spent,6),
                     published_claims=len(bank.published()), documents_read=len(material.reads),
                     profile=brief.role, duration_target=brief.duration_seconds)
        write_json(out / "ejecucion.json", state); material.save(out); checks.save()
        log(f"Completado: {out}"); return out
    except Exception as error:
        state.update(status="failed", error=f"{type(error).__name__}: {str(error)[:700]}", openrouter_usd=round(client.ledger.spent,6))
        write_json(out / "ejecucion.json", state); material.save(out); checks.save()
        log(f'Se puede reanudar con: b5t4 onboarding --resume "{out}"')
        raise
    finally:
        artifacts.close()
