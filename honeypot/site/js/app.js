const content = document.getElementById("content");
const VERSION_PREFIX = "/" + (location.pathname.split("/")[1] || "");

// Track current page module for cleanup
let currentPageModule = null;

async function loadPage(path) {
    // Clean up previous page module if it has a cleanup function
    if (currentPageModule?.cleanup) {
        try {
            currentPageModule.cleanup();
        } catch (e) {
            console.error('Error during page cleanup:', e);
        }
    }
    currentPageModule = null;

    // Strip leading slash and any version prefix
    path = path.replace(VERSION_PREFIX, "") || "/";
    if (!path.startsWith("/")) path = "/" + path;

    // Determine the route and module path
    let route, modulePath;

    // Check if this is a forum thread URL (/forums/{id})
    if (path.startsWith("/forums/") && path !== "/forums") {
        // This is an individual thread page
        route = `${VERSION_PREFIX}/pages/forum_thread.html`;
        modulePath = `${VERSION_PREFIX}/js/pages/forum_thread.js`;
    } else {
        // "/" maps to the home page; other paths to pages/<path>.html
        const ext = path.split(".").pop();
        route = path === "/" || path === "/index.html"
            ? `${VERSION_PREFIX}/pages/home.html`
            : (ext !== path && ext !== "" ? `${VERSION_PREFIX}/pages${path}` : `${VERSION_PREFIX}/pages${path}.html`);

        // Standard module path for non-thread pages
        modulePath = path === "/" || path === "/index.html" ? "" : `${VERSION_PREFIX}/js/pages${path}.js`;
    }

    content.classList.add("fade-out");
    await new Promise(r => setTimeout(r, 200));

    try {
        const res = await fetch(route);
        if (!res.ok) throw new Error("404");
        const html = await res.text();
        content.innerHTML = html;
        content.classList.remove("fade-out");
        content.classList.add("fade-in");

        // Lazy-load per-page JS module
        try {
            if (modulePath) {
                const mod = await import(modulePath);
                currentPageModule = mod;
                mod.init?.();
            }
        } catch {
            // Page has no JS module – that's fine
        }
    } catch (err) {
        content.innerHTML = "<h2>404 Not Found</h2>";
        content.classList.remove("fade-out");
    }
}

// --- Navigation handling (intercept all <a data-route>) ---
document.addEventListener("click", e => {
    const link = e.target.closest("a[data-route]");
    if (!link) return;
    e.preventDefault();

    const route = link.getAttribute("data-route");
    const newUrl = VERSION_PREFIX + route;

    history.pushState({ path: route }, "", newUrl);
    loadPage(route);
});

// --- Browser back/forward buttons ---
window.addEventListener("popstate", e => {
    const path = e.state?.path || "/";
    loadPage(path);
});

// --- Initial page load ---
loadPage(location.pathname);