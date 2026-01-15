const isPWA = !!(
  window.matchMedia?.("(display-mode: standalone)").matches ||
  window.matchMedia?.("(display-mode: fullscreen)").matches ||
  window.navigator.standalone
);

// Register service worker
if ("serviceWorker" in navigator) {
  navigator.serviceWorker
    .register("/sw.js")
    .then((registration) => {
      console.log("Service Worker registered with scope:", registration.scope);
    })
    .catch((error) => {
      console.error("Service Worker registration failed:", error);
    });
}

// Offline banner
const offlineBanner = document.querySelector("#offline-banner");

function updateOfflineStatus() {
  if (offlineBanner) {
    if (navigator.onLine) {
      offlineBanner.classList.add("hidden");
    } else {
      offlineBanner.classList.remove("hidden");
    }
  }
}

window.addEventListener("online", updateOfflineStatus);
window.addEventListener("offline", updateOfflineStatus);
updateOfflineStatus();

// PWA install prompt
if (!isPWA) {
  let installPrompt = null;
  const installButton = document.querySelector("#install-button");

  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    installPrompt = e;
    // Show the install button
    if (installButton) {
      installButton.removeAttribute("hidden");
      installButton.addEventListener("click", async () => {
        if (!installPrompt) return;
        const result = await installPrompt.prompt();
        console.log(`Install prompt was: ${result.outcome}`);
        installPrompt = null;
        installButton.setAttribute("hidden", "");
      });
    }
  });
}
