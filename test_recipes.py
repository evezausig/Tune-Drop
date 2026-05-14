"""
Basic sanity tests for the emotion/genre recipe system.
Run with: streamlit run test_recipes.py  (requires Streamlit environment)
Or import and call the test functions from within the running app.
"""
from emotion_recipes import EMOTION_RECIPES
from genre_recipes import GENRE_RECIPES


def test_all_recipes_have_subs():
    """Verify every emotion and genre has at least one sub-category."""
    for emotion, subs in EMOTION_RECIPES.items():
        assert len(subs) > 0, f"Emotion '{emotion}' has no sub-categories"
    for genre, subs in GENRE_RECIPES.items():
        assert len(subs) > 0, f"Genre '{genre}' has no sub-categories"
    print(f"✅ All {len(EMOTION_RECIPES)} emotions and {len(GENRE_RECIPES)} genres have sub-categories")


def test_recipe_keys():
    """Verify each recipe contains expected audio feature keys."""
    expected_keys = {"valence", "energy", "danceability"}
    for emotion, subs in EMOTION_RECIPES.items():
        for sub, recipe in subs.items():
            overlap = expected_keys & set(recipe.keys())
            assert len(overlap) > 0, f"Recipe {emotion}→{sub} has no audio feature keys"
    print(f"✅ All emotion recipes contain valid audio feature keys")


if __name__ == "__main__":
    print("Running recipe structure tests...\n")
    test_all_recipes_have_subs()
    test_recipe_keys()
    print("\nAll tests passed.")
