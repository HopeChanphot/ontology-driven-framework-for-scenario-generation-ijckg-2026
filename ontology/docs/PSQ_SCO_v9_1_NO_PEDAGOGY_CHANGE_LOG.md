# PSQ-SCO v9.1 No-Pedagogy Correction Change Log

Date: 2026-06-30

## Reason for Correction

The reviewer-aligned PSQ-SCO scope should not include a
`PedagogicalKnowledgeEntity` module. PSQ-SCO is a scenario-control ontology,
not a full pedagogical ontology. The v9.1 correction removes the pedagogical
branch and related runtime/binding fields while preserving CQ1-CQ4 scenario
control, cybersecurity structure, content-quality control, and evidence
grounding.

## Main Changes

1. Removed `PedagogicalKnowledgeEntity` and all subclasses.
2. Removed Bloom, knowledge-type, learning-objective, hint, feedback, and
   pedagogical-constraint individuals.
3. Removed pedagogy-linking properties from templates and supporting resources.
4. Removed pedagogical runtime fields from `data/ontology_runtime_v9_1`.
5. Removed `pedagogical_alignment` from the semantic packet schema.
6. Updated ontology header and scope boundary to say v9.1 has no pedagogical
   knowledge module.
7. Regenerated graph exports, bindings, runtime data, summary, and validation
   inputs.
8. Removed malformed anonymous OWL restrictions left after scope pruning, so
   Protege should not display an artificial `Error1` parent above
   `ScenarioTemplate`.

## Resulting Size

- Classes: 73
- Object properties: 49
- Datatype properties: 39
- Annotation properties: 17
- Named individuals: 133
- Graph nodes: 311
- Graph edges: 3164
- Runtime records: 12425

## Removed Scope

Removed resources: 36

Removed properties: 10

Removed triples: 605

Malformed anonymous OWL restrictions removed: 1

## Reviewer-Safe Wording

PSQ-SCO v9.1 is a scenario-control ontology and ontology-based knowledge graph.
It does not contain a `PedagogicalKnowledgeEntity` branch and does not claim to
model pedagogy. It retains only scenario selection, cybersecurity structure,
generated-content quality control, evidence grounding, semantic-packet export,
and validation metadata.
