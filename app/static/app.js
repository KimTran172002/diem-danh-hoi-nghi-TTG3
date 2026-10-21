document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll('form[enctype="multipart/form-data"]').forEach(form => {
    form.addEventListener("submit", () => {
      const button = form.querySelector('button[type="submit"]');
      if (button) {
        button.dataset.originalText = button.textContent.trim();
        button.textContent = "Đang xử lý...";
        button.disabled = true;
      }
    });
  });
});
