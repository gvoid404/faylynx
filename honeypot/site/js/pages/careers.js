import { countWebsiteVersion, postComplete, redirectToCompletionPage } from '../script.js';

export function init() {
    // Load careers.css
    if (!document.querySelector('link[href*="careers.css"]')) {
        const pathPrepend = "/" + (location.pathname.split("/")[1] || "");
        const link = document.createElement('link');
        link.rel = "stylesheet";
        link.href = pathPrepend + "/css/careers.css";
        document.head.appendChild(link);
    }

    const listingView = document.getElementById("careers-listing");
    const applyView = document.getElementById("careers-apply");
    const confirmView = document.getElementById("careers-confirmation");

    const applyRoleName = document.getElementById("apply-role-name");
    const positionSelect = document.getElementById("applicant-position");
    const applyBackBtn = document.getElementById("apply-back-btn");
    const confirmBackBtn = document.getElementById("confirm-back-btn");

    const form = document.getElementById("application-form");
    const resumeInput = document.getElementById("applicant-resume");
    const resumeDropzone = document.getElementById("resume-dropzone");
    const resumeFilename = document.getElementById("resume-filename");

    const confirmName = document.getElementById("confirm-name");
    const confirmRole = document.getElementById("confirm-role");

    function showView(view) {
        [listingView, applyView, confirmView].forEach(v => v.hidden = true);
        view.hidden = false;
        view.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    // --- Job listing -> application form ---
    document.querySelectorAll(".apply-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const role = btn.dataset.role;
            applyRoleName.textContent = role;
            positionSelect.value = role;
            showView(applyView);
        });
    });

    applyBackBtn.addEventListener("click", () => {
        form.reset();
        resumeFilename.hidden = true;
        resumeDropzone.classList.remove("has-file", "drag-over");
        showView(listingView);
    });

    confirmBackBtn.addEventListener("click", () => {
        showView(listingView);
    });

    // --- Resume dropzone: click-to-browse (native) + drag-and-drop visuals ---
    resumeInput.addEventListener("change", () => {
        if (resumeInput.files.length > 0) {
            resumeFilename.textContent = resumeInput.files[0].name;
            resumeFilename.hidden = false;
            resumeDropzone.classList.add("has-file");
        } else {
            resumeFilename.hidden = true;
            resumeDropzone.classList.remove("has-file");
        }
    });

    ["dragenter", "dragover"].forEach(evt => {
        resumeDropzone.addEventListener(evt, (e) => {
            e.preventDefault();
            resumeDropzone.classList.add("drag-over");
        });
    });

    ["dragleave", "drop"].forEach(evt => {
        resumeDropzone.addEventListener(evt, (e) => {
            e.preventDefault();
            resumeDropzone.classList.remove("drag-over");
        });
    });

    resumeDropzone.addEventListener("drop", (e) => {
        if (e.dataTransfer.files.length > 0) {
            resumeInput.files = e.dataTransfer.files;
            resumeInput.dispatchEvent(new Event("change"));
        }
    });

    // --- Submit application ---
    form.addEventListener("submit", (e) => {
        e.preventDefault();

        const name = document.getElementById("applicant-name").value.trim();
        const role = positionSelect.value;

        confirmName.textContent = name || "there";
        confirmRole.textContent = role;
        showView(confirmView);

        postComplete({ "webpage": "careers" });

        const websiteVersion = location.pathname.split("/")[1] || "";
        if (websiteVersion === countWebsiteVersion) {
            let careersCounts = Number(localStorage.getItem("careers"));
            careersCounts++;
            localStorage.setItem("careers", careersCounts);
            if (careersCounts >= 3) {
                redirectToCompletionPage("careers");
            }
        }
    });
}
