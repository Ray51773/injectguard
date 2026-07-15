from __future__ import annotations

import json
from pathlib import Path

REFERENCE_TEXTS = {
    "ENV_FILE": [
        "DATABASE_URL POSTGRES_HOST API_KEY DEBUG FEATURE_FLAG PORT SECRET_TOKEN",
        "KEY=value environment variables service credentials connection strings",
    ],
    "CREDENTIALS": [
        "private key certificate token password access key client secret credential",
        "ssh rsa pem certificate bearer token authentication material",
    ],
    "JSON": [
        "json api response object array id status data timestamp request metadata",
        "structured fields numbers booleans nested objects machine readable payload",
    ],
    "YAML": [
        "yaml config service deployment image ports environment variables",
        "configuration keys values lists maps infrastructure settings",
    ],
    "SOURCE_COMMENT": [
        "code comment function parameter return value implementation note todo",
        "developer explanation class method variable algorithm edge case",
    ],
    "LOG": [
        "timestamp level info warning error request latency service host process",
        "application log trace stack status event message",
    ],
    "HTML": [
        "html body div paragraph link title meta webpage content navigation",
        "document markup element attribute script style heading",
    ],
    "MARKDOWN": [
        "markdown heading paragraph bullet list link documentation prose",
        "readme guide notes explanation example code block",
    ],
    "PDF_TEXT": [
        "document page paragraph section table figure extracted text report",
        "paper invoice manual policy article pagination",
    ],
    "TOOL_RESPONSE": [
        "tool response status result observation output error metadata",
        "function result json fields command output structured artifact",
    ],
    "UNKNOWN": [
        "generic text data content record document output field value",
        "unclassified file payload extracted content",
    ],
}


def main() -> int:
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:
        raise SystemExit(f"sentence-transformers is required to build centroids: {exc}")

    model_name = "sentence-transformers/all-MiniLM-L6-v2"
    model = SentenceTransformer(model_name, local_files_only=True)
    centroids = {}
    for name, references in REFERENCE_TEXTS.items():
        vectors = model.encode(references, normalize_embeddings=True)
        centroid = vectors.mean(axis=0)
        norm = (centroid * centroid).sum() ** 0.5
        centroids[name] = (centroid / norm).tolist()

    output = {
        "model": model_name,
        "dimension": len(next(iter(centroids.values()))),
        "centroids": centroids,
    }
    path = Path(__file__).resolve().parents[1] / "src" / "injectguard" / "data" / "centroids.json"
    path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

