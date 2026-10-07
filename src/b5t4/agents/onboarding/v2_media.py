"""Voz expresiva, capturas reproducibles y auditoría audiovisual antes del montaje."""
from __future__ import annotations
import hashlib
import json
import re
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf

from ...config import get_settings
from ...models import tts
from ...models.openrouter import write_json
from ...render import video
from ...render.onboarding import image_url, referenced
from ...render.schemas import Scene, Storyboard
from .v2_schemas import AudioReview, Review, DirectedStoryboard
from .v2_content import SYSTEM, cited_passage, repair_items, validate_storyboard

VOICE_STYLE = ("Spanish from Spain. Warm, clear, sober and professional, like a helpful colleague "
               "welcoming a new team member. Natural conversational phrasing and pauses, measured pace, "
               "gentle emphasis on key ideas, no advertising enthusiasm, no monotone reading. "
               "Pronounce names carefully and finish every sentence.")


def common_storyboard(plan, brief, bank, source_map, images):
    scenes = []
    for scene in plan.scenes:
        data = scene.model_dump(exclude={"id", "kind", "narration"})
        refs = referenced(scene.claim_ids, bank, source_map)
        data.update(layout="onboarding_v2", kicker=brief.role[:95],
                    source="Informe de referencia · " + " ".join(f"[{number}]" for number in refs),
                    image_url=image_url(images[scene.image_id]) if scene.image_id else "")
        scenes.append(Scene(id=scene.id, kind=scene.kind, narration=scene.narration, data=data))
    return Storyboard(topic=bank.title, voice=get_settings().voice_v2, scenes=scenes)


def narrate(plan, brief, client, out, log=print, voice_feedback="", only=None):
    audio_dir = out / "audio"; audio_dir.mkdir(exist_ok=True)
    parts, scenes, total = [], [], 0.0
    style = VOICE_STYLE + (" Delivery correction: " + voice_feedback if voice_feedback else "")
    settings = get_settings()
    # Una corrección puntual (only) conserva los clips ya escuchados del resto de escenas.
    kept = {}
    if only is not None and (out / "timeline.json").is_file():
        kept = {entry["id"]: out / entry["audio"] for entry in
                json.loads((out / "timeline.json").read_text(encoding="utf-8"))["scenes"] if entry["id"] not in only}
    for scene in plan.scenes:
        spoken = tts.verbalize(scene.narration)
        key = hashlib.sha256(json.dumps([settings.model_tts, settings.voice_v2, style, spoken]).encode()).hexdigest()[:20]
        path = audio_dir / (key + ".wav")
        previous = kept.get(scene.id)
        if previous and previous.is_file() and previous.with_suffix(".json").is_file() and \
                json.loads(previous.with_suffix(".json").read_text(encoding="utf-8"))["text"] == spoken:
            path = previous
        if path.exists():
            samples, rate = sf.read(path, dtype="float32")
        else:
            blob, rate = client.speech(spoken, style, seconds=max(10, len(spoken.split()) / 1.8), stage="voz " + scene.id)
            samples = np.frombuffer(blob, dtype="<i2").astype(np.float32) / 32768
            sf.write(path, samples, rate, subtype="FLOAT")
            write_json(path.with_suffix(".json"), {"model": settings.model_tts, "voice": settings.voice_v2,
                       "style": style, "text": spoken, "sample_rate": rate,
                       "request": client.ledger.entries[-1].get("generation_id", "")})
        if rate != 24000 or samples.ndim != 1 or not len(samples) or not np.isfinite(samples).all():
            raise ValueError("La voz debe ser mono, finita, no vacía y a 24 kHz")
        voice_seconds = len(samples) / rate
        part = np.concatenate([np.zeros(round(.25 * rate), np.float32), samples, np.zeros(round(.35 * rate), np.float32)])
        duration = len(part) / rate
        scenes.append({"id": scene.id, "kind": scene.kind, "start": round(total, 6), "duration": round(duration, 6),
                       "voice_seconds": round(voice_seconds, 3), "audio": path.relative_to(out).as_posix()})
        total += duration; parts.append(part)
        log(f"  voz {scene.id}: {voice_seconds:.1f}s · acumulado {total:.1f}s")
    sf.write(out / "voz.wav", np.concatenate(parts), 24000)
    timeline = {"total": total, "scenes": scenes, "voice_sha256": hashlib.sha256((out / "voz.wav").read_bytes()).hexdigest()}
    write_json(out / "timeline.json", timeline)
    return timeline


