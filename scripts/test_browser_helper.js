async (page) => {
    return {
        status: "ok",
        url: page.url(),
        title: await page.title()
    };
};
