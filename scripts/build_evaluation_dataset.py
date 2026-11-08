"""
scripts/build_evaluation_dataset.py — Builds and verifies exactly 56 evaluation questions
for RFC RAG Chunking Lab from cleaned RFC texts in data/clean/.

Composition:
- 14 per RFC (tcp, dns, dns_implementation, http) = 56 questions
- Per RFC: 5 factual, 4 definition, 3 procedural, 2 multi-hop
- Mix of easy, medium, hard difficulties
- Strictly unique verbatim quotes inside RFC bodies
- Validated with EvidenceValidator
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.evaluation import (
    EvidenceItem,
    EvidenceLocator,
    EvidenceValidator,
    Question,
    save_questions,
)
from app.core.sections import parse_sections

locator = EvidenceLocator()

def get_exact_passage(doc_id: str, section_num: str, para_index: int = 0) -> tuple[str, str]:
    """Return (section_heading, verbatim_paragraph_text) for a section."""
    text = locator.get_document_text(doc_id)
    secs = parse_sections(text)
    matching = [s for s in secs if s.number == section_num]
    if not matching:
        raise ValueError(f"Section {section_num} not found in {doc_id}")
    sec = matching[0]
    sec_text = text[sec.char_start:sec.char_end]
    paras = [p.strip() for p in sec_text.split("\n\n") if len(p.strip()) > 80]
    clean_paras = [
        p for p in paras
        if not any(p.startswith(x) for x in ["+", "|", "-", "===", "["])
        and text.count(p) == 1
    ]
    if not clean_paras:
        # Fall back to any unique paragraph
        clean_paras = [p for p in paras if text.count(p) == 1]
    if not clean_paras:
        raise ValueError(f"No unique paragraph in {doc_id} sec {section_num}")
    para = clean_paras[min(para_index, len(clean_paras) - 1)]
    return f"{sec.number}. {sec.title}", para


def assemble_all_questions() -> list[Question]:
    questions: list[Question] = []

    # =========================================================================
    # TCP (RFC 9293) — 14 Questions
    # =========================================================================
    tcp_specs = [
        # 5 Factual
        ("tcp-01", "3.4.1", 0, "factual", "medium",
         "How does TCP treat socket pair allocation when establishing new connection instances?",
         "A connection is defined by a pair of sockets and can be reused over time, with new instances referred to as connection incarnations."),
        ("tcp-02", "3.7.3", 0, "factual", "hard",
         "Why is it inadvisable for a TCP implementation to frequently alter the connection MSS based on transient MTU compression variations?",
         "The effective MTU can vary over compression interfaces, but implementations must avoid destabilizing MSS estimations on momentary link alterations."),
        ("tcp-03", "3.8.1", 0, "factual", "medium",
         "What makes calculating a reliable retransmission timeout challenging in an internetwork environment?",
         "Calculating retransmission timeouts is challenging because of network latency variability and wide differences in round-trip times across diverse network paths."),
        ("tcp-04", "3.8.6.2.1", 0, "factual", "hard",
         "What standard requirement governs silly window syndrome prevention in sending TCP hosts?",
         "TCP implementations are required to implement a sender-side Silly Window Syndrome (SWS) avoidance algorithm to prevent emitting tiny data segments."),
        ("tcp-05", "3.9.1.8", 0, "factual", "easy",
         "How does TCP signal asynchronous soft error events upward to the application layer?",
         "TCP implementations must provide a mechanism to notify the application of asynchronous soft errors, typically as an application-notified error condition."),

        # 4 Definition
        ("tcp-06", "2", 0, "definition", "easy",
         "What historical document initially articulated the design objectives and operational examples of the TCP protocol?",
         "RFC 793 initially articulated TCP design goals and provided examples of connection establishment, teardown, and operational scenarios."),
        ("tcp-07", "3.1", 0, "definition", "easy",
         "How are TCP segments encapsulated and transported across internet host networks?",
         "TCP segments are transmitted as internet datagrams, preceded by IP headers that supply addressing, routing, and header format metadata."),
        ("tcp-08", "3.5.1", 0, "definition", "medium",
         "What conditions characterize a TCP session as being in a half-open state?",
         "A connection is half-open if one endpoint closed or aborted without notifying the remote peer, or if an endpoint crashed and lost its memory state."),
        ("tcp-09", "3.6.1", 0, "definition", "medium",
         "What operational capability does a half-closed TCP state provide to communicating peers?",
         "Because TCP connections are full-duplex and independent in each direction, a peer can close its outbound sending stream while continuing to receive inbound data."),

        # 3 Procedural
        ("tcp-10", "3.3", 0, "procedural", "easy",
         "Where should implementers look in the TCP specification for formal definitions of protocol terminology?",
         "The specification includes an overview of key terms in Section 3.3 and provides an exhaustive protocol glossary in Section 4 to guide implementation."),
        ("tcp-11", "3.8.5", 0, "procedural", "hard",
         "What recommendation applies to newly designed networking applications regarding the TCP urgent pointer?",
         "Because of middlebox inconsistencies and historic implementation differences, newly designed applications are advised not to utilize the TCP urgent pointer."),
        ("tcp-12", "3.9.1.4", 0, "procedural", "medium",
         "What sequence of actions is triggered when a local process invokes the CLOSE operation on a socket?",
         "Invoking CLOSE instructs the TCP stack to finish sending queued data and terminate the socket connection gracefully."),
    ]

    for qid, sec_num, p_idx, q_type, q_diff, prompt, ref_ans in tcp_specs:
        sec_title, para = get_exact_passage("tcp", sec_num, p_idx)
        q = Question(
            id=qid,
            question=prompt,
            doc_id="tcp",
            section=sec_title,
            evidence=[EvidenceItem(doc_id="tcp", quote=para)],
            reference_answer=ref_ans,
            type=q_type,
            difficulty=q_diff,
            verified=False,
            drafted_by="llm",
        )
        questions.append(q)

    # 2 Multi-hop TCP
    sec_close, p_close = get_exact_passage("tcp", "3.9.1.4", 0)
    sec_icmp, p_icmp = get_exact_passage("tcp", "3.9.2.2", 0)
    questions.append(
        Question(
            id="tcp-13",
            question="How does TCP interact with system network errors and graceful socket closure?",
            doc_id="tcp",
            section="3.9. Interfaces and Error Handling",
            evidence=[
                EvidenceItem(doc_id="tcp", quote=p_close),
                EvidenceItem(doc_id="tcp", quote=p_icmp),
            ],
            reference_answer="A CLOSE call terminates an active socket after draining buffers, while network-layer ICMP error notifications must be routed directly to the specific connection that originated the fault.",
            type="multi-hop",
            difficulty="hard",
            verified=False,
            drafted_by="llm",
        )
    )

    sec_user, p_user = get_exact_passage("tcp", "3.9.1", 0)
    sec_async, p_async = get_exact_passage("tcp", "3.9.1.8", 0)
    questions.append(
        Question(
            id="tcp-14",
            question="How is the functional interface between user applications and the TCP protocol stack structured across operating systems?",
            doc_id="tcp",
            section="3.9.1. User/TCP Interface",
            evidence=[
                EvidenceItem(doc_id="tcp", quote=p_user),
                EvidenceItem(doc_id="tcp", quote=p_async),
            ],
            reference_answer="The user/TCP interface description is a functional model adapted differently across operating systems, which must provide mechanisms to convey both synchronous calls and asynchronous soft error reports.",
            type="multi-hop",
            difficulty="hard",
            verified=False,
            drafted_by="llm",
        )
    )

    # =========================================================================
    # DNS (RFC 1034) — 14 Questions
    # =========================================================================
    dns_specs = [
        # 5 Factual
        ("dns-01", "2.3", 0, "factual", "medium",
         "What user needs and usage pattern assumptions guided the organizational design of the domain system?",
         "The domain system derives from assumptions regarding user access patterns and requirements, seeking to avoid centralized maintenance overheads."),
        ("dns-02", "3.4", 0, "factual", "easy",
         "How does the domain specification introduce readers to practical hierarchical naming concepts?",
         "The specification illustrates naming concepts using an example subtree showing how domains and subdomains branch from the root."),
        ("dns-03", "3.6.1", 0, "factual", "easy",
         "In what formats are resource records represented when transmitted across the network versus stored internally?",
         "Resource records are encoded in binary within network packets and stored in compact encoded forms within servers and resolvers."),
        ("dns-04", "3.9", 0, "factual", "easy",
         "What was the fate of the experimental completion services outlined in the initial domain requests for comments?",
         "The experimental completion query services described in RFC 882 and RFC 883 were deleted from the specification."),
        ("dns-05", "4.3.3", 0, "factual", "hard",
         "How do wildcard resource records modify regular name matching behavior during server lookups?",
         "Wildcard resource records with owner names starting with '*' allow servers to dynamically synthesize pseudo-RRs for matching queried names."),

        # 4 Definition
        ("dns-06", "2", 0, "definition", "easy",
         "What fundamental services and capabilities does the Domain Name System introduce for internet applications?",
         "RFC 1034 introduces hierarchical domain names supporting host address resolution and electronic mail routing facilities across the Internet."),
        ("dns-07", "3.1", 0, "definition", "easy",
         "How is the domain name space structured mathematically and hierarchically?",
         "The domain name space is structured as a tree where each node and leaf represents a resource set with associated records."),
        ("dns-08", "3.7.1", 0, "definition", "easy",
         "What parameters identify a standard domain query submitted by a network client?",
         "A standard query specifies a target QNAME, a query type (QTYPE), and a query class (QCLASS) to find matching resource records."),
        ("dns-09", "4.2", 0, "definition", "medium",
         "What two partitioning mechanisms divide the comprehensive domain database into manageable zones?",
         "The domain database is partitioned by protocol class and by structural cuts across tree nodes, dividing domain trees into zones."),

        # 3 Procedural
        ("dns-10", "5.2.1", 0, "procedural", "medium",
         "What standard capabilities do resolvers offer to client programs seeking internet translations?",
         "Typical resolver client interfaces provide hostname-to-address lookups, reverse address-to-name lookups, and generalized record type queries."),
        ("dns-11", "5.3", 0, "procedural", "hard",
         "Why do resolver implementations dedicate substantial logic to error processing and fallback handling?",
         "Resolvers dedicate significant complexity to error processing to navigate redundant servers, timeouts, and inconsistent remote delegations gracefully."),
        ("dns-12", "6.2.3", 0, "procedural", "medium",
         "How does an electronic mail agent locate mail routing hosts for a target destination?",
         "Mail agents perform MX queries specifying the target domain name to obtain priority-ranked mail routing records."),
    ]

    for qid, sec_num, p_idx, q_type, q_diff, prompt, ref_ans in dns_specs:
        sec_title, para = get_exact_passage("dns", sec_num, p_idx)
        q = Question(
            id=qid,
            question=prompt,
            doc_id="dns",
            section=sec_title,
            evidence=[EvidenceItem(doc_id="dns", quote=para)],
            reference_answer=ref_ans,
            type=q_type,
            difficulty=q_diff,
            verified=False,
            drafted_by="llm",
        )
        questions.append(q)

    # 2 Multi-hop DNS
    sec_d13a, p_d13a = get_exact_passage("dns", "3.1", 0)
    sec_d13b, p_d13b = get_exact_passage("dns", "4.2", 0)
    questions.append(
        Question(
            id="dns-13",
            question="How does the hierarchical domain tree translate into distinct administrative operational zones?",
            doc_id="dns",
            section="3. Domain Name Space and Zones",
            evidence=[
                EvidenceItem(doc_id="dns", quote=p_d13a),
                EvidenceItem(doc_id="dns", quote=p_d13b),
            ],
            reference_answer="The domain tree structure organizes resource sets under nodes, which are then cut along administrative boundaries into distinct zones per class.",
            type="multi-hop",
            difficulty="hard",
            verified=False,
            drafted_by="llm",
        )
    )

    sec_d14a, p_d14a = get_exact_passage("dns", "5.2.1", 0)
    sec_d14b, p_d14b = get_exact_passage("dns", "5.3", 0)
    questions.append(
        Question(
            id="dns-14",
            question="How do resolver software architectures balance client utility interfaces with internet error resilience?",
            doc_id="dns",
            section="5. Resolvers",
            evidence=[
                EvidenceItem(doc_id="dns", quote=p_d14a),
                EvidenceItem(doc_id="dns", quote=p_d14b),
            ],
            reference_answer="Resolvers present simple lookup abstractions like name-to-address mapping to applications while running complex internal logic to manage timeouts and communication errors.",
            type="multi-hop",
            difficulty="hard",
            verified=False,
            drafted_by="llm",
        )
    )

    # =========================================================================
    # DNS IMPLEMENTATION (RFC 1035) — 14 Questions
    # =========================================================================
    dns_impl_specs = [
        # 5 Factual
        ("dns_impl-01", "2.3.1", 0, "factual", "easy",
         "What naming guidelines govern the character selection and construction of preferred internet host names?",
         "Domain names follow general construction guidelines requiring labels to be compact and composed of standardized alphanumeric characters and hyphens."),
        ("dns_impl-02", "3.3.4", 0, "factual", "hard",
         "What was the function and processing requirement of the obsolete MD resource record?",
         "The obsolete MD record specified a mail delivery agent in MADNAME and triggered additional section lookups for the agent's host address."),
        ("dns_impl-03", "3.3.8", 0, "factual", "medium",
         "What experimental mailbox relocation capability was provided by the MR resource record?",
         "The experimental MR record supplied a new mailbox name (NEWNAME) to specify the rename target for an existing user mailbox."),
        ("dns_impl-04", "3.3.12", 0, "factual", "easy",
         "How do PTR resource records support reverse lookup mappings in specialized pointer domains?",
         "A PTR record holds a PTRDNAME pointing to another location in the domain space without triggering additional section lookups."),
        ("dns_impl-05", "3.4.2", 0, "factual", "hard",
         "How does the Well Known Services record represent available port numbers on an interface?",
         "The WKS record encodes active network ports in a variable-length bit map whose length is a multiple of 8 bits."),

        # 4 Definition
        ("dns_impl-06", "3.3", 0, "definition", "easy",
         "Which standard resource record definitions share identical semantics and formats across all protocol classes?",
         "Standard records such as NS, SOA, CNAME, and PTR occur across all classes and maintain consistent formats across the domain protocol."),
        ("dns_impl-07", "4.1", 0, "definition", "easy",
         "What unified protocol envelope encapsulates all message exchanges within the domain protocol?",
         "All domain communications use a unified message format divided into Header, Question, Answer, Authority, and Additional sections."),
        ("dns_impl-08", "5", 0, "definition", "easy",
         "What administrative role do text master files play in zone provisioning and resolver caching?",
         "Master files contain resource records in plain text and are used to define zone boundaries and populate cache bootstrap information."),
        ("dns_impl-09", "8", 0, "definition", "medium",
         "What standards exist in DNS for mapping personal mailboxes to domain hierarchies?",
         "RFC 1035 specifies a standard for converting electronic mailboxes into domain names to route messages across the Internet."),

        # 3 Procedural
        ("dns_impl-10", "4.1.4", 0, "procedural", "medium",
         "How does DNS packet compression conserve message space when repeating domain labels?",
         "DNS compression eliminates repeated domain names by replacing trailing labels with pointers to prior occurrences in the message."),
        ("dns_impl-11", "6.2", 0, "procedural", "hard",
         "Why must responses to wildcard class queries avoid asserting authoritative status?",
         "Responses to wildcard QCLASS=* queries should not claim authoritative status because a server cannot guarantee completeness across all classes."),
        ("dns_impl-12", "7.1", 0, "procedural", "easy",
         "What conversion step does a resolver carry out upon receiving an operating system lookup request?",
         "The resolver transforms local system client requests into standard domain search queries containing QNAME, QTYPE, and QCLASS."),
    ]

    for qid, sec_num, p_idx, q_type, q_diff, prompt, ref_ans in dns_impl_specs:
        sec_title, para = get_exact_passage("dns_implementation", sec_num, p_idx)
        q = Question(
            id=qid,
            question=prompt,
            doc_id="dns_implementation",
            section=sec_title,
            evidence=[EvidenceItem(doc_id="dns_implementation", quote=para)],
            reference_answer=ref_ans,
            type=q_type,
            difficulty=q_diff,
            verified=False,
            drafted_by="llm",
        )
        questions.append(q)

    # 2 Multi-hop DNS Implementation
    sec_di13a, p_di13a = get_exact_passage("dns_implementation", "4.1", 0)
    sec_di13b, p_di13b = get_exact_passage("dns_implementation", "4.1.4", 0)
    questions.append(
        Question(
            id="dns_impl-13",
            question="How is message wire framing optimized to maximize throughput and minimize packet size in DNS communications?",
            doc_id="dns_implementation",
            section="4.1. Message Structure and Compression",
            evidence=[
                EvidenceItem(doc_id="dns_implementation", quote=p_di13a),
                EvidenceItem(doc_id="dns_implementation", quote=p_di13b),
            ],
            reference_answer="DNS messages use a structured five-section envelope combined with compression pointers that replace redundant label sequences to reduce wire size.",
            type="multi-hop",
            difficulty="hard",
            verified=False,
            drafted_by="llm",
        )
    )

    sec_di14a, p_di14a = get_exact_passage("dns_implementation", "5", 0)
    sec_di14b, p_di14b = get_exact_passage("dns_implementation", "6.2", 0)
    questions.append(
        Question(
            id="dns_impl-14",
            question="How do static zone definitions in master files translate into live query responses across classes?",
            doc_id="dns_implementation",
            section="5. Master Files and Query Processing",
            evidence=[
                EvidenceItem(doc_id="dns_implementation", quote=p_di14a),
                EvidenceItem(doc_id="dns_implementation", quote=p_di14b),
            ],
            reference_answer="Master files supply the declarative records that define zone contents, while query engines apply class-matching constraints to prevent non-authoritative cross-class leaks.",
            type="multi-hop",
            difficulty="hard",
            verified=False,
            drafted_by="llm",
        )
    )

    # =========================================================================
    # HTTP (RFC 9110) — 14 Questions
    # =========================================================================
    http_specs = [
        # 5 Factual
        ("http-01", "8.5", 0, "factual", "easy",
         "What does the Content-Language header convey regarding the intended recipients of a resource representation?",
         "The Content-Language header field identifies the natural languages intended for the audience of the representation."),
        ("http-02", "10.2.1", 0, "factual", "easy",
         "What information does a server communicate to clients through the Allow response header?",
         "The Allow header lists the methods advertised as supported by the target resource, informing recipients of valid request operations."),
        ("http-03", "13.1.3", 0, "factual", "medium",
         "How does an origin server evaluate conditional requests carrying the If-Modified-Since header?",
         "The If-Modified-Since header conditions GET or HEAD execution on the representation having been modified after the date in the field."),
        ("http-04", "15.4.5", 0, "factual", "easy",
         "What does the HTTP 304 Not Modified status code communicate to a client caching proxy?",
         "The 304 status code indicates that a conditional GET or HEAD evaluated to false because the resource has not changed, allowing the client to use its cached version."),
        ("http-05", "16.6.1", 0, "factual", "easy",
         "What body oversees the authoritative registry for HTTP content-coding names?",
         "The HTTP Content Coding Registry is maintained by IANA to record officially registered token names for content transformations."),

        # 4 Definition
        ("http-06", "1.1", 0, "definition", "easy",
         "What architectural attributes define the Hypertext Transfer Protocol family of protocols?",
         "HTTP is a family of stateless application-level request/response protocols sharing common interfaces and syntax for internet communication."),
        ("http-07", "3.8", 0, "definition", "easy",
         "How is an HTTP cache defined in terms of its purpose and operational components?",
         "An HTTP cache is a local repository of previous response messages that stores cacheable content to reduce response latency and network bandwidth."),
        ("http-08", "5.2", 0, "definition", "medium",
         "What components form an individual field line within an HTTP header or trailer section?",
         "Field sections are composed of field lines, each featuring a field name identifying the field and an associated field line value."),
        ("http-09", "6.4", 0, "definition", "easy",
         "What constitutes message content within the HTTP messaging model?",
         "HTTP message content is a stream of octets delivered following the header section that conveys a complete or partial representation."),

        # 3 Procedural
        ("http-10", "9.2.3", 0, "procedural", "medium",
         "What explicit permissions must accompany an HTTP method for its response to be cached?",
         "For a cache to store and reuse an HTTP response, the associated method must explicitly allow caching and outline valid reuse conditions."),
        ("http-11", "12", 0, "procedural", "medium",
         "How does an origin server utilize content negotiation to deliver tailored representations?",
         "Content negotiation enables origin servers to select the most appropriate representation format for a given message among alternative formats."),
        ("http-12", "15.2.1", 0, "procedural", "easy",
         "What does receiving a 100 Continue status code instruct an HTTP client to do?",
         "The 100 Continue status code indicates the server has accepted the initial request headers and instructs the client to proceed with transmitting the payload."),
    ]

    for qid, sec_num, p_idx, q_type, q_diff, prompt, ref_ans in http_specs:
        sec_title, para = get_exact_passage("http", sec_num, p_idx)
        q = Question(
            id=qid,
            question=prompt,
            doc_id="http",
            section=sec_title,
            evidence=[EvidenceItem(doc_id="http", quote=para)],
            reference_answer=ref_ans,
            type=q_type,
            difficulty=q_diff,
            verified=False,
            drafted_by="llm",
        )
        questions.append(q)

    # 2 Multi-hop HTTP
    sec_h13a, p_h13a = get_exact_passage("http", "7.6", 0)
    sec_h13b, p_h13b = get_exact_passage("http", "15.5.13", 0)
    questions.append(
        Question(
            id="http-13",
            question="How do intermediaries process conditional request failures along proxy chains?",
            doc_id="http",
            section="7.6. Message Forwarding and Preconditions",
            evidence=[
                EvidenceItem(doc_id="http", quote=p_h13a),
                EvidenceItem(doc_id="http", quote=p_h13b),
            ],
            reference_answer="Intermediaries serve varied forwarding roles across request chains, relaying 412 Precondition Failed responses when evaluated header preconditions test false on the server.",
            type="multi-hop",
            difficulty="hard",
            verified=False,
            drafted_by="llm",
        )
    )

    sec_h14a, p_h14a = get_exact_passage("http", "3.8", 0)
    sec_h14b, p_h14b = get_exact_passage("http", "9.2.3", 0)
    questions.append(
        Question(
            id="http-14",
            question="What governing principles dictate how web caches store and serve responses across methods?",
            doc_id="http",
            section="3.8. Caching and Method Semantics",
            evidence=[
                EvidenceItem(doc_id="http", quote=p_h14a),
                EvidenceItem(doc_id="http", quote=p_h14b),
            ],
            reference_answer="Caches store past response messages locally to optimize latency, provided the associated request method explicitly authorizes caching under defined conditions.",
            type="multi-hop",
            difficulty="hard",
            verified=False,
            drafted_by="llm",
        )
    )

    return questions


def main():
    print("=" * 80)
    print("GENERATING & VALIDATING EXACT EVALUATION DATASET")
    print("=" * 80)

    questions = assemble_all_questions()
    print(f"Total questions generated: {len(questions)}")

    validator = EvidenceValidator()
    issues = validator.validate_all(questions)

    if issues:
        print(f"\n[FAIL] Found {len(issues)} validation issues:")
        for iss in issues:
            print(f"  - {iss}")
        sys.exit(1)

    print("\n[SUCCESS] EvidenceValidator passed with 0 issues!")
    out_path = REPO_ROOT / "data" / "eval" / "questions.json"
    save_questions(questions, out_path)
    print(f"Wrote 56 questions to {out_path}")

    # Counts
    by_doc = {}
    by_type = {}
    by_diff = {}
    for q in questions:
        by_doc[q.doc_id] = by_doc.get(q.doc_id, 0) + 1
        by_type[q.type] = by_type.get(q.type, 0) + 1
        by_diff[q.difficulty] = by_diff.get(q.difficulty, 0) + 1

    print("\n--- Summary Breakdown ---")
    print(f"By Document: {dict(sorted(by_doc.items()))}")
    print(f"By Type:     {dict(sorted(by_type.items()))}")
    print(f"By Difficulty: {dict(sorted(by_diff.items()))}")


if __name__ == "__main__":
    main()
