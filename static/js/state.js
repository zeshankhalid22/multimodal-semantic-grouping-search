"use strict";

// ---------------------------------------------------------------------------
// Constants — change these to reconfigure the app without touching logic
// ---------------------------------------------------------------------------
const BASE_URL = ""; // same origin, no trailing slash
const PAGE_SIZE = 48; // gallery products per page
const COMPARE_LIMIT = 5; // similar products per compare page

// ---------------------------------------------------------------------------
// Shared state — single source of truth across all modules
// ---------------------------------------------------------------------------
const state = {
  // gallery
  categories: [],
  activeCategory: null,
  galleryPage: 1,
  galleryTotal: 0, // true row count returned by the API
  searchQuery: "", // title search

  // detail
  currentProduct: null,

  // compare
  comparePage: 1,
  compareFetched: 0, // total DB rows fetched (used to decide if next page exists)
};

// ---------------------------------------------------------------------------
// DOM helper
// ---------------------------------------------------------------------------
const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

/**
 * GET `url` and return parsed JSON.
 * Extracts FastAPI's `detail` field from error responses for clean messages.
 * @param {string} url
 * @returns {Promise<any>}
 */
async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch (_) {
      /* non-JSON error body */
    }
    throw new Error(`[${res.status}] ${detail}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Toast notification
// ---------------------------------------------------------------------------
let _toastTimer = null;

/**
 * Show a brief toast message at the bottom-right of the screen.
 * @param {string}          msg
 * @param {"info"|"error"}  [type="info"]
 */
function showToast(msg, type = "info") {
  const el = $("toast");
  el.textContent = msg;
  el.classList.remove("toast--visible", "toast--error");
  if (type === "error") el.classList.add("toast--error");
  void el.offsetHeight; // force reflow so transition re-fires on rapid calls
  el.classList.add("toast--visible");

  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove("toast--visible"), 3200);
}

// ---------------------------------------------------------------------------
// Image helpers
// ---------------------------------------------------------------------------

/**
 * Inline SVG used as a placeholder when an image fails to load.
 * @returns {string} data URI
 */
function placeholderSvg() {
  return (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' " +
    "width='80' height='80' viewBox='0 0 24 24'%3E" +
    "%3Crect width='24' height='24' fill='%23f3f4f6'/%3E" +
    "%3Cpath d='M4 5h16v14H4z' fill='%23e5e7eb'/%3E%3C/svg%3E"
  );
}

/**
 * Resolve an `image_path` value from the DB into a browser-fetchable URL.
 * FastAPI mounts all product images under /images/ via StaticFiles.
 * @param {string} imagePath
 * @returns {string}
 */
function imageUrl(imagePath) {
  if (!imagePath) return placeholderSvg();
  return `${BASE_URL}/images/${imagePath.replace(/^\.\/|^\//, "")}`;
}

// ---------------------------------------------------------------------------
// Security
// ---------------------------------------------------------------------------

/**
 * Escape a string for safe injection into innerHTML.
 * @param {any} str
 * @returns {string}
 */
function esc(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ---------------------------------------------------------------------------
// IntersectionObserver — lazy image loading
// ---------------------------------------------------------------------------

/**
 * Shared observer instance.
 * Images should set `data-src` instead of `src` and call `observeLazy(img)`
 * after inserting into the DOM. The observer swaps in the real src once the
 * image is within 200px of the viewport, then adds `.loaded` for the CSS
 * fade-in transition.
 */
const _imgObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;

      const img = entry.target;
      const src = img.dataset.src;
      if (!src) return;

      img.src = src;
      img.addEventListener("load", () => img.classList.add("loaded"), {
        once: true,
      });
      img.addEventListener(
        "error",
        () => {
          img.src = placeholderSvg();
          img.classList.add("loaded");
        },
        { once: true },
      );

      _imgObserver.unobserve(img);
    });
  },
  { rootMargin: "200px 0px" },
);

/**
 * Register an image element for lazy loading.
 * Must be called after the element is attached to the DOM.
 * @param {HTMLImageElement} img
 */
function observeLazy(img) {
  _imgObserver.observe(img);
}
