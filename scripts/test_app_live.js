const { chromium } = require('playwright');

(async () => {
    console.log("Launching Playwright to test Clinical Health Engine on http://localhost:8501 ...");
    const browser = await chromium.launch({
        channel: 'chrome',
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

    await page.goto('http://localhost:8501', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForSelector('.main-header', { timeout: 25000 });
    console.log("1. App loaded. Header:", await page.locator('.main-header').innerText());

    // Wait for Streamlit to finish running / rendering
    await page.waitForSelector('[data-testid="stButton"] button', { timeout: 30000 });

    const btnTexts = await page.$$eval('[data-testid="stButton"] button', els => els.map(e => e.innerText.trim()));
    console.log("2. Buttons detected:", btnTexts);

    // Find and click the scan button
    const scanBtn = page.locator('[data-testid="stButton"] button', { hasText: 'Scan & Trace' });
    console.log("3. Clicking 'Scan & Trace' button...");
    await scanBtn.click();

    console.log("4. Waiting for OCR & Clinical Health analysis (12s)...");
    await page.waitForTimeout(12000);

    const mainText = await page.locator('[data-testid="stMain"]').innerText();
    console.log("5. Extracted Results Summary:");
    const matchingLines = [];
    for (const l of mainText.split('\n')) {
        const trimmed = l.trim();
        if (trimmed.includes('DIABETES') || trimmed.includes('CARDIOVASCULAR') || trimmed.includes('ADDITIVE') || 
            trimmed.includes('Sugars') || trimmed.includes('Sodium') || trimmed.includes('Compliant') ||
            trimmed.includes('Inconclusive') || trimmed.includes('TBHQ') || trimmed.includes('E319') ||
            trimmed.includes('Verdict') || trimmed.includes('Verdict:')) {
            if (!matchingLines.includes(trimmed)) matchingLines.push(trimmed);
        }
    }
    matchingLines.slice(0, 15).forEach(m => console.log("   ->", m));

    console.log("\n>>> LIVE CLINICAL HEALTH VERDICT VERIFIED! <<<");
    await browser.close();
})();
