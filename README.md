# FitFindr

FitFindr is a thrift-shopping agent that searches a mock secondhand listings dataset, suggests outfits based on the user's wardrobe, and generates a shareable social-media caption for the top match. The agent runs through a conditional planning loop in `agent.py` and is exposed via a Gradio UI in `app.py`.

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root with your Groq API key ([console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

Run the Gradio app:

```bash
python app.py
```

Run tests:

```bash
pytest tests/
```

Run the agent CLI smoke tests:

```bash
python agent.py
```

## Project Structure

```
Fitfinder/
├── agent.py              # Planning loop and session state
├── app.py                # Gradio UI
├── tools.py              # search_listings, suggest_outfit, create_fit_card
├── data/
│   ├── listings.json     # 40 mock secondhand listings
│   └── wardrobe_schema.json
├── utils/
│   └── data_loader.py    # load_listings(), get_example_wardrobe(), etc.
├── tests/
│   └── test_tools.py     # Tool-level pytest coverage
└── planning.md           # Full design spec
```

---

## Tool Inventory

### 1. `search_listings`

**Purpose:** Search the mock listings dataset for items matching a keyword description, with optional size and price filters.

| Parameter | Type | Description |
|-----------|------|-------------|
| `description` | `str` | Keywords describing the item (e.g. `"vintage graphic tee"`) |
| `size` | `str \| None` | Size filter; case-insensitive substring match (e.g. `"M"` matches `"S/M"`). `None` skips filtering. |
| `max_price` | `float \| None` | Maximum price (inclusive). `None` skips filtering. |

**Returns:** `list[dict]` — matching listings sorted by relevance score (highest first). Each dict has `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`. Returns `[]` if nothing matches.

**Scoring:** Filters by price and size first, then scores each listing by keyword overlap against `title`, `description`, and `style_tags`. Listings with score 0 are excluded.

---

### 2. `suggest_outfit`

**Purpose:** Given a thrifted item and the user's wardrobe, call the Groq LLM (`llama-3.3-70b-versatile`) to suggest 1–2 complete outfits.

| Parameter | Type | Description |
|-----------|------|-------------|
| `new_item` | `dict` | A listing dict from `search_listings` (uses `title`, `category`, `style_tags`, `colors`, `condition`) |
| `wardrobe` | `dict` | Wardrobe dict with an `items` key containing wardrobe item dicts (`name`, `category`, `colors`, `style_tags`, optional `notes`) |

**Returns:** `str` — non-empty outfit suggestion. References specific wardrobe pieces when items exist; provides general styling advice when the wardrobe is empty. On API failure, returns `"Error: could not generate outfit suggestion — please try again."`

---

### 3. `create_fit_card`

**Purpose:** Generate a 2–4 sentence casual Instagram/TikTok-style caption for the thrifted find.

| Parameter | Type | Description |
|-----------|------|-------------|
| `outfit` | `str` | Outfit suggestion string from `suggest_outfit` |
| `new_item` | `dict` | Listing dict (uses `title`, `price`, `platform`) |

**Returns:** `str` — casual first-person caption mentioning the item name, price, and platform naturally once each. LLM temperature is `1.0` for varied output. On invalid input or API failure, returns a descriptive error string starting with `"Error:"`.

---

## Planning Loop

`run_agent(query, wardrobe)` in `agent.py` follows a strict conditional sequence. Each tool is only called if the previous step succeeded.

```
User query
    │
    ▼
Step 1: Initialize session (_new_session)
    │
    ▼
Step 2: Parse query → description, size, max_price (regex)
    │
    ▼
Step 3: search_listings(description, size, max_price)
    │
    ├─ results == [] ──► set session["error"], RETURN (stop)
    │
    ▼
Step 4: selected_item = search_results[0]
    │
    ▼
Step 5: suggest_outfit(selected_item, wardrobe)
    │
    ├─ result starts with "Error:" ──► set session["error"], RETURN (stop)
    │
    ▼
Step 6: create_fit_card(outfit_suggestion, selected_item)
    │
    ├─ result starts with "Error:" ──► set session["error"], RETURN (stop)
    │
    ▼
Step 7: Return session (error is None, all fields populated)
```

**Query parsing** uses regex to extract:
- `max_price` from patterns like `under $30`, `under 30`, `less than $40`
- `size` from patterns like `size M`, `in M`
- `description` from the remaining text (with leading phrases like "looking for" stripped)

The agent does **not** call all three tools unconditionally. If `search_listings` returns no matches, `suggest_outfit` and `create_fit_card` are never invoked.

---

## State Management

All state lives in a single `session` dict initialized by `_new_session()` at the start of each interaction. No tool reads the raw user query after parsing — downstream steps use session values only.

| Key | Type | Set in | Used by |
|-----|------|--------|---------|
| `query` | `str` | Step 1 | Step 2 (parsing) |
| `parsed` | `dict` | Step 2 | Step 3 (`description`, `size`, `max_price`) |
| `search_results` | `list[dict]` | Step 3 | Step 4 |
| `selected_item` | `dict` | Step 4 | Steps 5, 6 |
| `wardrobe` | `dict` | Step 1 | Step 5 |
| `outfit_suggestion` | `str` | Step 5 | Step 6 |
| `fit_card` | `str` | Step 6 | `app.py` display |
| `error` | `str \| None` | Any failure step | `app.py` (checked first) |

`handle_query()` in `app.py` calls `run_agent()`, checks `session["error"]` first, and maps the session to three Gradio output panels: listing details, outfit suggestion, and fit card.

---

## Error Handling

Each tool handles its failure mode without raising exceptions to the caller. The planning loop checks results and branches early.

### `search_listings` — no matches

**Behavior:** Returns `[]`. Agent sets an informative error and stops.

**Example (tested):**
```bash
python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
# []
```

```bash
python agent.py  # no-results test case
```

**Agent response:**
```
No listings found for 'designer ballgown' in size XXS under $5.00. Try removing the size filter, raising your budget, or using different keywords.
```

`selected_item`, `outfit_suggestion`, and `fit_card` remain `None`.

---

### `suggest_outfit` — empty wardrobe

**Behavior:** Uses a different LLM prompt asking for general styling advice. Returns a useful non-empty string — does not crash or return `""`.

**Example (tested):**
```bash
python -c "
from tools import search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(suggest_outfit(results[0], get_empty_wardrobe()))
"
```

**Output:** General outfit ideas referencing piece types and aesthetics (e.g. cottagecore skirt + sneakers, Y2K streetwear with high-waisted jeans) — no wardrobe items named because the wardrobe is empty.

---

### `suggest_outfit` — LLM API failure

**Behavior:** Exception caught inside the tool. Returns `"Error: could not generate outfit suggestion — please try again."` Planning loop sets `session["error"]` and returns without calling `create_fit_card`.

---

### `create_fit_card` — empty outfit string

**Behavior:** Guard at the top of the function. Returns immediately without calling the LLM.

**Example (tested):**
```bash
python -c "
from tools import search_listings, create_fit_card
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(create_fit_card('', results[0]))
"
# Error: outfit description is required to generate a fit card.
```

---

### `create_fit_card` — LLM API failure

**Behavior:** Exception caught. Returns `"Error: could not generate fit card — please try again."` Planning loop sets `session["error"]`.

---

## Spec Reflection

**What matched the plan:** The three-tool pipeline, conditional planning loop, session dict as single source of truth, regex-based query parsing, and all documented failure modes behave as specified in `planning.md`. Tools were built and tested in isolation (Milestone 3) before wiring the agent loop (Milestone 4). Failure modes were deliberately triggered and verified (Milestone 5).

**What differed or was learned:**
- **Search ranking:** The top result for `"vintage graphic tee"` is not always `lst_006` — keyword scoring can rank other vintage/graphic tees higher depending on tag overlap. The behavior is correct per the scoring spec; exact top-match ordering was not guaranteed.
- **Empty wardrobe is not an error:** Initially easy to treat as a failure, but the spec correctly treats it as a prompt branch — the agent still completes the full flow and produces outfit advice plus a fit card.
- **Testing discipline:** Implementing and pytest-testing each tool before connecting them made debugging the planning loop straightforward. The `if not search_results` early-exit branch was the most important conditional to get right.
- **Error strings as control flow:** Using `"Error:"` prefixes from LLM tools lets the planning loop branch without try/except at the agent level — simple and readable.

---

## AI Usage

<!-- Write this section yourself. -->
