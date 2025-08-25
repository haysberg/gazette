if (window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone) {
    console.log("Déjà installé.")
} else {
    if (typeof window.onbeforeinstallprompt == "object") {
        console.log("This browser supports the beforeinstallprompt event.");
        document.getElementById("install-button").style.display = "block";
        let installPrompt = null;
        const installButton = document.querySelector("#install-button");
        window.addEventListener("beforeinstallprompt", e => {
            e.preventDefault();
            installPrompt = e;
            installButton.addEventListener("click", async () => {
                if (!installPrompt) return;
                const r = await installPrompt.prompt();
                console.log(`Install prompt was: ${r.outcome}`);
                installPrompt = null;
                installButton.setAttribute("hidden", "");
            });
            installButton.removeAttribute("hidden");
        });
    } else {
        console.log("This browser does not support the beforeinstallprompt event.");
    }
}