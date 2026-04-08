// Only register the leave-confirmation on job status pages, not on the upload form.
// upload.js handles its own confirmation only after a file has been selected.
if (document.getElementById("jobPage")) {
  window._jobLeaveHandler = function (e) {
    e.preventDefault();
    e.returnValue = "";
  };
  window.addEventListener("beforeunload", window._jobLeaveHandler);
}

(function () {
  const installButton = document.getElementById("installAppBtn");
  let deferredPrompt = null;
  const isInstalled = localStorage.getItem("docunlockInstalled") === "true";

  function hideInstallButton() {
    if (installButton) {
      installButton.classList.add("d-none");
    }
  }

  function showInstallButton() {
    if (installButton && !isInstalled) {
      installButton.classList.remove("d-none");
    }
  }

  if (navigator.serviceWorker) {
    navigator.serviceWorker.register("/static/sw.js").catch(() => {
      // Service worker registration is optional; install prompt may still work when available.
    });
  }

  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault();
    deferredPrompt = event;
    showInstallButton();
  });

  window.addEventListener("appinstalled", function () {
    localStorage.setItem("docunlockInstalled", "true");
    hideInstallButton();
  });

  if (installButton) {
    installButton.addEventListener("click", async function () {
      if (!deferredPrompt) {
        return;
      }
      deferredPrompt.prompt();
      const choiceResult = await deferredPrompt.userChoice;
      deferredPrompt = null;
      if (choiceResult.outcome === "accepted") {
        hideInstallButton();
      }
    });
  }

  if (isInstalled) {
    hideInstallButton();
  }
})();
