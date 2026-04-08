(function () {
  const jobPage = document.getElementById("jobPage");
  const jobId = jobPage.dataset.jobId;

  const stateQueued = document.getElementById("stateQueued");
  const stateProcessing = document.getElementById("stateProcessing");
  const stateDone = document.getElementById("stateDone");
  const stateError = document.getElementById("stateError");
  const queuePos = document.getElementById("queuePos");
  const queueBar = document.getElementById("queueBar");
  const downloadBtn = document.getElementById("downloadBtn");
  const errorDetail = document.getElementById("errorDetail");

  let currentState = null;
  let minQueueTimeExpired = false;
  let jobStartedAt = Date.now();
  let notified = false;
  let pollTimer = null;

  // Minimum 2 seconds on queue page
  setTimeout(() => {
    minQueueTimeExpired = true;
  }, 2000);

  function setState(name) {
    if (currentState === name) return;
    currentState = name;
    [stateQueued, stateProcessing, stateDone, stateError].forEach(
      (el) => (el.style.display = "none"),
    );
    const map = {
      queued: stateQueued,
      processing: stateProcessing,
      done: stateDone,
      error: stateError,
    };
    if (map[name]) map[name].style.display = "block";
  }

  const successSound = new Audio("/static/sounds/success.wav");
  const failureSound = new Audio("/static/sounds/failure.wav");

  function playSound(audio) {
    try {
      audio.currentTime = 0;
      audio.play();
    } catch (e) {}
  }

  function sendPushNotification() {
    if (!("Notification" in window)) return;
    const show = () => {
      try {
        const notification = new Notification("DocUnlock ✓", {
          body: "Your PDF has been unlocked and is ready to download!",
          icon: "/static/img/logo.png",
        });
        setTimeout(() => {
          notification.close();
        }, 10000);
      } catch (e) {}
    };
    if (Notification.permission === "granted") {
      show();
    } else if (Notification.permission !== "denied") {
      Notification.requestPermission().then((p) => {
        if (p === "granted") show();
      });
    }
  }

  function onDone(outputFilename) {
    if (notified) return;
    notified = true;

    clearInterval(pollTimer);
    setState("done");

    downloadBtn.href = "/download/" + jobId;
    downloadBtn.setAttribute("download", outputFilename || "unlocked.pdf");

    document.title = "✅ Done — DocUnlock";
    playSound(successSound);
    sendPushNotification();

    // Remove leave confirmation — job is complete
    if (window._jobLeaveHandler) {
      window.removeEventListener("beforeunload", window._jobLeaveHandler);
    }

    // Also suppress it when clicking "Unlock another PDF"
    const backLink = document.querySelector(".back-link a");
    if (backLink) {
      backLink.addEventListener("click", () => {
        if (window._jobLeaveHandler) {
          window.removeEventListener("beforeunload", window._jobLeaveHandler);
        }
      });
    }
  }

  function onError(msg) {
    clearInterval(pollTimer);
    setState("error");
    errorDetail.textContent = msg || "An unexpected error occurred.";
    document.title = "❌ Error — DocUnlock";
    playSound(failureSound);

    if (window._jobLeaveHandler) {
      window.removeEventListener("beforeunload", window._jobLeaveHandler);
    }
  }

  async function poll() {
    try {
      const res = await fetch("/status/" + jobId);
      if (!res.ok) {
        onError("Could not fetch job status.");
        return;
      }
      const data = await res.json();

      // Always update queue position display even during the minimum wait
      if (data.status === "queued") {
        const pos = data.queue_position || 1;
        queuePos.textContent = pos;
        const pct = Math.max(10, 100 - ((pos - 1) / 6) * 90);
        queueBar.style.width = pct + "%";
        document.title = `⏳ Queue #${pos} — DocUnlock`;
      }

      // Never leave the queue page until the 2-second minimum has elapsed
      if (!minQueueTimeExpired) return;

      if (data.status === "queued") {
        setState("queued");
      } else if (data.status === "processing") {
        setState("processing");
        document.title = "⚙️ Processing — DocUnlock";
      } else if (data.status === "done") {
        onDone(data.output_filename);
      } else if (data.status === "error") {
        onError(data.error);
      }
    } catch (e) {
      // transient network error, keep polling
    }
  }

  // Request notification permission early
  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission();
  }

  // Initial state: show queued
  setState("queued");
  document.title = "⏳ Queued — DocUnlock";

  poll();
  pollTimer = setInterval(poll, 2000);
})();
