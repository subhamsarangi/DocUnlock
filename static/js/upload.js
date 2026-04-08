(function () {
  const dropZone = document.getElementById("dropZone");
  const fileInput = document.getElementById("fileInput");
  const browseBtn = document.getElementById("browseBtn");
  const filePreview = document.getElementById("filePreview");
  const fileName = document.getElementById("fileName");
  const removeFile = document.getElementById("removeFile");
  const passwordInput = document.getElementById("passwordInput");
  const togglePass = document.getElementById("togglePass");
  const submitBtn = document.getElementById("submitBtn");
  const errorMsg = document.getElementById("errorMsg");

  let selectedFile = null;

  function beforeUnloadHandler(e) {
    e.preventDefault();
    e.returnValue = "";
  }

  function enableLeaveConfirmation() {
    window.addEventListener("beforeunload", beforeUnloadHandler);
  }

  function disableLeaveConfirmation() {
    window.removeEventListener("beforeunload", beforeUnloadHandler);
  }

  function setFile(file) {
    if (!file) return;
    if (file.type && file.type !== "application/pdf") {
      showError("Only PDF files are accepted.");
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      showError("File size must be less than 50 MB.");
      return;
    }
    selectedFile = file;
    fileName.textContent = file.name;
    filePreview.classList.remove("d-none");
    dropZone.querySelector(".drop-zone__inner").classList.add("d-none");
    updateSubmit();
    hideError();
    enableLeaveConfirmation();
  }

  function clearFile() {
    selectedFile = null;
    fileInput.value = "";
    filePreview.classList.add("d-none");
    dropZone.querySelector(".drop-zone__inner").classList.remove("d-none");
    updateSubmit();
    disableLeaveConfirmation();
  }

  const MAX_PASSWORD_LENGTH = 128;

  function updateSubmit() {
    const password = passwordInput.value.trim();
    const validPassword =
      password.length > 0 && password.length <= MAX_PASSWORD_LENGTH;
    submitBtn.disabled = !(selectedFile && validPassword);
  }

  let errorTimeout = null;

  function showError(msg) {
    if (errorTimeout) {
      clearTimeout(errorTimeout);
    }
    errorMsg.textContent = msg;
    errorMsg.classList.remove("d-none");
    errorTimeout = setTimeout(hideError, 5000);
  }

  function hideError() {
    if (errorTimeout) {
      clearTimeout(errorTimeout);
      errorTimeout = null;
    }
    errorMsg.classList.add("d-none");
    errorMsg.textContent = "";
  }

  browseBtn.addEventListener("click", () => fileInput.click());
  dropZone.addEventListener("click", (e) => {
    if (e.target === browseBtn || e.target === removeFile) return;
    if (!selectedFile) fileInput.click();
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files[0]) setFile(fileInput.files[0]);
  });

  removeFile.addEventListener("click", (e) => {
    e.stopPropagation();
    clearFile();
  });

  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("drag-over");
  });
  dropZone.addEventListener("dragleave", () =>
    dropZone.classList.remove("drag-over"),
  );
  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");

    // Check for directories
    let hasDirectory = false;
    for (let item of e.dataTransfer.items) {
      if (item.kind === "file") {
        const entry = item.webkitGetAsEntry();
        if (entry && entry.isDirectory) {
          hasDirectory = true;
          break;
        }
      }
    }

    if (hasDirectory) {
      showError("Folders not accepted. Please select individual PDF files.");
      return;
    }

    const file = e.dataTransfer.files[0];
    if (file) setFile(file);
  });

  passwordInput.addEventListener("input", updateSubmit);

  togglePass.addEventListener("click", () => {
    passwordInput.type =
      passwordInput.type === "password" ? "text" : "password";
    togglePass.textContent = passwordInput.type === "password" ? "👁" : "🙈";
  });

  submitBtn.addEventListener("click", async () => {
    if (!selectedFile || !passwordInput.value.trim()) return;

    submitBtn.disabled = true;
    submitBtn.querySelector(".btn-submit__text").textContent = "Uploading…";
    submitBtn.querySelector(".btn-submit__spinner").classList.remove("d-none");
    hideError();

    const password = passwordInput.value.trim();
    if (password.length === 0) {
      showError("Please enter the PDF password.");
      submitBtn.disabled = false;
      submitBtn.querySelector(".btn-submit__text").textContent = "Unlock PDF";
      submitBtn.querySelector(".btn-submit__spinner").classList.add("d-none");
      return;
    }
    if (password.length > MAX_PASSWORD_LENGTH) {
      showError(`Password must be ${MAX_PASSWORD_LENGTH} characters or fewer.`);
      submitBtn.disabled = false;
      submitBtn.querySelector(".btn-submit__text").textContent = "Unlock PDF";
      submitBtn.querySelector(".btn-submit__spinner").classList.add("d-none");
      return;
    }
    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append("password", password);

    try {
      const res = await fetch("/upload", { method: "POST", body: formData });
      const data = await res.json();

      if (!res.ok) {
        showError(data.detail || "Upload failed. Please try again.");
        submitBtn.disabled = false;
        submitBtn.querySelector(".btn-submit__text").textContent = "Unlock PDF";
        submitBtn.querySelector(".btn-submit__spinner").classList.add("d-none");
        return;
      }

      disableLeaveConfirmation();
      window.location.href = "/job/" + data.job_id;
    } catch (err) {
      showError("Network error. Please check your connection and try again.");
      submitBtn.disabled = false;
      submitBtn.querySelector(".btn-submit__text").textContent = "Unlock PDF";
      submitBtn.querySelector(".btn-submit__spinner").classList.add("d-none");
    }
  });
})();
