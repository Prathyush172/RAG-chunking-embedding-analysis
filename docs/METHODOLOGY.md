# Experimental Methodology: Comparative Analysis of Chunking Strategies and Embedding Models on Technical RFC Documentation

## 1. Research Questions & Experimental Objectives

This study investigates the empirical retrieval performance, semantic groundedness, and computational resource trade-offs of Retrieval-Augmented Generation (RAG) pipelines operating over dense, highly structured technical networking documentation from the Internet Engineering Task Force (IETF).

We formulate three primary research questions:
- **RQ1 (Chunking Strategy Effect):** How do token-window fixed-size chunking, structure-preserving sentence-level chunking, and embedding-driven semantic chunking affect retrieval effectiveness across different window capacities ($N \in \{128, 256, 512\}$ tokens) and overlap ratios?
- **RQ2 (Model & Strategy Interaction):** How does embedding model architecture—specifically comparing symmetric sentence encoders (`all-MiniLM-L6-v2`) against instruction-tuned asymmetric models (`bge-small-en-v1.5`, `e5-small-v2`)—interact with chunking granularities and token length distributions?
- **RQ3 (Operational Trade-offs):** What empirical trade-offs exist between retrieval precision, answer groundedness, indexing latency, preprocessing overhead, and memory/index footprint when constrained to CPU execution?

To guarantee scientific validity, the evaluation operates under a **strictly controlled benchmark**: identical evaluation queries, verbatim relevance labels, fixed cut-off rank ($k=5$), and uniform evaluation metrics are applied across every configuration. No ranking numbers or comparative claims are assumed; all findings derive strictly from measured experimental runs.

---

## 2. Technical Corpus & Preprocessing

The experimental corpus comprises four fundamental IETF Request for Comments (RFC) specifications totaling 310,000 words:
1. **RFC 9293 (Transmission Control Protocol - TCP):** Modern specification featuring packet headers, state transition diagrams, congestion control algorithms, and ASCII protocol state diagrams.
2. **RFC 1034 (Domain Name System - Concepts and Facilities):** Core conceptual specification for hierarchical namespace resolution.
3. **RFC 1035 (Domain Name System - Implementation and Specification):** Technical wire formats, master file representations, and resource record specifications.
4. **RFC 9110 (HTTP Semantics):** Comprehensive modern specification covering method semantics, status code registries, header field definitions, and extensive ASCII tables.

### 2.1 Deterministic Preprocessing
Raw RFC source files contain legacy formatting artifacts dating back to typewriter-era line printers. A deterministic cleaner performs the following transformations without modifying raw ground truth sources:
- Replaces form-feed pagination characters (`\x0c`) with standard newlines.
- Removes legacy running page footers (`[Page N]`) and running headers (`RFC NNNN ... Month YYYY`).
- Strips trailing line whitespace and normalizes multi-line blank runs to at most two consecutive blank lines.
- **Structural Preservation Invariant:** Protocol ASCII packet diagrams (e.g., TCP +-+-+ bit headers), section numbers, and code blocks are strictly preserved.
- **Front-Matter Exclusion:** An explicit `exclude_front_matter: true` boundary isolates normative RFC body sections from non-normative memo titles, copyright notices, and tables of contents, ensuring retrieval candidates reflect operative specification text while maintaining global document character offsets.

---

## 3. Chunking Strategies

Tokenization for all chunking strategies is standardized on `tiktoken` (`cl100k_base`) to decouple chunk boundary selection from downstream embedding model tokenizers.

### 3.1 Strategy A: Fixed-Size Token Window
- **Windows ($N$):** $N \in \{128, 256, 512\}$ tokens.
- **Overlap:** 0% (disjoint adjacent windows) and 15% (sliding overlap of $\lfloor 0.15 \times N \rfloor$ tokens).
- **Invariants:** Every chunk satisfies $N$ token limits and adheres to exact character slicing: `chunk.text == doc_text[char_start:char_end]`.

### 3.2 Strategy B: RFC-Aware Sentence Packing
- Splits text into sentence units using NLTK `PunktSentenceTokenizer` enhanced with RFC-specific exception regexes:
  - Protects abbreviations (`e.g.`, `i.e.`, `et al.`, `cf.`).
  - Protects dotted section identifiers (`Section 3.1.2.`).
  - Isolates ASCII art diagrams and tables from internal punctuation splits.
- Packs contiguous sentences into chunks up to maximum token capacity $N \in \{128, 256, 512\}$.
- **Overlap Invariant:** Overlap is parameterized by sentence units (0 or 1 sentence). When overlap is enabled, the subsequent chunk begins with the final complete sentence of the preceding chunk.
- **Oversized Block Protection:** Structural blocks exceeding $N$ tokens (e.g., massive HTTP header tables) are deterministically split at line boundaries into sub-chunks of at most $N$ tokens with `split_from_oversized = True`.

### 3.3 Strategy C: Semantic Boundary Chunking
- Segments text into candidate sentences and computes adjacent sentence embeddings using `all-MiniLM-L6-v2`.
- Calculates cosine distance between consecutive sentence embeddings $d_i = 1 - \cos(\mathbf{e}_i, \mathbf{e}_{i+1})$.
- Establishes chunk boundaries where cosine distance exceeds the 25th percentile of distances across the document, subject to constraints: $\text{min\_tokens} = 64$ and $\text{max\_tokens} = 512$.

---

## 4. Embedding Models & Vector Retrieval

