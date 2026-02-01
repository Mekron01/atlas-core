from collections import defaultdict

def project_artifacts(events):
    artifacts = {}
    for e in events:
        aid = e.get("artifact_id")
        if not aid:
            continue
        artifacts.setdefault(aid, {"artifact_id": aid, "events": []})
        artifacts[aid]["events"].append(e)
    return artifacts
