# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---
## A Complete Interaction (Step by Step)

FitFindr takes a user's natural language request — including what they're looking for, their size, and their budget — and calls `search_listings` to find matching items from the 40-item mock dataset. If a match is found, it passes the top result and the user's wardrobe into `suggest_outfit` to generate a styling recommendation using the Groq LLM, then calls `create_fit_card` to produce a shareable Instagram-style caption. If `search_listings` returns an empty list, the agent stops immediately, sets an informative error message in the session, and does NOT call the remaining tools.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:** The agent parses the query to extract `description = "vintage graphic tee"`, `size = None` (not specified), and `max_price = 30.0`. It calls `search_listings("vintage graphic tee", size=None, max_price=30.0)`. The function loads all 40 listings, drops anything over $30.00, then scores remaining listings by counting keyword and style_tag overlaps with "vintage graphic tee". It returns a ranked list — the top match is `lst_006` ("Graphic Tee — 2003 Tour Bootleg Style", $24.00, depop) with a high overlap score on "graphic tee" and "vintage" tags. The agent stores this in `session["selected_item"]`.

**Step 2:** The agent calls `suggest_outfit(session["selected_item"], wardrobe)`. The wardrobe has 10 items (baggy straight-leg jeans, white ribbed tank, chunky white sneakers, black combat boots, etc.). The LLM receives a prompt describing the band tee and the wardrobe contents, and returns something like: "Pair this faded graphic tee with the baggy straight-leg dark wash jeans and chunky white sneakers for a classic 90s streetwear look. Tuck the front of the tee in slightly for shape. Add the vintage black denim jacket if the weather calls for it." This is stored in `session["outfit_suggestion"]`.

**Step 3:** The agent calls `create_fit_card(session["outfit_suggestion"], session["selected_item"])`. The LLM receives the outfit suggestion and the item details (title, price, platform) and produces a casual, first-person caption like: "found this faded 2003 tour tee on depop for $24 and it immediately went with every single thing in my closet 🖤 baggy jeans + chunky sneakers and we're good to go". This is stored in `session["fit_card"]`.

**Final output to user:** The Gradio interface displays three panels — the listing details (title, price, platform, condition, size), the outfit suggestion paragraph, and the fit card caption. All three panels are populated and the user sees a complete result from a single query.


## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the 40-item mock listings dataset (`data/listings.json`) for items matching the user's description, optional size, and optional price ceiling. It scores matches by counting keyword overlaps between the user's description and each listing's `title`, `description` field, and `style_tags` array, then returns results ranked by relevance score.

**Input parameters:**
- `description` (str): Natural language keywords describing the item the user wants (e.g., `"vintage graphic tee"`, `"90s track jacket"`). Used for keyword scoring against `title`, `description`, and `style_tags` fields on each listing.
- `size` (str | None): Size string to filter by, or `None` to skip size filtering. Matching is case-insensitive and uses substring matching so `"M"` matches `"S/M"` and `"M/L"`. If `None`, all sizes pass through.
- `max_price` (float | None): Maximum price (inclusive). Any listing with `price > max_price` is dropped before scoring. If `None`, no price filter is applied.

**What it returns:**
A list of listing dicts sorted by relevance score (highest first). Each dict contains all original listing fields: `id` (str), `title` (str), `description` (str), `category` (str — one of tops/bottoms/outerwear/shoes/accessories), `style_tags` (list[str]), `size` (str), `condition` (str — excellent/good/fair), `price` (float), `colors` (list[str]), `brand` (str or None), `platform` (str — depop/thredUp/poshmark). Listings with a relevance score of 0 are excluded. Returns an empty list `[]` if nothing matches — never raises an exception.

**What happens if it fails or returns nothing:**
The function returns `[]`. The planning loop checks `if not results` immediately after this call. If true, it sets `session["error"]` to a message like: `"No listings found for 'designer ballgown' in size XXS under $5.00. Try removing the size filter, raising your budget, or using different keywords."` Then it returns the session immediately — `suggest_outfit` and `create_fit_card` are never called.

---

### Tool 2: suggest_outfit

**What it does:**
Given a specific listing item the user is considering buying and their current wardrobe, calls the Groq LLM (`llama-3.3-70b-versatile`) to suggest one or two complete outfit combinations. If the wardrobe is empty, it provides general styling advice based on the item's category and style tags alone.