To evaluate model-chunking interactions under realistic edge/CPU constraints, three state-of-the-art 384-dimensional dense sentence encoders are evaluated:
1. **`sentence-transformers/all-MiniLM-L6-v2`:** 6-layer BERT distilled student model optimized for symmetric semantic similarity. Max sequence length: 256 tokens.
2. **`BAAI/bge-small-en-v1.5`:** 12-layer model pre-trained with retrofitted retro-encoders. Requires asymmetric query prompt prefix: `"Represent this sentence for searching relevant passages: "`. Max sequence length: 512 tokens.
3. **`intfloat/e5-small-v2`:** Asymmetric embedding model trained via weakly supervised contrastive pre-training. Requires explicit prefixes: `"query: "` for search queries and `"passage: "` for indexed text chunks. Max sequence length: 512 tokens.

### 4.1 Normalization and Vector Search
- All passage and query embeddings undergo strict $L_2$ unit normalization: $\hat{\mathbf{v}} = \frac{\mathbf{v}}{\|\mathbf{v}\|_2}$.
- Vector indexing utilizes FAISS `IndexFlatIP` (exact inner product search). On $L_2$-normalized vectors, inner product is mathematically identical to cosine similarity: $\langle \hat{\mathbf{q}}, \hat{\mathbf{d}} \rangle = \cos(\mathbf{q}, \mathbf{d})$.
- Exact search eliminates approximate nearest neighbor (ANN) recall error, ensuring differences reflect chunking and embedding representations alone.
- **Tokenizer Truncation Monitoring:** Passage lengths are verified against each model's maximum sequence length, recording the exact passage truncation rate as an empirical confound.

---

## 5. Evaluation Dataset & Ground-Truth Relevance

### 5.1 Dataset Construction & Integrity Guards
- The benchmark includes 56 technical questions (14 per RFC) distributed across factual (20), definition (16), procedural (12), and multi-hop (8) queries.
- **Verbatim Evidence Anchoring:** Every question maps to 1–2 verbatim passage quotes extracted directly from cleaned RFC body text, recording exact character offsets `[char_start, char_end)`.
- **Dynamic Section Derivation:** Question section metadata is computed dynamically from section outline character ranges rather than hand-labeled strings.
- **Lexical Overlap Restrictions:** To eliminate trivial quote lookups and force genuine semantic retrieval, questions must satisfy:
  - Longest common word run between question and evidence quote $< 5$ words.
  - Lexical Jaccard word similarity $< 0.50$.
- **Verification Provenance:** Questions are flagged with verification states (`verified: false` for automated drafts, `verified: true` for expert-reviewed questions). The system mandates explicit disclosure notices whenever unverified questions are included.

### 5.2 Relevance Criteria
A retrieved chunk $c = [c_{\text{start}}, c_{\text{end}}]$ is judged relevant to question evidence $e = [e_{\text{start}}, e_{\text{end}}]$ if and only if they originate from the same document ($c.\text{doc\_id} == e.\text{doc\_id}$) and satisfy either:
1. **Overlap Length:** The length of character interval intersection $\ge 40$ characters:
   $$\max(0, \min(c_{\text{end}}, e_{\text{end}}) - \max(c_{\text{start}}, e_{\text{start}})) \ge 40$$
2. **Containment Ratio:** For short evidence spans ($|e| < 40$), the chunk covers $\ge 80\%$ of the evidence characters:
   $$\frac{\text{IntersectionLen}(c, e)}{e_{\text{end}} - e_{\text{start}}} \ge 0.80$$

---

## 6. Metrics & Statistical Testing

### 6.1 Position-Aware Retrieval Metrics
For top-$k$ retrieved chunks ($k=5$):
- **Hit@5:** Binary indicator whether at least one relevant chunk appears within top 5 ranks.
- **Mean Reciprocal Rank (MRR):** Reciprocal of the rank of the first relevant retrieved chunk ($1/\text{rank}_1$), or 0 if no relevant chunk is retrieved.
- **Precision@5:** Proportion of the 5 retrieved chunks that are relevant: $\frac{|\text{relevant in top-5}|}{5}$.
- **Recall@5:** Fraction of total relevant chunks in the index retrieved within the top 5, normalized by $\min(5, |\text{total relevant in index}|)$.
- **Context Precision (Rank-Weighted):** Mean precision at ranks containing relevant items:
  $$\text{Context Precision} = \frac{1}{|\text{relevant chunks in top-k}|} \sum_{r=1}^k P@r \times v_r$$
  where $v_r \in \{0, 1\}$ indicates relevance at rank $r$.
- **Context Recall (Span Coverage):** Proportion of character length of the gold evidence span covered by the union of retrieved chunks.

### 6.2 Controlled Baselines & Confidence Intervals
- **Random Baseline Floor:** Deterministic average over 100 random draws from the chunk pool (seeds 0–99), providing an empirical performance floor.
- **Bootstrap Confidence Intervals:** 95% confidence intervals are computed using 1,000 bootstrap resamples with fixed pseudo-random seed 42.
- **Wilcoxon Paired Signed-Rank Test:** Pairwise differences between configurations on identical questions are tested for statistical significance ($\alpha = 0.05$). All-zero difference ties are explicitly handled with $p = 1.0$.

---

## 7. Multi-Criteria Decision Framework

To resolve RQ3, configurations are evaluated across competing criteria using a normalized utility function:
$$U(c) = \sum_{i \in \text{active}} w'_i \cdot \hat{x}_i(c)$$
where:
- Positive criteria (Hit@5, MRR, Groundedness) are normalized via $\hat{x} = \frac{x - x_{\min}}{x_{\max} - x_{\min}}$.
- Negative cost criteria (Query Latency, Preprocessing Time, Storage Footprint) are inverted via $\hat{x} = \frac{x_{\max} - x}{x_{\max} - x_{\min}}$.
- Active weights are re-normalized to sum to 1.0 when optional criteria (e.g. groundedness) are disabled:
  $$w'_i = \frac{w_i}{\sum_{j \in \text{active}} w_j}$$
