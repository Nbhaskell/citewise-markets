from api.export_openapi import OUT, render


def test_committed_openapi_file_matches_the_api():
    """Fails when an endpoint or response shape changed but web/openapi.json wasn't regenerated.

    Fix: python -m api.export_openapi, then `npm run gen:api` in web/.
    """
    assert OUT.exists(), "web/openapi.json is missing; run python -m api.export_openapi"
    assert OUT.read_text(encoding="utf-8") == render()
