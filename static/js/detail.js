"use strict";

// ---------------------------------------------------------------------------
// Product Detail — opens on card click, fetches full data lazily
// ---------------------------------------------------------------------------

/**
 * Entry point called by gallery.js when a product card is clicked.
 * Switches to the detail view, shows a skeleton, fetches full product data,
 * then renders it. Description, attributes, platform, and category_group are
 * NOT included in the gallery payload — they arrive here for the first time.
 *
 * @param {number} id - product primary key
 */
async function openProduct(id, fromPopstate = false) {
  // temporarily mock state.currentProduct so updateUrl syncs the right ID
  // before the full product fetch completes
  state.currentProduct = { id: String(id) };

  if (!fromPopstate) {
    const url = new URL(window.location.href);
    url.searchParams.set("product", String(id));
    window.history.pushState({}, "", url.toString());
  }

  showView("detail");
  resetCompareSection();
  renderDetailSkeleton();
  window.scrollTo({ top: 0, behavior: "smooth" });

  try {
    const product = await fetchJSON(`${BASE_URL}/product/${id}`);
    state.currentProduct = product;
    renderDetail(product);
    updateBreadcrumb("detail");
  } catch (err) {
    showToast("Failed to load product: " + err.message, "error");
    state.currentProduct = null;
    if (!fromPopstate) {
      updateUrl(true);
    }
    showView("gallery");
  }
}

// ---------------------------------------------------------------------------
// Skeleton — shown while the lazy fetch is in-flight
// ---------------------------------------------------------------------------

function renderDetailSkeleton() {
  $("detail-image").src = "";
  $("detail-platform").textContent = "";
  $("detail-category").textContent = "";
  $("detail-title").innerHTML =
    `<span class="skeleton-rect inline-block h-5 w-3/4 rounded">&nbsp;</span>`;
  $("detail-price").innerHTML =
    `<span class="skeleton-rect inline-block h-6 w-1/4 rounded">&nbsp;</span>`;
  $("detail-description").textContent = "";
  $("detail-attributes").innerHTML = "";
  $("detail-attributes-section").classList.add("hidden");
  $("btn-expand-desc").classList.add("hidden");
}

// ---------------------------------------------------------------------------
// Full render
// ---------------------------------------------------------------------------

function renderDetail(p) {
  // Hero image — loaded directly (not lazy) because it is immediately visible
  $("detail-image").src = imageUrl(p.image_path);
  $("detail-image").alt = p.title ?? "";

  // Platform / category badges
  $("detail-platform").textContent = p.platform ?? "";
  $("detail-category").textContent = p.category_group ?? "";

  // Title
  $("detail-title").textContent = p.title ?? "Untitled";

  // Price
  const priceEl = $("detail-price");
  if (p.price) {
    priceEl.textContent = `$${p.price}`;
    priceEl.classList.remove("hidden");
  } else {
    priceEl.textContent = "";
    priceEl.classList.add("hidden");
  }

  // Description with expand / collapse toggle
  _renderDescription(p.description ?? "");

  // Attributes list
  _renderAttributes(p.attributes ?? {});
}

function _renderDescription(desc) {
  const el = $("detail-description");
  const btn = $("btn-expand-desc");

  el.textContent = desc;

  if (desc.length > 300) {
    el.classList.add("line-clamp-5");
    btn.textContent = "Read more";
    btn.classList.remove("hidden");
    // Replace onclick to avoid accumulating listeners across product loads
    btn.onclick = () => {
      const clamped = el.classList.toggle("line-clamp-5");
      btn.textContent = clamped ? "Read more" : "Read less";
    };
  } else {
    el.classList.remove("line-clamp-5");
    btn.classList.add("hidden");
    btn.onclick = null;
  }
}

function _renderAttributes(attrs) {
  const section = $("detail-attributes-section");
  const list = $("detail-attributes");
  const keys = Object.keys(attrs);

  if (keys.length === 0) {
    section.classList.add("hidden");
    return;
  }

  section.classList.remove("hidden");
  list.innerHTML = keys
    .map(
      (k) => `
      <li class="flex gap-2">
        <span class="font-medium text-content-secondary min-w-max">${esc(k)}:</span>
        <span class="text-content-muted">${esc(attrs[k])}</span>
      </li>`,
    )
    .join("");
}

// ---------------------------------------------------------------------------
// Navigation listeners
// ---------------------------------------------------------------------------

$("btn-back-gallery").addEventListener("click", () => {
  state.currentProduct = null;

  const url = new URL(window.location.href);
  url.searchParams.delete("product");
  window.history.pushState({}, "", url.toString());

  showView("gallery");
  window.scrollTo({ top: 0, behavior: "smooth" });
});

window.addEventListener("popstate", () => {
  const params = new URLSearchParams(window.location.search);
  const productId = params.get("product");
  if (productId) {
    openProduct(productId, true);
  } else if ($("view-detail").classList.contains("active")) {
    state.currentProduct = null;
    showView("gallery");
  }
});