def cached_timeline(plan, out):
    """Reanuda una pista revisada solo si clips, texto, modelo y WAV coinciden."""
    if not (out / "timeline.json").is_file() or not (out / "voz.wav").is_file(): return None
    timeline = json.loads((out / "timeline.json").read_text(encoding="utf-8"))
    if [entry["id"] for entry in timeline["scenes"]] != [scene.id for scene in plan.scenes]: return None
    s = get_settings(); parts = []
    for scene, entry in zip(plan.scenes, timeline["scenes"]):
        path = (out / entry["audio"]).resolve(); path.relative_to(out.resolve())
        if not path.is_file() or not path.with_suffix(".json").is_file(): return None
        metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        spoken = tts.verbalize(scene.narration)
        if metadata["text"] != spoken or metadata["model"] != s.model_tts or metadata["voice"] != s.voice_v2: return None
        key = hashlib.sha256(json.dumps([s.model_tts,s.voice_v2,metadata["style"],spoken]).encode()).hexdigest()[:20]
        if path.stem != key: return None
        samples,rate = sf.read(path,dtype="float32")
        if rate!=24000 or samples.ndim!=1: return None
        parts.append(np.concatenate([np.zeros(6000,np.float32),samples,np.zeros(8400,np.float32)]))
    digest = hashlib.sha256((out / "voz.wav").read_bytes()).hexdigest()
    if timeline.get("voice_sha256"):
        if timeline["voice_sha256"] != digest: return None
    elif not timeline.get("tempo_factor"):
        actual,rate = sf.read(out / "voz.wav",dtype="float32")
        expected = np.concatenate(parts)
        if rate!=24000 or actual.shape!=expected.shape or not np.allclose(actual,expected,atol=1/32768): return None
        timeline["voice_sha256"] = digest
        write_json(out / "timeline.json",timeline)
    else: return None
    if abs(sf.info(out / "voz.wav").duration-timeline["total"])>.001: return None
    return timeline


class AudioMismatch(ValueError):
    """Las escuchas aprueban el audio, pero alguna frase no casa con el guion: basta repetir esas escenas."""
    def __init__(self, sentences, scenes):
        super().__init__("La voz no coincide con el guion en " + ", ".join(scenes) + ": "
                         + "; ".join(f"«{text}» ({score:.2f})" for text, score in sentences))
        self.scenes = scenes


def _sound(word):
    """Clave fonética mínima del español: «Alfa» y «Alpha» suenan igual."""
    word = word.lower().translate(str.maketrans("áéíóúü", "aeiouu"))
    for written, sounded in (("ph", "f"), ("qu", "k"), ("ll", "y"), ("ch", "#"), ("h", ""), ("v", "b"), ("z", "s")):
        word = word.replace(written, sounded)
    word = re.sub(r"g(?=[ei])", "j", re.sub(r"c(?=[ei])", "s", word)).replace("c", "k").replace("#", "ch")
    return re.sub(r"([^r])\1", r"\1", word)


def align_spelling(heard, script):
    """Escribe lo oído con la grafía del guion cuando suena igual que una única palabra suya.

    Una transcripción ciega no puede saber si se dijo «Alfa» o «Alpha». Solo se tocan
    homófonos: otra persona, cifra o condición sigue llegando distinta al verificador.
    """
    word = r"[^\W\d_]+"
    known, by_sound = set(), {}
    for written in re.findall(word, script):
        known.add(written.lower())
        by_sound.setdefault(_sound(written), {}).setdefault(written.lower(), written)
    def spell(match):
        said = match.group(0)
        options = by_sound.get(_sound(said), {})
        if said.lower() in known or len(options) != 1:
            return said
        written = next(iter(options.values()))
        return written[0].upper() + written[1:] if said[0].isupper() else written
    return re.sub(word, spell, heard)


