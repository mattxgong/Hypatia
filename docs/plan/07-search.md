# Phase 7: Search & Retrieval

**Goal**: Upgrade from basic text search to a hybrid search system (BM25 keyword search + optional semantic embeddings) so that wiki queries and /ask commands find the most relevant pages efficiently, even as the wiki grows.

**Prerequisites**: Phase 3 (wiki engine produces pages), Phase 4 (search API endpoint exists).

**Outputs**: A fast, accurate search system over wiki pages that powers both the sidebar search bar and the LLM's context retrieval for /ask queries.

---

## Tasks

### 7.1 Enable SQLite FTS5 for keyword search
Extend `app/database.py` and `app/models/db_models.py`:
- Create an FTS5 virtual table that mirrors wiki_pages content:
  ```sql
  CREATE VIRTUAL TABLE wiki_pages_fts USING fts5(
      title, content, page_path,
      content='wiki_pages',
      content_rowid='rowid'
  );
  ```
- Set up triggers to keep the FTS table in sync with wiki_pages (insert, update, delete).
- `search_wiki(class_id, query) -> list[SearchResult]` — uses FTS5 `MATCH` with BM25 ranking.
- Each result includes: page title, path, category, snippet (highlighted match), relevance score.

**Acceptance**: Keyword search returns ranked results with snippets. Results update when wiki pages change.

---

### 7.2 Implement search service
Create `app/services/search_service.py`:
- `search(class_id, query, limit=20) -> list[SearchResult]` — main search entry point.
- Initially uses FTS5 only (keyword search).
- Returns results with: title, path, category, snippet, score.
- Support filtering by category (source-summaries, concepts, entities).
- Support pagination (offset/limit).

**Acceptance**: Search returns relevant, ranked results. Filtering works.

---

### 7.3 Upgrade search API endpoint
Update `app/routers/wiki.py`:
- `GET /api/classes/{class_id}/wiki/search?q=...&category=...&limit=...`
- Returns paginated search results with snippets.
- Highlights matched terms in snippets.

**Acceptance**: API returns structured search results suitable for frontend rendering.

---

### 7.4 Integrate search into wiki engine's /ask flow
Update `app/services/wiki_engine.py` `handle_ask()`:
- Instead of reading the full index to find relevant pages, use the search service.
- `search(class_id, query, limit=10)` returns the most relevant pages.
- Read those pages and include them as context for the LLM.
- This makes /ask much more accurate for larger wikis where the index alone isn't sufficient.

**Acceptance**: /ask queries use search to find relevant context. Answer quality improves for wikis with many pages.

---

### 7.5 (Optional) Add semantic search with embeddings
Extend the search service for hybrid retrieval:
- On wiki page create/update: generate an embedding (e.g., using `sentence-transformers` with a small model like `all-MiniLM-L6-v2`).
- Store embeddings in a new table or in SQLite (as BLOB).
- At search time: embed the query, compute cosine similarity against stored embeddings.
- Combine BM25 score + cosine similarity for hybrid ranking.
- This is optional — FTS5 alone works well for moderate-scale wikis (<1000 pages).

**Acceptance**: Semantic search finds conceptually related pages even without exact keyword matches.

---

### 7.6 Connect search UI to upgraded backend
Update the frontend search (from Phase 6.9):
- Show search result categories (concept, entity, source-summary).
- Show relevance indicators.
- Show highlighted snippets.
- Support category filtering in the UI.

**Acceptance**: Search UI displays rich results from the upgraded search backend.

---

## Sequencing

```
7.1 (FTS5) ──→ 7.2 (search service) ──→ 7.3 (API) ──→ 7.4 (integrate /ask)
                                                    ──→ 7.6 (frontend)
7.5 (embeddings) — optional, after 7.2
```

- 7.1 first (database layer).
- 7.2 depends on 7.1.
- 7.3 and 7.4 depend on 7.2 and can be done in parallel.
- 7.5 is optional and can be done anytime after 7.2.
- 7.6 depends on 7.3.

---

## Risks

| Risk | Mitigation |
|------|------------|
| FTS5 not available in all SQLite builds | Python's built-in sqlite3 includes FTS5. Verify on first run. |
| Embedding model is too large for user's machine | Make semantic search optional. Default to FTS5-only. |
| Search quality degrades with wiki size | Monitor and tune BM25 parameters. Add category boosting. |
