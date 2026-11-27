# RAZU e-depot — access restrictions for documents

Design documents for enforcing access restrictions on documents in the RAZU
e-depot (public / personal copy / study room / individually granted), including
an architecture with a single enforcement point (the "resolver"), a stateless
session service, and layered bot protection on the low-threshold routes.

Status: design, for discussion (2026-11-27).

## The documents

| File | Language | What it is |
| --- | --- | --- |
| [`access-restrictions-overview.en.md`](access-restrictions-overview.en.md) | English | A short **summary** of the approach, with diagrams, the strengths of the design, residual risks and open points |
| [`architectuur-toegangsbeperkingen.md`](architectuur-toegangsbeperkingen.md) | Dutch | The **architecture**: the full elaboration — resolver as PEP/PDP chokepoint, stateless session service (`sessie.razu.nl`) signing context tokens, attribute store, authorization register, central terms source, RDF sidecars as source of truth, storage/public sphere, anti-automation layers, residual risks, per-category flows (Bijlage A), standards (Bijlage B), glossary (Bijlage C) |
| [`requirements-toegangsbeperkingen.md`](requirements-toegangsbeperkingen.md) | Dutch | The **requirements**: the *what* and *why* — legal bases, the four access categories, the actor matrix, metadata restrictions, management requirements |
| [`example_flows_cat1.md`](example_flows_cat1.md) | English | **Example flows** for category 1 — direct consent and an optional e-mail verification route, both using the token-only architecture |


The two Dutch documents are authoritative; the English overview and example flows are supporting documents.

