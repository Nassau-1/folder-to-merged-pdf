from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


ALLOWED_FINAL_STATUSES = {
    "no-course-change",
    "course-update-required",
    "new-course-recommended",
    "manual-review-required",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a Course Impact report from changed files.")
    parser.add_argument("--repo-name", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--base-ref", default="")
    parser.add_argument("--head-ref", default="")
    parser.add_argument("--changed-files-file", required=True)
    parser.add_argument("--map", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--report-md", required=True)
    return parser.parse_args()


def read_changed_files(path: str) -> list[str]:
    changed: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        value = line.strip().replace("\\", "/")
        if value:
            changed.append(value)
    return changed


def load_map(path: str) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("course-impact map must be a mapping")
    return data


def matches_pattern(file_path: str, pattern: str) -> bool:
    posix_path = PurePosixPath(file_path)
    return posix_path.match(pattern) or PurePosixPath(posix_path.name).match(pattern)


def documentation_acknowledged(changed_files: list[str], doc_patterns: list[str]) -> bool:
    return any(
        matches_pattern(changed_file, pattern)
        for changed_file in changed_files
        for pattern in doc_patterns
    )


def aggregate_confidence(confidences: list[str]) -> str:
    if not confidences:
        return "low"
    if "high" in confidences:
        return "high"
    if "medium" in confidences:
        return "medium"
    return "low"


def choose_final_status(rule_hits: list[dict[str, Any]]) -> str:
    if not rule_hits:
        return "no-course-change"

    status_hints = [hit["status_hint"] for hit in rule_hits]
    if "manual-review-required" in status_hints:
        return "manual-review-required"
    if "new-course-recommended" in status_hints:
        return "new-course-recommended"
    if "course-update-required" in status_hints:
        return "course-update-required"
    return "manual-review-required"


def build_report(args: argparse.Namespace, config: dict[str, Any], changed_files: list[str]) -> dict[str, Any]:
    rule_hits: list[dict[str, Any]] = []
    detected_concepts: set[str] = set()
    existing_notes: set[str] = set()
    new_notes: set[str] = set()
    recommended_actions: set[str] = set()
    example_files: list[str] = []
    confidences: list[str] = []

    repo_project_case = f"[[Project Course - {args.repo_name} - Architecture]]"

    for rule in config.get("rules", []):
        patterns = list(rule.get("patterns", []))
        matched_files = [
            file_path for file_path in changed_files
            if any(matches_pattern(file_path, pattern) for pattern in patterns)
        ]
        if not matched_files:
            continue

        confidence = str(rule.get("confidence", "low"))
        status_hint = str(rule.get("status_hint", "manual-review-required"))
        concepts = list(rule.get("concepts", []))
        note_targets = list(rule.get("note_targets", []))
        project_case_action = str(rule.get("project_case_action", "") or "")

        for concept in concepts:
            detected_concepts.add(concept)

        for note_target in note_targets:
            note = str(note_target.get("note", "")).strip()
            state = str(note_target.get("state", "existing")).strip()
            action = str(note_target.get("action", "enrich-existing")).strip()
            if note:
                if state == "existing":
                    existing_notes.add(note)
                else:
                    new_notes.add(note)
            if action:
                recommended_actions.add(action)

        if project_case_action == "update-if-existing":
            existing_notes.add(repo_project_case)
            recommended_actions.add("update-project-case-if-existing")
        elif project_case_action == "update-or-create":
            new_notes.add(repo_project_case)
            recommended_actions.add("update-or-create-project-case")
        elif project_case_action == "manual-review":
            recommended_actions.add("manual-project-case-review")

        for matched_file in matched_files:
            if matched_file not in example_files:
                example_files.append(matched_file)

        confidences.append(confidence)
        rule_hits.append(
            {
                "rule_id": rule.get("id", ""),
                "matched_files": matched_files,
                "confidence": confidence,
                "status_hint": status_hint,
                "concepts": concepts,
                "existing_notes": [target["note"] for target in note_targets if target.get("state") == "existing"],
                "candidate_notes": [target["note"] for target in note_targets if target.get("state") != "existing"],
                "project_case_action": project_case_action,
            }
        )

    final_status = choose_final_status(rule_hits)
    if final_status not in ALLOWED_FINAL_STATUSES:
        final_status = "manual-review-required"

    doc_patterns = list(config.get("documentation_ack_patterns", []))

    return {
        "report_schema_version": 1,
        "repo": args.repo_name,
        "branch": args.branch,
        "event": args.event_name,
        "base_ref": args.base_ref,
        "head_ref": args.head_ref,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "changed_files": changed_files,
        "detected_concepts": sorted(detected_concepts),
        "existing_notes_impacted": sorted(existing_notes),
        "new_notes_recommended": sorted(new_notes),
        "example_files_to_reuse": example_files,
        "recommended_actions": sorted(recommended_actions),
        "rule_hits": rule_hits,
        "documentation_acknowledged": documentation_acknowledged(changed_files, doc_patterns),
        "overall_confidence": aggregate_confidence(confidences),
        "final_status": final_status,
    }


def render_markdown(report: dict[str, Any]) -> str:
    def bullets(items: list[str]) -> str:
        if not items:
            return "- none"
        return "\n".join(f"- `{item}`" if not item.startswith("[[") else f"- {item}" for item in items)

    rule_lines: list[str] = []
    for hit in report["rule_hits"]:
        files = ", ".join(f"`{value}`" for value in hit["matched_files"]) or "`none`"
        concepts = ", ".join(hit["concepts"]) or "none"
        rule_lines.append(
            f"- `{hit['rule_id']}` | confidence=`{hit['confidence']}` | status_hint=`{hit['status_hint']}` | files={files} | concepts={concepts}"
        )

    if not rule_lines:
        rule_lines = ["- none"]

    return f"""# Course Impact Report

## Metadata

- repo: `{report['repo']}`
- report_schema_version: `{report['report_schema_version']}`
- branch: `{report['branch']}`
- event: `{report['event']}`
- base_ref: `{report['base_ref'] or 'n/a'}`
- head_ref: `{report['head_ref'] or 'n/a'}`
- generated_at: `{report['generated_at']}`

## Final Status

- status: `{report['final_status']}`
- overall_confidence: `{report['overall_confidence']}`
- documentation_acknowledged: `{str(report['documentation_acknowledged']).lower()}`

## Changed Files

{bullets(report['changed_files'])}

## Detected Concepts

{bullets(report['detected_concepts'])}

## Existing Notes Impacted

{bullets(report['existing_notes_impacted'])}

## New Notes Recommended

{bullets(report['new_notes_recommended'])}

## Example Files To Reuse

{bullets(report['example_files_to_reuse'])}

## Recommended Actions

{bullets(report['recommended_actions'])}

## Rule Hits

{chr(10).join(rule_lines)}
"""


def main() -> None:
    args = parse_args()
    config = load_map(args.map)
    changed_files = read_changed_files(args.changed_files_file)
    report = build_report(args, config, changed_files)

    report_json_path = Path(args.report_json)
    report_md_path = Path(args.report_md)
    report_json_path.parent.mkdir(parents=True, exist_ok=True)
    report_md_path.parent.mkdir(parents=True, exist_ok=True)

    report_json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    report_md_path.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