@lru_cache(maxsize=1)
def _number_words():
    from num2words import num2words
    return {num2words(number, lang="es"): str(number) for number in range(1000)}


def sound_key(text):
    """Cómo suena un texto: sin mayúsculas ni puntuación, homófonos unidos y decimales dígito a dígito.

    «v once» y «B once», o «tres coma veintitrés» y «tres coma dos tres», son la misma lectura en voz alta.
    Otra cifra, persona o condición produce una clave distinta y sigue llegando al verificador.
    """
    words, key, index = re.findall(r"[^\W_]+", text.lower()), [], 0
    while index < len(words):
        key.append(words[index] if words[index].isdigit() else _sound(words[index]))
        index += 1
        if words[index - 1] != "coma":
            continue
        digits = ""
        while index < len(words):
            span = next((size for size in range(5, 0, -1) if " ".join(words[index:index + size]) in _number_words()), 0)
            if not span: break
            digits += _number_words()[" ".join(words[index:index + span])]
            index += span
        if digits: key.append(digits)
    return " ".join(key)


def audit_audio(plan, client, out, checks):
    voice = out / "voz.wav"
    result = client.audio_review(AudioReview, SYSTEM,
        "Escucha este audio COMPLETO de onboarding. Transcribe literalmente lo que se oye. Evalúa "
        "claridad y naturalidad de 1 a 5 (4 es apto). complete indica que el audio termina normalmente "
        "sin palabras cortadas. issues solo incluye problemas que impiden entregar: audio vacío, "
        "distorsión, frases truncadas, pronunciación incomprensible, instrucciones recitadas o ritmo "
        "claramente robótico. No inventes palabras ni completes lo que no se oye. No penalices pausas "
        "cortas entre escenas. No tienes el guion para evitar inferir la transcripción.", voice,
        stage="revisión independiente del audio", max_output=6500)
    spoken = [(scene.id, tts.verbalize(scene.narration)) for scene in plan.scenes]
    intended = " ".join(text for _, text in spoken)
    write_json(out / "revision_audio.json", result)
    write_json(out / "revision_audio_independiente.json", result)
    if not result.complete or min(result.clarity, result.naturalness) < 4 or result.issues:
        raise ValueError("La revisión del audio requiere corrección: " + "; ".join(result.issues or ["claridad o naturalidad insuficiente"]))
    # El verificador trabaja con afirmaciones cortas y números verbalizados en
    # ambos sentidos: detecta añadidos y también frases omitidas por la voz.
    # Comillas y rayas no se pronuncian, y la grafía de lo oído se alinea con el guion.
    plain = lambda text: re.sub(r"[«»“”\"]|\s[-–—](?=\s)", "", text)
    script = plain(intended)
    split = lambda text: [part.strip() for part in re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡])", text) if len(part.strip())>15]
    def differences(transcript):
        heard = plain(align_spelling(tts.verbalize(transcript), script))
        # Lo que suena igual que el otro texto ya coincide; el verificador solo decide sobre lo demás.
        sounds = lambda text: f" {sound_key(text)} "
        pairs = [(part, other) for parts, other in ((split(heard), script), (split(script), heard))
                 for part in parts if sounds(part) not in sounds(other)]
        return [(part, score) for (part, _), score in zip(pairs, checks.many(pairs)) if score < get_settings().publish_threshold]
    mismatches = differences(result.transcript)
    if mismatches:
        # Una transcripción ciega puede escribir mal un nombre que se pronunció
        # correctamente. La segunda escucha compara sonido y guion expresamente;
        # conserva la primera y sigue exigiendo respaldo semántico de 0,80.
        compared = client.audio_review(AudioReview, SYSTEM,
            "Compara el audio COMPLETO con el guion esperado. Escucha especialmente estas diferencias "
            "detectadas en la transcripción ciega. Decide por lo que SE OYE, nunca completes el audio "
            "leyendo el guion. Transcribe lo pronunciado; puedes usar la ortografía oficial de un nombre "
            "solo si sus sonidos corresponden. Si realmente dice otra persona, empresa, cifra o condición, "
            "conserva esa diferencia en transcript y añádela a issues. Evalúa claridad, naturalidad y "
            "finalización.\nDIFERENCIAS:\n" + json.dumps([part for part, _ in mismatches],ensure_ascii=False)
            + "\nGUION ESPERADO:\n" + intended, voice,
            stage="comparación auditiva de nombres y cifras",max_output=6500)
        write_json(out / "revision_audio_comparativa.json", compared)
        if not compared.complete or min(compared.clarity,compared.naturalness)<4 or compared.issues:
            raise ValueError("El audio difiere del guion: " + "; ".join(compared.issues or ["audio incompleto"]))
        result = compared
        mismatches = differences(result.transcript)
        if mismatches:
            words = lambda text: set(re.findall(r"\w+", text.lower()))
            affected = {max(spoken, key=lambda entry: len(words(part) & words(entry[1])))[0] for part, _ in mismatches}
            raise AudioMismatch(mismatches, [scene_id for scene_id, _ in spoken if scene_id in affected])
    write_json(out / "revision_audio.json",result)
    return result


