from unittest.mock import MagicMock, patch

from tools import create_fit_card, search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe, get_example_wardrobe, load_listings


SAMPLE_ITEM = load_listings()[5]  # Graphic Tee — 2003 Tour Bootleg Style


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


# ── suggest_outfit ────────────────────────────────────────────────────────────

@patch("tools._get_groq_client")
def test_suggest_outfit_empty_wardrobe(mock_get_client):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Pair with baggy jeans and sneakers."))]
    )
    mock_get_client.return_value = mock_client

    result = suggest_outfit(SAMPLE_ITEM, get_empty_wardrobe())

    assert isinstance(result, str)
    assert len(result) > 0
    assert not result.startswith("Error:")
    prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "wardrobe is empty" in prompt.lower()


@patch("tools._get_groq_client")
def test_suggest_outfit_llm_failure(mock_get_client):
    mock_get_client.side_effect = Exception("API down")

    result = suggest_outfit(SAMPLE_ITEM, get_example_wardrobe())

    assert result == "Error: could not generate outfit suggestion — please try again."


# ── create_fit_card ─────────────────────────────────────────────────────────

def test_create_fit_card_empty_outfit():
    result = create_fit_card("", SAMPLE_ITEM)
    assert result == "Error: outfit description is required to generate a fit card."


def test_create_fit_card_whitespace_outfit():
    result = create_fit_card("   ", SAMPLE_ITEM)
    assert result == "Error: outfit description is required to generate a fit card."


@patch("tools._get_groq_client")
def test_create_fit_card_llm_failure(mock_get_client):
    mock_get_client.side_effect = Exception("API down")

    result = create_fit_card("Jeans and sneakers combo.", SAMPLE_ITEM)

    assert result == "Error: could not generate fit card — please try again."
