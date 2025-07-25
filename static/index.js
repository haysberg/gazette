emoji_list = [
    "🐢", "🇵🇸", "🍉", "✊", "🔺", "🌈", "📬", "🕊️", "🗞️"
];
document.getElementById("random-emoji").innerText =
    emoji_list[(Math.random() * emoji_list.length) | 0];

if (
    window.matchMedia &&
    window.matchMedia("(max-width: 480px)").matches
) {
    console.log("Fermeture des sources sur téléphone.");
    feed_element = document.getElementById("feed-list");
    feed_element.open = false;
}

const isPWA =
    !!(
        window.matchMedia?.('(display-mode: standalone)').matches ||
        window.matchMedia?.('(display-mode: fullscreen)').matches ||
        window.navigator.standalone
    );

if (
    typeof window.onbeforeinstallprompt == "object" &&
    !isPWA
) {
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