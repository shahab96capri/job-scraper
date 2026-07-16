from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    page = browser.new_page(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150 Safari/537.36"
    )

    page.goto(
        "https://jobvision.ir",
        timeout=60000,
        wait_until="domcontentloaded"
    )

    print(page.title())

    input("Press Enter to close...")

    browser.close()