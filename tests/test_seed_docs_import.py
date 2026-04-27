from pathlib import Path


def test_seed_docs_importable_from_demo_package() -> None:
    from demo.seed_docs import docs_dir, seed_demo_docs, seed_test_questions

    assert callable(seed_demo_docs)
    assert callable(seed_test_questions)
    assert docs_dir() == Path(__file__).resolve().parents[1] / "demo" / "docs"