**Input parameters:**
- `new_item` (dict): A single listing dict returned by `search_listings` — specifically `session["selected_item"]`. The relevant fields used in the prompt are `title`, `category`, `style_tags`, `colors`, and `condition`.
- `wardrobe` (dict): The user's wardrobe dict with an `'items'` key containing a list of wardrobe item dicts. Each wardrobe item has `name`, `category`, `colors`, `style_tags`, and optional `notes`. May be an empty wardrobe (`{'items': []}`) — this must be handled gracefully.

**What it returns:**
A non-empty string (the LLM response) containing 1–2 outfit suggestions. If the wardrobe has items, the suggestions reference specific named pieces from the wardrobe. If the wardrobe is empty, the string contains general styling advice about what kinds of pieces pair well with the new item's style tags and category. On LLM API failure, returns an error string like `"Error: could not generate outfit suggestion — please try again."` rather than raising an exception.

**What happens if it fails or returns nothing:**
If `wardrobe['items']` is empty, the LLM prompt is adjusted to ask for general styling advice — the function still returns a useful string, never an empty string or exception. If the Groq API call fails, the exception is caught and a descriptive error string starting with `"Error:"` is returned. The planning loop detects the `"Error:"` prefix and sets `session["error"]` accordingly.
---

### Tool 3: create_fit_card
**What it does:**
Generates a 2–4 sentence casual, shareable outfit caption — the kind of text someone would post with an OOTD photo on Instagram or TikTok. It calls the Groq LLM with a higher temperature to ensure varied, authentic-sounding output across different inputs.

**Input parameters:**
- `outfit` (str): The outfit suggestion string from `suggest_outfit()`, stored in `session["outfit_suggestion"]`. Provides the LLM with full styling context for the caption.
- `new_item` (dict): The listing dict from `session["selected_item"]`. Fields used: `title` (item name), `price` (mentioned naturally once), `platform` (mentioned naturally once — e.g., "found it on depop").

**What it returns:**
A 2–4 sentence string that sounds like a real social media caption — first-person, casual tone, specific about the outfit vibe, mentioning the item name, price, and platform naturally once each. LLM temperature is set to `1.0` or higher so outputs vary across runs on the same input. Returns a descriptive error string if inputs are invalid — never raises an exception.

**What happens if it fails or returns nothing:**
If `outfit` is an empty string or whitespace-only, the function immediately returns `"Error: outfit description is required to generate a fit card."` without calling the LLM. If the LLM call fails, the exception is caught and `"Error: could not generate fit card — please try again."` is returned. The function never raises an exception to the caller.
---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**
The planning loop in `run_agent()` follows a strict conditional sequence — each tool is only called if the previous one succeeded. Here is the exact conditional logic:
Step 1: Initialize session with _new_session(query, wardrobe).
Step 2: Parse the query using regex + simple string matching to extract:
- description: the search phrase (everything before size/price keywords)
- size: match patterns like "size M", "size XL", "in M"
- max_price: match patterns like "under $30", "under 30", "less than $40"
Store result in session["parsed"].
Step 3: Call search_listings(description, size, max_price).
Store list in session["search_results"].
IF len(session["search_results"]) == 0:
→ set session["error"] = f"No listings found for '{description}'..."
→ RETURN session immediately (do NOT call suggest_outfit or create_fit_card)
Step 4: session["selected_item"] = session["search_results"]
(top-ranked result by relevance score)
Step 5: Call suggest_outfit(session["selected_item"], session["wardrobe"]).
IF result starts with "Error:":
→ set session["error"] = result
→ RETURN session immediately (do NOT call create_fit_card)
ELSE:
→ session["outfit_suggestion"] = result
Step 6: Call create_fit_card(session["outfit_suggestion"], session["selected_item"]).
IF result starts with "Error:":
→ set session["error"] = result
→ RETURN session early
ELSE:
→ session["fit_card"] = result
Step 7: Return session.
session["error"] is None — all three tools completed successfully.
---

## State Management

**How does information from one tool get passed to the next?**

All state lives in a single `session` dict initialized by `_new_session()` at the start of each `run_agent()` call. The session is the single source of truth — no tool reads from the original user query string after Step 2.

