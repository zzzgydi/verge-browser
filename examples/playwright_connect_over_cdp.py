from playwright.sync_api import sync_playwright

from verge_browser import VergeClient


def main() -> None:
    client = VergeClient()
    sandbox = client.create_sandbox(alias="playwright-demo", default_url="https://example.com")
    cdp = client.get_cdp_info(sandbox["id"])

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp["cdp_url"])
        page = browser.contexts[0].pages[0]
        print(page.title())
        browser.close()


if __name__ == "__main__":
    main()
