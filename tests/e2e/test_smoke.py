# ABOUTME: Proves the E2E fixture infrastructure itself works — a real browser can load a
# ABOUTME: page served by a real Reconvene server instance. Substantive flows are in later files.
def test_index_page_loads_in_a_real_browser(page, e2e_server):
    base_url, resumed, config, config_path = e2e_server
    page.goto(base_url)
    assert page.title() == "Reconvene"
