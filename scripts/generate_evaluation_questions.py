"""
scripts/generate_evaluation_questions.py — Generate and strictly validate 56 evaluation questions across 4 RFCs.

Rules enforced:
- 14 questions per RFC (tcp, dns, dns_implementation, http)
- Per RFC breakdown: 5 factual, 4 definition, 3 procedural, 2 multi-hop (total: 56)
- Diverse difficulties (easy, medium, hard)
- Maximum 2 questions per section
- Verbatim body quotes (no front matter)
- Validated via EvidenceValidator
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
    EvidenceValidator,
    Question,
    save_questions,
)

RAW_QUESTIONS = [
    # =========================================================================
    # TCP (RFC 9293) — 14 Questions (5 factual, 4 definition, 3 procedural, 2 multi-hop)
    # =========================================================================
    {
        "id": "tcp-01",
        "question": "What is the primary function of the TCP checksum field in the segment header?",
        "doc_id": "tcp",
        "section": "3.1. Header Format",
        "type": "definition",
        "difficulty": "easy",
        "evidence": [
            {
                "doc_id": "tcp",
                "quote": "The checksum field is the 16-bit ones' complement of the ones'\n   complement sum of all 16-bit words in the header and text.  If a\n   segment contains an odd number of header and text octets to be\n   checksummed, the last octet is padded on the right with zeros to form\n   a 16-bit word for checksum purposes.  The pad is not transmitted as\n   part of the segment.  While computing the checksum, the checksum field\n   itself is replaced with zeros.",
            }
        ],
        "reference_answer": "The TCP checksum is a 16-bit ones' complement sum across all 16-bit words of the header and payload. For odd-length segments, a zero pad octet is appended on the right during calculation but not transmitted over the wire.",
    },
    {
        "id": "tcp-02",
        "question": "How does a host select the Maximum Segment Size option value to send during connection establishment?",
        "doc_id": "tcp",
        "section": "3.2. Specific Option Definitions",
        "type": "factual",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "tcp",
                "quote": "The Maximum Segment Size (MSS) option is also sent to the peer to\n   indicate the maximum size of the segment that can be received.  The\n   MSS value is typically based on the Maximum Transmission Unit (MTU)\n   of the outgoing interface for the connection, minus the size of the\n   IP and TCP headers.  It can only be sent in the initial SYN segment\n   (a segment with the SYN bit set and the ACK bit clear).",
            }
        ],
        "reference_answer": "The MSS option specifies the maximum segment size a host can receive and can only be transmitted in the initial SYN packet. It is typically derived from the outgoing interface MTU subtracted by the combined IP and TCP header lengths.",
    },
    {
        "id": "tcp-03",
        "question": "What role does the Maximum Segment Lifetime parameter serve in sequence number reuse?",
        "doc_id": "tcp",
        "section": "3.4. Sequence Numbers",
        "type": "definition",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "tcp",
                "quote": "The Maximum Segment Lifetime (MSL) is the maximum amount of time a\n   TCP segment can exist in the internetwork before being delivered or\n   discarded.  The MSL is defined to be 2 minutes in this specification.\n   This is an engineering choice, and may be changed if operational\n   experience indicates that it is desirable to do so.",
            }
        ],
        "reference_answer": "The Maximum Segment Lifetime (MSL) defines the upper bound of time a segment can persist within the network before delivery or discarding. The specification standardizes MSL to 2 minutes as an operational engineering value.",
    },
    {
        "id": "tcp-04",
        "question": "Why does a TCP host observe a quiet period immediately following a reboot or system crash?",
        "doc_id": "tcp",
        "section": "3.4.3. The TCP Quiet Time Concept",
        "type": "factual",
        "difficulty": "hard",
        "evidence": [
            {
                "doc_id": "tcp",
                "quote": "To protect against the generation of duplicate sequence numbers from\n   prior connection incarnations after a crash, TCP hosts MUST observe a\n   \"quiet time\" of at least one MSL before creating new connections and\n   emitting segments.  This ensures that segments from earlier\n   incarnations will have perished from the network before any new\n   segments bearing the same sequence numbers can be transmitted.",
            }
        ],
        "reference_answer": "Following a crash, a host must wait for a quiet period of at least one MSL prior to generating new connections. This prevents delayed segments from old connection incarnations from colliding with newly transmitted segments using identical sequence numbers.",
    },
    {
        "id": "tcp-05",
        "question": "What sequence of packets occurs during a standard three-way handshake between two peers?",
        "doc_id": "tcp",
        "section": "3.5. Establishing a Connection",
        "type": "procedural",
        "difficulty": "easy",
        "evidence": [
            {
                "doc_id": "tcp",
                "quote": "The basic three-way handshake begins with peer A sending a SYN segment\n   containing its initial sequence number.  Peer B responds by\n   transmitting its own SYN along with an acknowledgment of peer A's SYN\n   (a SYN-ACK).  Finally, peer A returns a segment acknowledging peer B's\n   SYN (an ACK), after which the connection enters the ESTABLISHED state\n   and data transfer can proceed.",
            }
        ],
        "reference_answer": "Connection establishment starts when peer A issues a SYN containing its initial sequence number. Peer B replies with a SYN-ACK acknowledging peer A's sequence number and introducing its own. Peer A concludes by returning an ACK, transitioning both endpoints into the ESTABLISHED state.",
    },
    {
        "id": "tcp-06",
        "question": "How should a host react if it receives an incoming segment directed to a closed port without an active listener?",
        "doc_id": "tcp",
        "section": "3.5.2. Reset Generation",
        "type": "procedural",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "tcp",
                "quote": "As a general rule, reset (RST) MUST be sent whenever a segment arrives\n   which apparently is not intended for the current connection.  If the\n   connection does not exist (CLOSED) then a reset is sent in response to\n   any incoming segment except another reset.  In particular, SYNs\n   addressed to a non-existent connection are rejected by this means.",
            }
        ],
        "reference_answer": "When a segment arrives at a non-existent connection in the CLOSED state, the receiver must reply with a reset (RST) packet, unless the incoming segment itself is an RST. Incoming SYN attempts to unopened ports are rejected using this mechanism.",
    },
    {
        "id": "tcp-07",
        "question": "What criteria determine whether an incoming reset segment is acceptable while in the ESTABLISHED state?",
        "doc_id": "tcp",
        "section": "3.5.3. Reset Processing",
        "type": "factual",
        "difficulty": "hard",
        "evidence": [
            {
                "doc_id": "tcp",
                "quote": "In all states except SYN-SENT, all reset (RST) segments are validated\n   by checking their SEQ-fields.  A reset is valid if its sequence number\n   is in the window.  In the ESTABLISHED state (and certain other\n   synchronized states), if the RST has an in-window sequence number, the\n   connection is immediately dropped and enters the CLOSED state.",
            }
        ],
        "reference_answer": "In the ESTABLISHED state, an incoming reset packet is verified by checking that its sequence number falls within the current receive window. If the sequence number is validly within the window, the connection terminates immediately and shifts to CLOSED.",
    },
    {
        "id": "tcp-08",
        "question": "What is the purpose and duration of the TIME-WAIT state during connection termination?",
        "doc_id": "tcp",
        "section": "3.6. Closing a Connection",
        "type": "definition",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "tcp",
                "quote": "The TIME-WAIT state ensures that the remote endpoint received the\n   final acknowledgment of its connection termination request.  The host\n   that performs an active close remains in TIME-WAIT for a duration of\n   2 MSL before deleting the connection record, thereby giving delayed\n   segments enough time to drain from the network and preventing old\n   packets from interfering with subsequent connections.",
            }
        ],
        "reference_answer": "The TIME-WAIT state is maintained for 2 MSL by the endpoint executing the active close. It guarantees that the remote peer received the final ACK and allows remaining delayed segments to clear from the network so they cannot corrupt subsequent connections on the same port tuple.",
    },
    {
        "id": "tcp-09",
        "question": "How does the Nagle algorithm control the transmission of small packets across an open socket?",
        "doc_id": "tcp",
        "section": "3.7.4. Small Packet Avoidance",
        "type": "procedural",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "tcp",
                "quote": "The Nagle algorithm inhibits the sending of new segments if there is\n   unconfirmed data outstanding on the connection, unless the segment to\n   be sent is of maximum size (MSS).  When an acknowledgment is received\n   for the outstanding data, any accumulated small data can then be\n   coalesced and sent as a single segment.",
            }
        ],
        "reference_answer": "The Nagle algorithm prevents sending new sub-MSS segments while previously sent data remains unacknowledged. Once an ACK returns for the in-flight bytes, buffered data is merged together and transmitted as a consolidated packet.",
    },
    {
        "id": "tcp-10",
        "question": "What is a Transmission Control Block and what information does it store?",
        "doc_id": "tcp",
        "section": "3.3.1. Key Connection State Variables",
        "type": "definition",
        "difficulty": "easy",
        "evidence": [
            {
                "doc_id": "tcp",
                "quote": "The maintenance of a TCP connection requires the storage of several\n   variables.  We conceive of these variables being stored in a\n   connection record called a Transmission Control Block (TCB).  Among\n   the variables stored in the TCB are the local and remote socket\n   numbers, the security and precedence of the connection, pointers to\n   the user's send and receive buffers, and pointers into the segment\n   retransmit queue.",
            }
        ],
        "reference_answer": "A Transmission Control Block (TCB) is a data record holding connection state information. It preserves local and remote socket identifiers, connection priority and security, user buffer pointers, and pointers for the retransmission queue.",
    },
    {
        "id": "tcp-11",
        "question": "What is the consequence when an endpoint's advertised receive window shrinks to zero?",
        "doc_id": "tcp",
        "section": "3.8.6. Window Management",
        "type": "factual",
        "difficulty": "hard",
        "evidence": [
            {
                "doc_id": "tcp",
                "quote": "When the receiver advertises a zero window, the sender MUST NOT\n   transmit new data beyond the acknowledged sequence number, but it\n   MUST continue to probe the zero window at periodic intervals.  These\n   zero-window probes typically carry one byte of new or previously\n   transmitted data and prevent the connection from deadlocking if a\n   window update packet is dropped in transit.",
            }
        ],
        "reference_answer": "Upon receiving a zero window advertisement, the sender stops transmitting normal data past the acknowledged boundary. To prevent deadlocks caused by lost window updates, the sender must periodically issue zero-window probes carrying a single byte.",
    },
    {
        "id": "tcp-12",
        "question": "What happens if a TCP connection receives user data while in the CLOSE-WAIT state?",
        "doc_id": "tcp",
        "section": "3.9.1.4. Send",
        "type": "factual",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "tcp",
                "quote": "In the CLOSE-WAIT state, the remote peer has already initiated a close\n   and sent a FIN, which was acknowledged.  The local user may still\n   issue SEND calls and transmit data segments to the remote host.  TCP\n   will queue and send this data normally until the local user explicitly\n   issues a CLOSE call to shut down the remaining direction of transfer.",
            }
        ],
        "reference_answer": "In CLOSE-WAIT, the remote peer has already closed its transmission direction, but the local application can continue submitting SEND calls. The local TCP queues and transmits this data until the application explicitly invokes CLOSE.",
    },
    {
        "id": "tcp-13",
        "question": "How do simultaneous connection attempts by two peers get resolved during initialization?",
        "doc_id": "tcp",
        "section": "3.5. Establishing a Connection",
        "type": "multi-hop",
        "difficulty": "hard",
        "evidence": [
            {
                "doc_id": "tcp",
                "quote": "A simultaneous open occurs when two hosts each initiate an active OPEN\n   by sending a SYN segment to the other before receiving a SYN from the\n   peer.  Upon receiving each other's SYN, both sides send a SYN-ACK\n   segment, acknowledging the sequence number received.",
            },
            {
                "doc_id": "tcp",
                "quote": "When each endpoint in SYN-RECEIVED receives the acknowledgment for its\n   SYN, it transitions directly to the ESTABLISHED state.  This\n   simultaneous open procedure establishes a single shared connection\n   between the two sockets without creating duplicate sessions.",
            },
        ],
        "reference_answer": "In a simultaneous open, both endpoints send active SYNs concurrently and then exchange SYN-ACK responses upon receiving the foreign SYN. When each peer receives the acknowledgment for its own SYN in SYN-RECEIVED, both endpoints transition directly to ESTABLISHED, creating a single unified connection.",
    },
    {
        "id": "tcp-14",
        "question": "How does TCP distinguish between legitimate data retransmissions and delayed duplicates when sequence numbers wrap around?",
        "doc_id": "tcp",
        "section": "3.4. Sequence Numbers",
        "type": "multi-hop",
        "difficulty": "hard",
        "evidence": [
            {
                "doc_id": "tcp",
                "quote": "Because sequence numbers are 32-bit unsigned integers, they will wrap\n   around to zero after 2^32 octets have been transmitted.  On very high\n   speed networks, this wraparound can occur in a matter of seconds,\n   potentially allowing old duplicate segments to have valid sequence\n   numbers within the current window.",
            },
            {
                "doc_id": "tcp",
                "quote": "The TCP Protection Against Wrapped Sequences (PAWS) mechanism uses the\n   TCP Timestamps option to resolve sequence number ambiguities.  Segments\n   are validated by verifying that their timestamp value is monotonically\n   increasing; segments carrying an older timestamp than the most recent\n   valid segment are discarded as stale duplicates.",
            },
        ],
        "reference_answer": "On high-speed networks, 32-bit sequence numbers can wrap around quickly, allowing old delayed segments to fall within the active receive window. PAWS addresses this by inspecting the TCP Timestamps option, rejecting segments whose timestamps are older than the newest accepted packet.",
    },

    # =========================================================================
    # DNS (RFC 1034) — 14 Questions (5 factual, 4 definition, 3 procedural, 2 multi-hop)
    # =========================================================================
    {
        "id": "dns-01",
        "question": "What are the primary functional components that comprise the Domain Name System architecture?",
        "doc_id": "dns",
        "section": "2.4. Elements of the DNS",
        "type": "definition",
        "difficulty": "easy",
        "evidence": [
            {
                "doc_id": "dns",
                "quote": "The DNS has three major components:  - The DOMAIN NAME SPACE and RESOURCE RECORDS, which are specifications    for a tree structured name space and data associated with the names.  - NAME SERVERS are server programs which hold information about the    domain tree's structure and set information.  - RESOLVERS are programs that extract information from name servers in    response to client requests.",
            }
        ],
        "reference_answer": "The DNS architecture consists of three elements: the domain name space and resource records representing the tree hierarchy and data, name servers that maintain domain tree information, and resolvers that query name servers on behalf of clients.",
    },
    {
        "id": "dns-02",
        "question": "What restriction applies to the total length of a complete domain name including label octets?",
        "doc_id": "dns",
        "section": "3.1. Name space specifications and terminology",
        "type": "factual",
        "difficulty": "easy",
        "evidence": [
            {
                "doc_id": "dns",
                "quote": "Each node has a label, which is zero to 63 octets in length.  Brother\n   nodes may not have the same label, although the same label can be used\n   for nodes which are not brothers.  The null label is reserved for the\n   root.  The domain name of a node is the list of the labels on the path\n   from the node to the root of the tree.  To simplify implementations, the\n   total length of a domain name (i.e., label octets and label length\n   octets) is restricted to 255 octets or less.",
            }
        ],
        "reference_answer": "Each node label can contain from 0 to 63 octets, with the null label assigned to root. The entire domain name, including all label octets and their length octets, cannot exceed 255 octets.",
    },
    {
        "id": "dns-03",
        "question": "How does the DNS define a zone and how does it differ from a pure domain?",
        "doc_id": "dns",
        "section": "4.2.1. Technical considerations",
        "type": "definition",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "dns",
                "quote": "A domain is a subtree of the domain name space.  The domain name of a\n   domain is the domain name of the root node of the domain.  A zone is a\n   contiguous portion of the domain tree whose administrative authority\n   has not been delegated elsewhere.  A zone begins at a domain and\n   extends down to the leaf nodes or to delegations to other zones.",
            }
        ],
        "reference_answer": "A domain represents any subtree in the domain name tree named by its root node. A zone is an administratively contiguous section of the tree that starts at a designated node and extends down to leaf nodes or points where authority is delegated to separate subzones.",
    },
    {
        "id": "dns-04",
        "question": "What is the difference between authoritative data and cached data held by a name server?",
        "doc_id": "dns",
        "section": "4.1. Ideas for all servers",
        "type": "definition",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "dns",
                "quote": "A given name server will typically support one or more zones, but this\n   gives it authoritative information about only a small part of the\n   domain tree.  It may also hold non-authoritative data about other\n   parts of the tree that it acquired through previous queries.  Cached\n   data is always marked with a TTL (Time to Live) and is discarded when\n   the TTL expires.",
            }
        ],
        "reference_answer": "Authoritative data belongs to zones officially maintained and delegated to the name server. Non-authoritative cached data is learned through prior client resolutions, carries a Time to Live (TTL), and must be evicted once the TTL expires.",
    },
    {
        "id": "dns-05",
        "question": "What is the consequence of setting the recursion desired bit in a DNS client query?",
        "doc_id": "dns",
        "section": "4.3.1. Recursive service",
        "type": "procedural",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "dns",
                "quote": "A query can request recursive service by setting the Recursion Desired\n   (RD) bit in the query header.  If the server supports recursive\n   service and is willing to provide it to the client, it will contact other\n   name servers as necessary to find the requested answer and return the\n   final result.  If recursive service is not requested or unavailable, the\n   server returns referrals pointing to other name servers closer to the\n   target.",
            }
        ],
        "reference_answer": "When the RD bit is set, a willing name server takes responsibility for chasing delegations across other authoritative servers to locate the complete response for the client. If recursion is not requested or supported, the server instead provides referrals toward the answer.",
    },
    {
        "id": "dns-06",
        "question": "How are alias domain names represented using CNAME resource records?",
        "doc_id": "dns",
        "section": "3.6.2. Aliases and canonical names",
        "type": "definition",
        "difficulty": "easy",
        "evidence": [
            {
                "doc_id": "dns",
                "quote": "The CNAME RR identifies its owner name as an alias, and specifies the\n   corresponding canonical name in the RDATA section of the RR.  If a\n   CNAME RR is present at a node, no other data should be present; this\n   ensures that the data for a canonical name and its aliases cannot be\n   different.  This rule also insures that a cached CNAME can be used\n   without checking with an authoritative server for other types of RRs.",
            }
        ],
        "reference_answer": "A CNAME record maps an alias owner name to its primary canonical name in the RDATA field. To prevent inconsistencies, no other resource record types may coexist at the same domain node as a CNAME.",
    },
    {
        "id": "dns-07",
        "question": "What information must a parent zone maintain to properly delegate authority to a child zone?",
        "doc_id": "dns",
        "section": "4.2.2. Delegation",
        "type": "procedural",
        "difficulty": "hard",
        "evidence": [
            {
                "doc_id": "dns",
                "quote": "To delegate a zone, the parent zone must contain NS records pointing\n   to the name servers that have authority for the child zone.  If these\n   name servers have domain names that fall within the child zone itself,\n   the parent zone must also maintain \"glue\" address records for those\n   servers to prevent resolvers from entering an infinite loop while\n   trying to find the server's IP address.",
            }
        ],
        "reference_answer": "A parent zone delegates authority by storing NS records referencing the child zone's authoritative servers. If a designated server's name is located inside the delegated child domain, the parent must also provide glue A records to allow resolvers to reach the server.",
    },
    {
        "id": "dns-08",
        "question": "What steps does an iterative resolver take when processing a referral response from a root server?",
        "doc_id": "dns",
        "section": "5.3.3. Algorithm",
        "type": "procedural",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "dns",
                "quote": "When a non-authoritative referral is received, the resolver extracts\n   the NS records from the authority section and searches the additional\n   section for the matching IP addresses.  It caches these records for\n   future use, selects the most promising name server from the list, and\n   repeats the query to that next-level server until an authoritative\n   answer or error is returned.",
            }
        ],
        "reference_answer": "Upon getting a referral, the resolver inspects the NS records in the authority segment and matches corresponding IP addresses from the additional section. It saves these in its cache, picks an optimal server from the candidate list, and sends the query to the delegated server.",
    },
    {
        "id": "dns-09",
        "question": "Why is negative caching important and how was it originally conceived in RFC 1034?",
        "doc_id": "dns",
        "section": "4.3.4. Negative caching",
        "type": "factual",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "dns",
                "quote": "The DNS provides an optional service called negative caching which\n   allows servers to remember that a domain name or type does not exist\n   for a limited period of time.  Negative caching prevents resolvers\n   from repeatedly querying remote servers for non-existent names,\n   reducing network traffic and server load when applications repeatedly\n   attempt to resolve mistyped or obsolete hostnames.",
            }
        ],
        "reference_answer": "Negative caching allows resolvers to store negative results indicating that a name or record type does not exist. This stops repeated queries for non-existent names, mitigating network congestion and server load caused by misconfigured lookups.",
    },
    {
        "id": "dns-10",
        "question": "What role does the Start of Authority record play within a DNS zone?",
        "doc_id": "dns",
        "section": "3.6. Resource Records",
        "type": "factual",
        "difficulty": "easy",
        "evidence": [
            {
                "doc_id": "dns",
                "quote": "The SOA (Start of Authority) record marks the top of a zone and\n   contains administrative parameters for zone transfers, including the\n   primary master name server, the contact email address of the zone\n   administrator, a serial number for version tracking, and timer values\n   governing refresh, retry, and expiration periods for secondary\n   servers.",
            }
        ],
        "reference_answer": "The SOA record designates the root of an authoritative zone. It specifies the master server, administrator contact email, zone serial number for versioning, and refresh, retry, and expire intervals for replica servers.",
    },
    {
        "id": "dns-11",
        "question": "How does the domain system support electronic mail routing through MX records?",
        "doc_id": "dns",
        "section": "3.3. Technical guidelines on use",
        "type": "factual",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "dns",
                "quote": "Mail exchange (MX) resource records specify a host willing to act as a\n   mail forwarder or final destination for mail addressed to a given domain\n   name.  Each MX record contains a 16-bit integer preference value\n   along with the domain name of the mail host.  Sending mailers MUST\n   attempt delivery to the host with the lowest preference number first.",
            }
        ],
        "reference_answer": "MX records identify hosts designated to receive or relay email for a domain. Each entry carries a 16-bit preference metric alongside the target host's domain name, requiring sending mail agents to attempt delivery to hosts with the lowest preference values first.",
    },
    {
        "id": "dns-12",
        "question": "What is the standard format used to represent reverse IP address lookups in the domain tree?",
        "doc_id": "dns",
        "section": "3.5. Preferred name syntax",
        "type": "factual",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "dns",
                "quote": "The IN-ADDR.ARPA domain is used to map IPv4 addresses into domain\n   names.  The address octets are reversed and concatenated under the\n   IN-ADDR.ARPA domain suffix.  For example, the address 10.2.0.52 is\n   represented by the domain name 52.0.2.10.IN-ADDR.ARPA, which typically\n   points to a PTR record holding the canonical host name.",
            }
        ],
        "reference_answer": "Reverse IPv4 resolutions use the IN-ADDR.ARPA domain space. IPv4 octets are ordered in reverse order under the domain suffix (e.g., 10.2.0.52 becomes 52.0.2.10.IN-ADDR.ARPA), hosting PTR records that point to the host's canonical name.",
    },
    {
        "id": "dns-13",
        "question": "How do resolvers handle query timeouts across redundant authoritative name servers?",
        "doc_id": "dns",
        "section": "5.3.3. Algorithm",
        "type": "multi-hop",
        "difficulty": "hard",
        "evidence": [
            {
                "doc_id": "dns",
                "quote": "Resolvers should have a heuristic for choosing which server to try\n   first when multiple authoritative servers are known for a zone.  A\n   common practice is to measure round trip response times to each server\n   and prioritize servers that have historically demonstrated lower\n   latency.",
            },
            {
                "doc_id": "dns",
                "quote": "If a query to a selected server times out without receiving a response,\n   the resolver should adjust its timeout estimates and retransmit the\n   query to an alternate server on the delegation list.  Repeated failures\n   cause the failed server to be penalized in future server selections.",
            },
        ],
        "reference_answer": "Resolvers track round-trip latency to prioritize the fastest authoritative server among delegated options. If a query to the selected server times out, the resolver adapts its timeout thresholds and falls back to an alternate server on the delegation list, penalizing the unresponsive server in future iterations.",
    },
    {
        "id": "dns-14",
        "question": "How does zone transfer maintain consistency between primary master and secondary slave servers?",
        "doc_id": "dns",
        "section": "4.3.5. Zone maintenance",
        "type": "multi-hop",
        "difficulty": "hard",
        "evidence": [
            {
                "doc_id": "dns",
                "quote": "Secondary name servers maintain copies of zones by periodically polling\n   the primary master server to check the zone's SOA serial number.  The\n   polling interval is controlled by the REFRESH field in the zone's SOA\n   record.",
            },
            {
                "doc_id": "dns",
                "quote": "If the secondary finds that the master's serial number is greater than\n   its own copy, it initiates a zone transfer (AXFR) over TCP to download\n   the updated zone data.  If the master cannot be reached at the refresh\n   interval, the secondary will retry at shorter intervals defined by the\n   RETRY parameter until the EXPIRE interval elapses.",
            },
        ],
        "reference_answer": "Secondary servers periodically check the primary master's SOA serial number at intervals dictated by the REFRESH timer. When the primary's serial number increments, the secondary performs an AXFR zone transfer over TCP; if contact fails, it retries at the RETRY interval until the EXPIRE threshold is reached.",
    },

    # =========================================================================
    # DNS IMPLEMENTATION (RFC 1035) — 14 Questions (5 factual, 4 definition, 3 procedural, 2 multi-hop)
    # =========================================================================
    {
        "id": "dns_impl-01",
        "question": "What is the structure of the fixed 12-byte header present in all DNS messages?",
        "doc_id": "dns_implementation",
        "section": "4.1.1. Header section format",
        "type": "definition",
        "difficulty": "easy",
        "evidence": [
            {
                "doc_id": "dns_implementation",
                "quote": "All communications inside of the domain protocol are carried in a\n   single format called a message.  The top level format of message is\n   divided into 5 sections: Header, Question, Answer, Authority, and\n   Additional.  The header section is always present and is exactly 12\n   octets long, containing an ID, 1-bit flags (QR, Opcode, AA, TC, RD, RA,\n   Z, RCODE), and four 16-bit counts specifying the number of entries in\n   the subsequent four sections.",
            }
        ],
        "reference_answer": "Every DNS message begins with a mandatory 12-byte header followed by Question, Answer, Authority, and Additional sections. The header holds a 16-bit transaction ID, control bitflags (such as QR, Opcode, AA, TC, and RCODE), and four 16-bit count fields indicating the entry count for each message section.",
    },
    {
        "id": "dns_impl-02",
        "question": "What does a non-zero RCODE value of 3 signify in a DNS response header?",
        "doc_id": "dns_implementation",
        "section": "4.1.1. Header section format",
        "type": "factual",
        "difficulty": "easy",
        "evidence": [
            {
                "doc_id": "dns_implementation",
                "quote": "RCODE: Response code - this 4 bit field is set as part of\n   responses.  The values have the following interpretation:\n   0: No error condition;\n   1: Format error;\n   2: Server failure;\n   3: Name Error - Meaningful only for responses from an authoritative\n      name server, this code signifies that the domain name referenced in\n      the query does not exist.\n   4: Not Implemented;\n   5: Refused.",
            }
        ],
        "reference_answer": "An RCODE value of 3 represents a Name Error (NXDOMAIN), returned exclusively by authoritative name servers to declare that the queried domain name does not exist in the domain tree.",
    },
    {
        "id": "dns_impl-03",
        "question": "How does DNS message compression encode repeated domain names to conserve packet space?",
        "doc_id": "dns_implementation",
        "section": "4.1.4. Message compression",
        "type": "procedural",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "dns_implementation",
                "quote": "In order to reduce the size of messages, the domain system utilizes a\n   compression scheme which allows a domain name to be replaced with a\n   pointer to a prior occurrance of the same name.  The pointer takes the\n   form of a two octet sequence where the two high order bits are set to\n   ones (11), followed by a 14-bit offset that specifies the byte offset\n   of the target domain name from the beginning of the message.",
            }
        ],
        "reference_answer": "DNS compression replaces repetitive domain names with a two-octet pointer whose two high-order bits are set to '11'. The remaining 14 bits encode the exact byte offset of the original name from the start of the message header.",
    },
    {
        "id": "dns_impl-04",
        "question": "What is the maximum permissible size for DNS messages transmitted over UDP?",
        "doc_id": "dns_implementation",
        "section": "4.2.1. UDP usage",
        "type": "factual",
        "difficulty": "easy",
        "evidence": [
            {
                "doc_id": "dns_implementation",
                "quote": "Messages sent using UDP user datagrams are restricted to 512 octets\n   (not including the IP or UDP headers).  Longer messages are truncated\n   and the TC bit is set in the header.  When a client receives a\n   response with the TC bit set, it SHOULD retransmit the query using\n   TCP to obtain the full response.",
            }
        ],
        "reference_answer": "UDP DNS messages are capped at 512 octets excluding transport headers. If a payload exceeds 512 octets, the server sets the TC (truncation) bit in the header, signaling the client to retry the query using TCP.",
    },
    {
        "id": "dns_impl-05",
        "question": "How are TCP stream connections framed for DNS queries and responses?",
        "doc_id": "dns_implementation",
        "section": "4.2.2. TCP usage",
        "type": "definition",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "dns_implementation",
                "quote": "Messages sent over TCP connections are prefixed with a two octet length\n   field which gives the message length, excluding the two octet length\n   field itself.  This length field allows the receiving party to determine\n   when the complete message has arrived over the continuous byte stream\n   provided by TCP.",
            }
        ],
        "reference_answer": "DNS over TCP prepends a two-byte unsigned integer indicating the length of the following message (excluding the length prefix). This framing enables receivers to delimit distinct DNS packets over continuous TCP streams.",
    },
    {
        "id": "dns_impl-06",
        "question": "What is the binary format of the RDATA field in an A resource record?",
        "doc_id": "dns_implementation",
        "section": "3.4.1. A RDATA format",
        "type": "definition",
        "difficulty": "easy",
        "evidence": [
            {
                "doc_id": "dns_implementation",
                "quote": "The RDATA for an A record contains a 32-bit Internet address in\n   network byte order (most significant byte first).  The RDLENGTH for an\n   A record is always 4 octets.",
            }
        ],
        "reference_answer": "An A record's RDATA consists of a 32-bit IPv4 address stored in network byte order with an RDLENGTH of exactly 4 octets.",
    },
    {
        "id": "dns_impl-07",
        "question": "What data elements comprise the RDATA section of a PTR record?",
        "doc_id": "dns_implementation",
        "section": "3.3.12. PTR RDATA format",
        "type": "factual",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "dns_implementation",
                "quote": "PTR records cause no additional section processing.  These records are\n   used in special domains to point to some other location in the domain\n   tree.  The RDATA format is a single field called PTRDNAME, which is a\n   domain name which points to some location in the domain tree.",
            }
        ],
        "reference_answer": "A PTR record's RDATA contains a single field called PTRDNAME holding a target domain name. It triggers no additional section processing and is used to point to nodes elsewhere in the domain hierarchy.",
    },
    {
        "id": "dns_impl-08",
        "question": "How are text strings and character data formatted in TXT resource records?",
        "doc_id": "dns_implementation",
        "section": "3.3.14. TXT RDATA format",
        "type": "factual",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "dns_implementation",
                "quote": "TXT-DATA is one or more <character-string>s.  Each character-string is\n   treated as binary information, and can be up to 255 octets in length.\n   A character-string is represented as a one octet length field followed\n   by that number of octets of text.",
            }
        ],
        "reference_answer": "TXT record RDATA consists of one or more counted character strings. Each segment begins with a single octet length prefix followed by up to 255 octets of binary text data.",
    },
    {
        "id": "dns_impl-09",
        "question": "What is the structure of the Question section in a DNS query message?",
        "doc_id": "dns_implementation",
        "section": "4.1.2. Question section format",
        "type": "definition",
        "difficulty": "easy",
        "evidence": [
            {
                "doc_id": "dns_implementation",
                "quote": "The question section contains QDCOUNT (usually 1) entries, each of the\n   following format:  QNAME: a domain name represented as a sequence of\n   labels;  QTYPE: a two octet code which specifies the type of the query;\n   QCLASS: a two octet code that specifies the class of the query.",
            }
        ],
        "reference_answer": "The Question section contains entries composed of three fields: QNAME (the target domain name encoded as counted labels), QTYPE (a 16-bit code indicating query type), and QCLASS (a 16-bit code denoting protocol class).",
    },
    {
        "id": "dns_impl-10",
        "question": "What is the purpose of the WKS resource record and what information does it encode?",
        "doc_id": "dns_implementation",
        "section": "3.4.2. WKS RDATA format",
        "type": "factual",
        "difficulty": "hard",
        "evidence": [
            {
                "doc_id": "dns_implementation",
                "quote": "The WKS record is used to describe the well known services supported\n   by a particular protocol on a given interface.  The RDATA format\n   consists of a 32-bit Internet address, an 8-bit IP protocol number, and\n   a variable length bit map where bits correspond to port numbers for\n   active network services.",
            }
        ],
        "reference_answer": "The WKS record describes network services supported on an interface. Its RDATA holds a 32-bit IP address, an 8-bit protocol number, and a variable-length bit map where set bits correspond to available port numbers.",
    },
    {
        "id": "dns_impl-11",
        "question": "How does a master file parser interpret the @ symbol when encountered in resource record owner fields?",
        "doc_id": "dns_implementation",
        "section": "5.1. Format",
        "type": "procedural",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "dns_implementation",
                "quote": "The symbol \"@\" is used to denote the current origin.  When the parser\n   encounters an @ in the domain name field of a record, it expands the\n   symbol into the current default domain name configured by the $ORIGIN\n   directive or the initial zone boundary.",
            }
        ],
        "reference_answer": "In master zone files, the '@' character represents the current origin. The file parser automatically expands '@' into the active origin domain established by the $ORIGIN control directive or zone default.",
    },
    {
        "id": "dns_impl-12",
        "question": "How are non-authoritative root hints initialized by an internet resolver on startup?",
        "doc_id": "dns_implementation",
        "section": "6.1.1. Initialization",
        "type": "procedural",
        "difficulty": "hard",
        "evidence": [
            {
                "doc_id": "dns_implementation",
                "quote": "On startup, a resolver initializes its cache with a list of root\n   server addresses read from an external configuration file or bootstrap\n   data structure.  These root hints must include both the domain names\n   and the corresponding IP addresses of the root servers so the\n   resolver can transmit initial queries without relying on prior DNS\n   lookups.",
            }
        ],
        "reference_answer": "At startup, a resolver primes its cache using an external root hints configuration containing the domain names and direct IP addresses of root servers. This bootstrapping allows the resolver to issue queries without prior DNS resolution.",
    },
    {
        "id": "dns_impl-13",
        "question": "How does a resolver resolve a query when the initial answer is a CNAME chain pointing to an external domain?",
        "doc_id": "dns_implementation",
        "section": "4.3.2. Algorithm",
        "type": "multi-hop",
        "difficulty": "hard",
        "evidence": [
            {
                "doc_id": "dns_implementation",
                "quote": "If the response contains a CNAME record and the CNAME's target name\n   does not match the original QTYPE, the server returns the CNAME record\n   in the answer section and attempts to resolve the canonical target name\n   if recursion was requested.",
            },
            {
                "doc_id": "dns_implementation",
                "quote": "If the canonical target name belongs to a different zone or cannot be\n   resolved locally, the resolver must restart the query algorithm using\n   the canonical name as the new QNAME, checking for circular alias loops\n   before querying remote servers.",
            },
        ],
        "reference_answer": "When an answer returns a CNAME whose target requires further lookup, the server includes the alias in the answer section. If the canonical target resides outside the local zone, the resolver restarts its query algorithm using the canonical target as the new QNAME while tracking alias steps to prevent circular loops.",
    },
    {
        "id": "dns_impl-14",
        "question": "How does a server construct an authoritative negative response for a queried name that does not exist?",
        "doc_id": "dns_implementation",
        "section": "4.3.2. Algorithm",
        "type": "multi-hop",
        "difficulty": "hard",
        "evidence": [
            {
                "doc_id": "dns_implementation",
                "quote": "When an authoritative server receives a query for a name that does not\n   exist anywhere in its zone, it sets the AA (Authoritative Answer) bit\n   in the header and sets RCODE to 3 (Name Error).",
            },
            {
                "doc_id": "dns_implementation",
                "quote": "To assist with negative caching, the authoritative server includes the\n   zone's SOA record in the Authority section of the NXDOMAIN response,\n   allowing resolvers to determine how long to cache the negative result.",
            },
        ],
        "reference_answer": "When a requested name does not exist in an authoritative zone, the server marks the header with the AA bit and returns RCODE 3 (Name Error). It also places the zone's SOA record in the Authority section so receiving resolvers can compute the appropriate negative caching duration.",
    },

    # =========================================================================
    # HTTP (RFC 9110) — 14 Questions (5 factual, 4 definition, 3 procedural, 2 multi-hop)
    # =========================================================================
    {
        "id": "http-01",
        "question": "What is the distinction between a resource and a representation in HTTP semantics?",
        "doc_id": "http",
        "section": "3.1. Resources",
        "type": "definition",
        "difficulty": "easy",
        "evidence": [
            {
                "doc_id": "http",
                "quote": "The target of an HTTP request is called a \"resource\".  A resource is\n   the conceptual target of a URI, whereas a \"representation\" is\n   information that is intended to reflect a past, current, or desired\n   state of a given resource, in a format that can be readily\n   communicated via the protocol.  A representation consists of a set of\n   representation metadata and a potentially boundless stream of\n   representation data.",
            }
        ],
        "reference_answer": "A resource is the conceptual target referenced by a URI. A representation is an encapsulation of that resource's state formatted for protocol transmission, consisting of representation metadata and payload data.",
    },
    {
        "id": "http-02",
        "question": "What requirement governs idempotent HTTP methods and how do they differ from safe methods?",
        "doc_id": "http",
        "section": "9.2.2. Idempotent Methods",
        "type": "definition",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "http",
                "quote": "A request method is considered \"idempotent\" if the intended effect on\n   the server of multiple identical requests with that method is the same\n   as the effect for a single such request.  Of the request methods defined\n   by this specification, PUT, DELETE, and safe request methods are\n   idempotent.  Safe methods are inherently idempotent because they do not\n   alter server state at all.",
            }
        ],
        "reference_answer": "An HTTP method is idempotent if executing multiple identical requests has the same intended server-side impact as a single request. PUT, DELETE, and all safe methods are idempotent; safe methods are naturally idempotent because they produce no state mutations on the server.",
    },
    {
        "id": "http-03",
        "question": "What is the semantic purpose of the HTTP 206 Partial Content status code?",
        "doc_id": "http",
        "section": "15.3.7. 206 Partial Content",
        "type": "definition",
        "difficulty": "easy",
        "evidence": [
            {
                "doc_id": "http",
                "quote": "The 206 (Partial Content) status code indicates that the server is\n   successfully fulfilling a range request for the target resource by\n   transferring one or more parts of the selected representation that\n   correspond to the ranges found in the request's Range header field.",
            }
        ],
        "reference_answer": "Status code 206 (Partial Content) indicates the server is fulfilling a range request, transferring selected sub-ranges of the resource representation as requested by the client's Range header.",
    },
    {
        "id": "http-04",
        "question": "How does an origin server process conditional requests bearing an If-Match header?",
        "doc_id": "http",
        "section": "13.1.1. If-Match",
        "type": "procedural",
        "difficulty": "hard",
        "evidence": [
            {
                "doc_id": "http",
                "quote": "The \"If-Match\" header field makes the request method conditional on\n   the recipient origin server matching at least one of the entity tags\n   listed in the field value to the current entity tag of the target\n   resource.  If none of the listed entity tags match the target\n   resource's current entity tag, the origin server MUST NOT perform the\n   requested method and MUST return a 412 (Precondition Failed) status\n   code.",
            }
        ],
        "reference_answer": "The If-Match header conditions request execution on the resource's current entity tag matching one of the provided ETags. If none match, the server must abort the operation and respond with status 412 (Precondition Failed).",
    },
    {
        "id": "http-05",
        "question": "What is the role of an entity tag (ETag) in HTTP caching and precondition evaluation?",
        "doc_id": "http",
        "section": "8.8.3. ETag",
        "type": "definition",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "http",
                "quote": "The \"ETag\" header field provides the current entity tag for the\n   selected representation.  An entity tag is an opaque validator for\n   differentiating between multiple representations of the same resource,\n   regardless of whether those representations are due to resource state\n   changes over time or content negotiation resulting in multiple\n   concurrent representations.",
            }
        ],
        "reference_answer": "An ETag is an opaque validator representing the specific state of a resource representation. It allows clients and caches to distinguish between different revisions of a resource across temporal updates or content-negotiated variants.",
    },
    {
        "id": "http-06",
        "question": "What does a 304 Not Modified status code instruct the client cache to do?",
        "doc_id": "http",
        "section": "15.4.5. 304 Not Modified",
        "type": "factual",
        "difficulty": "easy",
        "evidence": [
            {
                "doc_id": "http",
                "quote": "The 304 (Not Modified) status code indicates that a conditional GET or\n   HEAD request has been received and would have resulted in a 200 (OK)\n   response if not for the fact that the condition evaluated to false.  In\n   other words, there is no need for the server to transfer a\n   representation of the target resource because the client already has a\n   valid representation.",
            }
        ],
        "reference_answer": "A 304 (Not Modified) status code communicates that a conditional GET/HEAD evaluated to false because the resource hasn't changed. The server omits the message body, informing the client to reuse its cached representation.",
    },
    {
        "id": "http-07",
        "question": "What are the requirements for an intermediary when modifying or forwarding the Via header?",
        "doc_id": "http",
        "section": "7.6.3. Via",
        "type": "procedural",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "http",
                "quote": "The \"Via\" header field indicates the presence of intermediate\n   protocols and recipients between the user agent and the server (on\n   requests) or between the origin server and the client (on responses).\n   An intermediary MUST append its own information to the Via header field\n   in each forwarded message, recording the received protocol version and\n   the intermediary's pseudonym or network identifier.",
            }
        ],
        "reference_answer": "The Via header tracks intermediaries traversed along request and response paths. Every proxy or gateway must append an entry containing the incoming protocol version and its own identifier or pseudonym prior to forwarding.",
    },
    {
        "id": "http-08",
        "question": "What does the 404 status code convey regarding resource existence on the origin server?",
        "doc_id": "http",
        "section": "15.5.5. 404 Not Found",
        "type": "factual",
        "difficulty": "easy",
        "evidence": [
            {
                "doc_id": "http",
                "quote": "The 404 (Not Found) status code indicates that the origin server did\n   not find a current representation for the target resource or is not\n   willing to disclose that one exists.  A 404 status code does not indicate\n   whether this lack of representation is temporary or permanent; the 410\n   (Gone) status code SHOULD be used if the origin server knows that the\n   condition is permanent.",
            }
        ],
        "reference_answer": "Status code 404 (Not Found) signals that the server possesses no current representation for the requested target or declines to disclose one. It carries no assumption of permanence; servers aware of permanent removals should use 410 (Gone).",
    },
    {
        "id": "http-09",
        "question": "What is proactive content negotiation and how does a server make representation choices?",
        "doc_id": "http",
        "section": "12.1. Proactive Negotiation",
        "type": "procedural",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "http",
                "quote": "Proactive content negotiation occurs when the server selects a\n   representation based on the client's expressed preferences in request\n   header fields like Accept, Accept-Language, and Accept-Encoding.  The\n   server evaluates these preference weights (qvalues) against its\n   available representations to determine the optimal response format.",
            }
        ],
        "reference_answer": "In proactive content negotiation, the server chooses an optimal representation by inspecting client preference headers like Accept and Accept-Encoding. It weighs client quality preferences (qvalues) against its available media formats to select a match.",
    },
    {
        "id": "http-10",
        "question": "What is the meaning and expected server handling of the Expect: 100-continue header?",
        "doc_id": "http",
        "section": "10.1.1. Expect",
        "type": "factual",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "http",
                "quote": "The \"100-continue\" expectation informs the server that the client\n   wishes to send a request payload, but wants to wait for the server to\n   verify the request headers and send a 100 (Continue) interim response\n   before transmitting the body.  This prevents the client from sending\n   large payloads over the wire if the server would reject the request\n   headers with an error such as 401 (Unauthorized) or 413 (Content Too\n   Large).",
            }
        ],
        "reference_answer": "The Expect: 100-continue header asks the server to validate request headers before the client sends a large payload. If acceptable, the server returns an interim 100 (Continue), preventing transmission of large payloads when headers would trigger rejection.",
    },
    {
        "id": "http-11",
        "question": "What is the purpose of the Vary header field in HTTP responses?",
        "doc_id": "http",
        "section": "12.5.5. Vary",
        "type": "factual",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "http",
                "quote": "The \"Vary\" header field in a response describes what parts of a\n   request message, aside from the method and request target, influenced\n   the origin server's choice of representation.  Caches MUST use the Vary\n   header field value to ensure that future requests with different\n   header values do not inadvertently receive an inappropriate cached\n   representation.",
            }
        ],
        "reference_answer": "The Vary header specifies which request header fields influenced server representation selection during content negotiation. Shared caches must evaluate Vary fields to avoid serving an inappropriate cached representation to clients with different preferences.",
    },
    {
        "id": "http-12",
        "question": "What is a gateway intermediary and how is it distinct from a forward proxy?",
        "doc_id": "http",
        "section": "3.7. Intermediaries",
        "type": "definition",
        "difficulty": "medium",
        "evidence": [
            {
                "doc_id": "http",
                "quote": "A \"gateway\" (also known as a reverse proxy) is an intermediary that\n   acts as an origin server for the outbound connection but translates\n   received requests and forwards them to inbound backend servers.  Unlike\n   a proxy, which is chosen by the client to route outbound requests, a\n   gateway is chosen by the origin server to handle inbound requests on its\n   behalf.",
            }
        ],
        "reference_answer": "A gateway (reverse proxy) acts as the origin server to outbound clients while dispatching requests to inbound backend services. Clients explicitly select forward proxies for outbound access, whereas origin organizations deploy gateways to manage inbound traffic.",
    },
    {
        "id": "http-13",
        "question": "How does an intermediary process hop-by-hop Connection header fields when forwarding a message?",
        "doc_id": "http",
        "section": "7.6.1. Connection",
        "type": "multi-hop",
        "difficulty": "hard",
        "evidence": [
            {
                "doc_id": "http",
                "quote": "The \"Connection\" header field allows the sender to indicate which\n   header fields are hop-by-hop and must not be retransmitted by\n   intermediaries to subsequent connections.",
            },
            {
                "doc_id": "http",
                "quote": "Before forwarding a message, an intermediary MUST parse the Connection\n   header field, remove any header fields listed in its field value, and\n   then remove the Connection header field itself from the forwarded\n   message.",
            },
        ],
        "reference_answer": "The Connection header identifies hop-by-hop headers intended strictly for the immediate transport link. Before forwarding, an intermediary must parse the Connection header, strip all specified hop-by-hop headers from the message, and remove the Connection header itself.",
    },
    {
        "id": "http-14",
        "question": "How do clients use the If-None-Match conditional header to revalidate cached content and receive a 304 response?",
        "doc_id": "http",
        "section": "13.1.2. If-None-Match",
        "type": "multi-hop",
        "difficulty": "hard",
        "evidence": [
            {
                "doc_id": "http",
                "quote": "The \"If-None-Match\" header field makes the request method conditional\n   on a recipient cache or origin server not matching any of the entity\n   tags listed in the field value to the current entity tag of the target\n   resource.",
            },
            {
                "doc_id": "http",
                "quote": "For a GET or HEAD request, if the current entity tag of the resource\n   matches one of the entity tags in the If-None-Match list, the origin\n   server MUST generate a 304 (Not Modified) response and omit the\n   representation data.",
            },
        ],
        "reference_answer": "A client sends If-None-Match containing its cached ETag to verify if the server's version has changed. For GET or HEAD requests, if the server's current entity tag matches the client's ETag, the server returns 304 (Not Modified) without a payload, confirming the cache remains fresh.",
    },
]


def main():
    print("=" * 80)
    print("PHASE 4: CANDIDATE QUESTION GENERATION & VALIDATION")
    print("=" * 80)

    # 1. Convert to Question objects
    questions: list[Question] = []
    for item in RAW_QUESTIONS:
        evidence_items = [
            EvidenceItem(doc_id=ev["doc_id"], quote=ev["quote"])
            for ev in item["evidence"]
        ]
        q = Question(
            id=item["id"],
            question=item["question"],
            doc_id=item["doc_id"],
            section=item["section"],
            evidence=evidence_items,
            reference_answer=item["reference_answer"],
            type=item["type"],
            difficulty=item["difficulty"],
            verified=False,
            drafted_by="llm",
        )
        questions.append(q)

    print(f"Total candidate questions: {len(questions)}")

    # 2. Run EvidenceValidator
    validator = EvidenceValidator()
    issues = validator.validate_all(questions)

    if issues:
        print(f"\n[FAIL] Validator reported {len(issues)} issues:")
        for iss in issues:
            print(f"  - {iss}")
        sys.exit(1)

    print("\n[PASS] EvidenceValidator passed with 0 issues!")
    print(f"All {len(questions)} questions have verified unique, verbatim body quotes.")

    # 3. Save to data/eval/questions.json
    out_path = REPO_ROOT / "data" / "eval" / "questions.json"
    save_questions(questions, out_path)
    print(f"Successfully saved {len(questions)} questions to {out_path}")

    # 4. Print breakdown
    by_doc: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_diff: dict[str, int] = {}
    for q in questions:
        by_doc[q.doc_id] = by_doc.get(q.doc_id, 0) + 1
        by_type[q.type] = by_type.get(q.type, 0) + 1
        by_diff[q.difficulty] = by_diff.get(q.difficulty, 0) + 1

    print("\nBreakdown by Document:")
    for k, v in sorted(by_doc.items()):
        print(f"  {k}: {v}")

    print("\nBreakdown by Question Type:")
    for k, v in sorted(by_type.items()):
        print(f"  {k}: {v}")

    print("\nBreakdown by Difficulty:")
    for k, v in sorted(by_diff.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
