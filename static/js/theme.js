// Applies the stored color theme before first paint, and wires the navbar
// toggle. Kept as a separate synchronous script (not bundled with the deferred
// index.min.js) so a reader who chose a theme never sees a flash of the other.
(function () {
  var KEY = "gazette-theme";

  function read() {
    try {
      return localStorage.getItem(KEY);
    } catch (error) {
      return null;
    }
  }

  function apply(theme) {
    if (theme === "light" || theme === "dark") {
      document.documentElement.setAttribute("data-theme", theme);
      document.documentElement.style.colorScheme = theme;
    } else {
      document.documentElement.removeAttribute("data-theme");
      document.documentElement.style.colorScheme = "";
    }
  }

  apply(read());

  function current() {
    var explicit = document.documentElement.getAttribute("data-theme");
    if (explicit) return explicit;
    return window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  function updateButton(button) {
    var dark = current() === "dark";
    var label = dark ? "Activer le thème clair" : "Activer le thème sombre";
    button.setAttribute("aria-label", label);
    button.setAttribute("title", label);
  }

  function toggle() {
    var next = current() === "dark" ? "light" : "dark";
    try {
      localStorage.setItem(KEY, next);
    } catch (error) {
      /* private mode: theme just will not persist */
    }
    apply(next);
    var button = document.getElementById("theme-toggle");
    if (button) updateButton(button);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var button = document.getElementById("theme-toggle");
    if (!button) return;
    updateButton(button);
    button.addEventListener("click", toggle);
  });
})();
