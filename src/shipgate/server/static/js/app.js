/* Report UI helpers beyond declarative HTMX attributes. */

function initFindingRows(root = document) {
  root.querySelectorAll(".finding-summary").forEach((row) => {
    if (row.dataset.bound === "1") {
      return;
    }
    row.dataset.bound = "1";

    const toggle = () => {
      const group = row.closest(".finding-group");
      if (!group) {
        return;
      }
      const opening = !row.classList.contains("finding-expanded");
      const detail = group.querySelector(".finding-detail");
      const message = row.querySelector(".finding-message");
      if (detail) {
        detail.classList.toggle("hidden", !opening);
      } else if (message) {
        message.classList.toggle("line-clamp-2", !opening);
      }
      row.setAttribute("aria-expanded", opening ? "true" : "false");
      row.classList.toggle("finding-expanded", opening);
    };

    row.addEventListener("click", toggle);
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        toggle();
      }
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initFindingRows();
});

document.body.addEventListener("htmx:afterSwap", (event) => {
  const el = event.detail.elt;
  if (!(el instanceof HTMLElement)) {
    return;
  }
  if (el.dataset.runComplete === "1" && el.dataset.runId) {
    window.location.replace(`/?run_id=${encodeURIComponent(el.dataset.runId)}`);
  }
  initFindingRows(el);
});
