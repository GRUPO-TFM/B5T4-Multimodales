"""Capa de datos: acceso a la carpeta de la empresa (manifiesto, documentos de contexto y extracción de texto).
Es la única capa que sabe dónde están los ficheros; los agentes le piden lo que necesitan."""
from .contexts import ContextDoc, ContextSection, load_contexts, section_index
from .extract import Page, extract, pdf_page_images, pdf_pages
from .manifest import CorpusFile, load_manifest, select, summary

__all__ = ["ContextDoc", "ContextSection", "load_contexts", "section_index", "Page", "extract", "pdf_page_images",
           "pdf_pages", "CorpusFile", "load_manifest", "select", "summary"]
