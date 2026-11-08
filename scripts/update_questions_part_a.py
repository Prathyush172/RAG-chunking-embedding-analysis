import json
from pathlib import Path
from app.core.sections import parse_sections, find_section_for_offset
from app.core.evaluation import (
    EvidenceLocator,
    EvidenceValidator,
    Question,
    EvidenceItem,
    compute_longest_common_word_run,
    compute_jaccard_similarity,
)

CLEAN_DIR = Path("data/clean")
QUESTIONS_FILE = Path("data/eval/questions.json")

def main():
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    # 1. Update dns-06
    dns_txt = (CLEAN_DIR / "dns.txt").read_text(encoding="utf-8")
    dns_quote = dns_txt[11824:12263]
    for q in raw_data:
        if q["id"] == "dns-06":
            q["question"] = "What is the functional definition and scope of responsibility for a name server program?"
            q["evidence"] = [{
                "doc_id": "dns",
                "quote": dns_quote,
                "char_start": 11824,
                "char_end": 12263,
            }]
            q["reference_answer"] = (
                "Name servers store information about the domain tree structure and resource sets. "
                "While a server may cache data for any subtree, it typically maintains complete "
                "authoritative information for a specific subset and holds pointers to other servers "
                "for the rest of the namespace."
            )
            q["type"] = "definition"
            q["difficulty"] = "easy"

        # 2. Rewrite wording-overlap flagged questions
        elif q["id"] == "tcp-02":
            q["question"] = "Why should transport stacks avoid constantly readjusting segment sizing when network links exhibit dynamic payload compression?"
        elif q["id"] == "http-03":
            q["question"] = "How does a web server determine freshness when an incoming request provides a timestamp validator?"
        elif q["id"] == "http-04":
            q["question"] = "What signal does receiving response code 304 convey to downstream browser caches regarding asset freshness?"

    # Cache parsed sections
    doc_sections = {}
    for doc_file in CLEAN_DIR.glob("*.txt"):
        doc_id = doc_file.stem
        doc_sections[doc_id] = parse_sections(doc_file.read_text(encoding="utf-8"))

    # Track section changes
    section_changes = []

    for q in raw_data:
        first_ev = q["evidence"][0]
        doc_id = first_ev["doc_id"]
        char_start = first_ev["char_start"]
        secs = doc_sections[doc_id]
        matched_sec = find_section_for_offset(secs, char_start)
        new_sec_label = matched_sec.label if matched_sec else q.get("section", "")

        old_sec_label = q.get("section", "")
        if old_sec_label != new_sec_label:
            section_changes.append((q["id"], old_sec_label, new_sec_label))
            q["section"] = new_sec_label

        # Lexical overlap
        ev_combined = " ".join(e["quote"] for e in q["evidence"] if e.get("quote"))
        run = compute_longest_common_word_run(q["question"], ev_combined)
        jac = compute_jaccard_similarity(q["question"], ev_combined)
        q["lexical_overlap_run"] = run
        q["lexical_overlap_jaccard"] = round(jac, 4)
        q["flagged_too_easy"] = bool(run >= 5 or jac > 0.5)

    print(f"Total questions with section changed: {len(section_changes)}")
    for qid, old_s, new_s in section_changes:
        print(f"  - [{qid}] '{old_s}' -> '{new_s}'")

    too_easy_flags = [q["id"] for q in raw_data if q["flagged_too_easy"]]
    print(f"\nQuestions flagged as too_easy: {len(too_easy_flags)}")
    if too_easy_flags:
        print(f"  IDs: {too_easy_flags}")

    # Save questions.json
    with open(QUESTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, indent=2)
    print(f"\nSaved updated questions to {QUESTIONS_FILE}")

    # Validate using EvidenceValidator
    locator = EvidenceLocator(CLEAN_DIR)
    validator = EvidenceValidator(locator)
    q_objects = [
        Question(
            id=d["id"],
            question=d["question"],
            doc_id=d["doc_id"],
            section=d["section"],
            evidence=[EvidenceItem(**e) for e in d["evidence"]],
            reference_answer=d["reference_answer"],
            type=d["type"],
            difficulty=d["difficulty"],
            verified=d.get("verified", False),
            drafted_by=d.get("drafted_by", "llm"),
            notes=d.get("notes"),
            reviewer=d.get("reviewer"),
            lexical_overlap_run=d.get("lexical_overlap_run"),
            lexical_overlap_jaccard=d.get("lexical_overlap_jaccard"),
            flagged_too_easy=d.get("flagged_too_easy", False),
        )
        for d in raw_data
    ]
    issues = validator.validate_all(q_objects)
    print(f"\nValidator results on all {len(q_objects)} questions:")
    print(f"Total issues: {len(issues)}")
    for iss in issues:
        print(f"  [{iss.question_id}] {iss.issue_type}: {iss.message}")

if __name__ == "__main__":
    main()