def fit_audio_tempo(timeline, out, maximum, log=print):
    """Corrige una variación residual de tempo sin cortar voz ni cambiar su tono.

    Se limita al 8%; el audio resultante pasa después la revisión independiente.
    Las desviaciones mayores requieren abreviar el guion y nunca se fuerzan.
    """
    target = maximum * (.97 if timeline["total"] > maximum else .93)
    factor = timeline["total"] / target
    if not .92 <= factor <= 1.08:
        raise ValueError(f"La duración medida ({timeline['total']:.1f}s) necesita un nuevo ajuste de guion")
    source = out / "voz.wav"
    temporary = out / "voz_ajustada.wav"
    subprocess.run([video._ffmpeg(), "-y", "-v", "error", "-i", str(source), "-af", f"atempo={factor:.9f}",
                    "-ar", "24000", "-ac", "1", str(temporary)], check=True)
    actual = sf.info(temporary).duration
    if not maximum*.9 <= actual <= maximum-.1:
        raise ValueError("El ajuste de tempo no cumple la duración del encargo")
    scale = actual / timeline["total"]
    result = {"total": actual, "tempo_factor": factor, "source_total": timeline["total"],
              "scenes": [{**scene, "start": scene["start"]*scale, "duration": scene["duration"]*scale,
                          "source_voice_seconds": scene["voice_seconds"], "voice_seconds": scene["voice_seconds"]*scale}
                         for scene in timeline["scenes"]]}
    temporary.replace(source)
    result["voice_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    write_json(out / "timeline.json", result)
    log(f"  Ajuste residual de tempo {factor:.3f}: {actual:.1f}s; voz completa y tono conservado")
    return result


def previews(sb, timeline, out):
    from playwright.sync_api import sync_playwright
    html = video.scene_html(sb, timeline)
    (out / "escenas.html").write_text(html, encoding="utf-8")
    images, bounds = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": get_settings().width, "height": get_settings().height})
            errors = []; page.on("pageerror", lambda error: errors.append(str(error)))
            page.set_content(html, wait_until="load"); page.evaluate("document.fonts.ready")
            boundary_times = []
            for scene in timeline["scenes"]:
                for fraction in (.1, .5, .9):
                    t = scene["start"] + scene["duration"] * fraction
                    page.evaluate("t=>render(t)", t)
                    failures = page.evaluate("""id=>[...document.getElementById(id).querySelectorAll('.v2-title,.v2-card,.v2-node')]
                        .filter(node=>{const r=node.getBoundingClientRect();return r.right>innerWidth-35||r.left<35||
                        r.bottom>innerHeight-90||node.scrollWidth>node.clientWidth+2||node.scrollHeight>node.clientHeight+2})
                        .map(node=>node.textContent.trim().slice(0,120))""", scene["id"])
                    if failures: bounds.append({"scene": scene["id"], "fraction": fraction, "elements": failures})
                t = scene["start"] + scene["duration"] * .7
                page.evaluate("t=>render(t)", t)
                target = out / ("escena_" + scene["id"] + ".png")
                first = page.screenshot(path=str(target)); images.append(target)
                page.evaluate("t=>render(t)", max(0, scene["start"] - .2))
                page.evaluate("t=>render(t)", t)
                if first != page.screenshot():
                    raise ValueError(f"La escena {scene['id']} no se reproduce igual al retroceder y avanzar")
                for sample in (scene["start"],scene["start"]+.04,scene["start"]+.8,
                               scene["start"]+scene["duration"]-.04):
                    sample=min(timeline["total"]-.001,max(0,sample))
                    page.evaluate("t=>render(t)",sample); before=page.screenshot()
                    page.evaluate("t=>render(t)",0 if sample>0 else timeline["total"]-.001)
                    page.evaluate("t=>render(t)",sample)
                    if before!=page.screenshot(): raise ValueError("La transición no es reproducible en " + str(sample))
                    boundary_times.append(round(sample,3))
            if errors:
                raise ValueError("Error de JavaScript del render: " + "; ".join(errors))
        finally:
            browser.close()
    write_json(out / "validacion_diseno.json", {"deterministic": True, "sampled_scenes": len(images), "bounds": bounds,
                                               "transition_samples":boundary_times})
    return images, bounds


def visual_review(sb, images, client, brief):
    return client.vision(Review, SYSTEM,
        "Revisa estas capturas de un vídeo corporativo Andbank. La marca debe usar blanco predominante, "
        "negro, gris cálido y rojo; logo a la derecha, mucha claridad y espacio. Evalúa legibilidad, "
        "relevancia del lenguaje para el perfil, coherencia y variedad de composición. Nota 4 es apto. "
        "issues SOLO incluye fallos que impiden entregar: cortes, solapamientos, texto ilegible o "
        "incoherencia clara. No sugieras preferencias opcionales. affected_ids usa los ids exactos "
        "de las escenas. Las ilustraciones son conceptuales, no fotografías de personas o sedes reales.\n"
        "BRIEF:\n" + brief.model_dump_json() + "\nESCENAS en el orden de las imágenes:\n"
        + json.dumps([{"id": scene.id, "title": scene.data["title"]} for scene in sb.scenes], ensure_ascii=False),
        images, stage="revisión visual independiente", max_output=3000)


def repair_visuals(plan, direction, bank, brief, client, checks, issues):
    prompt = ("Corrige SOLO los elementos visuales del storyboard según estos problemas. Puedes acortar "
              "títulos y detalles, simplificar diagramas o cambiar la composición dentro del repertorio. "
              "Mantén EXACTAMENTE ids, orden, número de escenas, narration, claim_ids de locución e image_id. "
              "No cambies la marca. No inventes datos ni relaciones. Devuelve el storyboard completo.\n"
              "PROBLEMAS:\n" + json.dumps(issues, ensure_ascii=False) + "\nSTORYBOARD:\n" + plan.model_dump_json()
              + "\nHECHOS:\n" + json.dumps({key: fact.text for key, fact in bank.published().items()}, ensure_ascii=False))
    def validate(result):
        before = [(scene.id, scene.narration, scene.claim_ids, scene.image_id) for scene in plan.scenes]
        after = [(scene.id, scene.narration, scene.claim_ids, scene.image_id) for scene in result.scenes]
        if before != after:
            raise ValueError("La reparación visual debe conservar ids, orden y locuciones exactamente")
        repair_items(result.scenes, bank, checks, client)
        validate_storyboard(result, bank, direction, checks)
    return client.json(DirectedStoryboard, SYSTEM, prompt, validate=validate, stage="reparación visual", max_output=12000)
