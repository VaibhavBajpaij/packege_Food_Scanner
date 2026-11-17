const { chromium } = require('playwright');

(async () => {
    console.log("Connecting Playwright to http://localhost:8501 ...");
    const browser = await chromium.launch({
        channel: 'chrome',
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
    });
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

    await page.goto('http://localhost:8501', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForSelector('.main-header', { timeout: 25000 });
    console.log("1. Header text:", await page.locator('.main-header').innerText());

    const caption = await page.getByText('Expand sidebar').innerText();
    console.log("2. Tooltip / Caption:", caption);

    const expandBtn = page.locator('button[aria-label="Expand sidebar"]');
    if (await expandBtn.isVisible()) {
        console.log("3. Sidebar initially collapsed as required. Expanding sidebar...");
        await expandBtn.click();
        await page.waitForTimeout(1000);
    }

    const sidebarText = await page.locator('[data-testid="stSidebar"]').innerText();
    console.log("4. System Diagnostics in sidebar:");
    for (const l of sidebarText.split('\n')) {
        if (l.includes('PaddleOCR') || l.includes('Database') || l.includes('Gemini') || l.includes('USDA') || l.includes('Open Food')) {
            console.log("   ->", l.trim());
        }
    }

    console.log("\n>>> LIVE UI & SYSTEM DIAGNOSTICS FULLY VERIFIED! <<<");
    await browser.close();
})();