| Key | Type | Set in | Read by |
|-----|------|--------|---------|
| `session["query"]` | str | Step 1 | Step 2 (parsing) |
| `session["parsed"]` | dict with keys `description`, `size`, `max_price` | Step 2 | Step 3 (search call) |
| `session["search_results"]` | list[dict] | Step 3 | Step 4 (item selection) |
| `session["selected_item"]` | dict (single listing) | Step 4 | Step 5 (suggest_outfit), Step 6 (create_fit_card) |
| `session["wardrobe"]` | dict | Step 1 (passed in from caller) | Step 5 (suggest_outfit) |
| `session["outfit_suggestion"]` | str | Step 5 | Step 6 (create_fit_card) |
| `session["fit_card"]` | str | Step 6 | Returned to app.py for display |
| `session["error"]` | str or None | Any step on failure | app.py checks this first |

State flows in one direction only: each step reads from prior session keys and writes to new ones. No tool is ever called with re-entered user input — the user types their query once and all downstream data flows from session values.
---
## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No listings match the query (returns `[]`) | Sets `session["error"]` to: `"No listings found for '[description]' [in size X] [under $Y]. Try removing the size filter, raising your budget, or using different keywords."` Returns session immediately. `suggest_outfit` and `create_fit_card` are never called. |
| `suggest_outfit` | Wardrobe is empty (`wardrobe['items'] == []`) | Adjusts the LLM prompt to ask for general styling advice (what vibe the item suits, what categories pair well). Still returns a useful non-empty string. Does not crash or return an empty string. |
| `suggest_outfit` | LLM API call raises an exception | Exception is caught in a `try/except`. Returns `"Error: could not generate outfit suggestion — please try again."` The planning loop detects the "Error:" prefix and sets `session["error"]`, returning early. |
| `create_fit_card` | `outfit` argument is empty or whitespace-only | Returns `"Error: outfit description is required to generate a fit card."` immediately, without calling the LLM. |
| `create_fit_card` | LLM API call raises an exception | Exception is caught. Returns `"Error: could not generate fit card — please try again."` The planning loop detects this and sets `session["error"]`. |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     ASCII art, a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html), or an embedded
     sketch are all fine. You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

**Tool 1 — `search_listings`:** I will give Claude the Tool 1 spec block above (inputs with types, scoring logic description, return value, failure mode) and the `load_listings()` docstring from `utils/data_loader.py`. I will ask it to implement the function body inside `tools.py` without modifying the function signature. Before running the code, I will verify: (1) it calls `load_listings()` and does not re-open the JSON file, (2) it applies `max_price` and `size` filters before scoring, (3) it handles `None` for both optional parameters, (4) it returns `[]` on no matches instead of raising. I will then test it with three queries: `("vintage graphic tee", None, 30.0)` (expect results), `("band tee", "L", 25.0)` (expect filtered results), and `("designer ballgown", "XXS", 5.0)` (expect `[]`).

**Tool 2 — `suggest_outfit`:** I will give Claude the Tool 2 spec block above plus the `wardrobe_schema.json` example wardrobe structure (so it knows the field names). I will ask it to write the prompt for both the empty and non-empty wardrobe cases and make the Groq API call. Before using the code, I will verify: (1) it imports `_get_groq_client()` from the same file, (2) it checks `if not wardrobe['items']` and uses a different prompt branch, (3) all exceptions are caught and return an error string. I will test it with `get_example_wardrobe()` and `get_empty_wardrobe()` separately.

**Tool 3 — `create_fit_card`:** I will give Claude the Tool 3 spec block above and ask it to write a prompt that produces an Instagram-style caption. I will specify that `temperature=1.0` must be set on the API call. Before using the code, I will verify: (1) the empty `outfit` guard is at the top of the function before any API call, (2) temperature is set, (3) exceptions are caught. I will run it twice on the same input and confirm the outputs differ.

**Milestone 4 — Planning loop and state management:**

I will give Claude the full Architecture diagram above (the ASCII art) and the Planning Loop section (the step-by-step pseudo-code). I will ask it to implement `run_agent()` in `agent.py`, following the numbered steps exactly. Before trusting the generated code, I will verify: (1) the `if not results` branch is present after `search_listings`, (2) `suggest_outfit` is never called with `None` as the first argument, (3) all session keys defined in `_new_session()` are populated at the right steps, (4) the function returns `session` at every possible exit point (not just at the end). I will run the two test cases already in `agent.py`'s `__main__` block and confirm the happy-path populates all fields and the no-results path shows a non-None `session["error"]` with `session["fit_card"]` remaining `None`.
---