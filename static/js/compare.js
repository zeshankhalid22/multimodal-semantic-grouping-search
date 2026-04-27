"use strict";

// ---------------------------------------------------------------------------
// Compare — HNSW similarity search results rendered as a dynamic table
// ---------------------------------------------------------------------------

/**
 * Reset all compare UI state. Called whenever a new product is opened so the
 * previous comparison does not bleed through.
 */
function resetCompareSection() {
  state.comparePage    = 1;
  state.compareFetched = 0;

  $("compare-section").classList.add("hidden");
  $("compare-loading").classList.add("hidden");
  $("compare-table").classList.add("hidden");
  $("compare-error").classList.add("hidden");
  $("compare-page-controls").classList.add("hidden");
  $("compare-thead").innerHTML  = "";
  $("compare-tbody").innerHTML  = "";
  $("compare-error").textContent = "";
  $("bc-sep2").classList.add("hidden");
  $("bc-compare").classList.add("hidden");
}

/**
 * Kick off a compare search for the current product at the given page.
 * Generates a fused embedding server-side, runs HNSW, and renders the table.
 *
 * @param {number} [page=1]
 */
async function runCompare(page = 1) {
  const product = state.currentProduct;
  if (!product) return;

  state.comparePage = page;

  // Show section + spinner, hide stale content
  $("compare-section").classList.remove("hidden");
  $("compare-loading").classList.remove("hidden");
  $("compare-table").classList.add("hidden");
  $("compare-error").classList.add("hidden");
  $("compare-page-controls").classList.add("hidden");

  $("compare-section").scrollIntoView({ behavior: "smooth", block: "start" });

  try {
    const data = await fetchJSON(
      `${BASE_URL}/product/${product.id}/compare` +
        `?limit=${COMPARE_LIMIT}&page=${page}`,
    );

    // total_fetched tells us how many DB rows came back at the DB level
    // (= page * limit at most). Used to decide whether a next page exists.
    state.compareFetched = data.total_fetched;
    renderCompareTable(data.anchor, data.similar, data.page);
  } catch (err) {
    $("compare-loading").classList.add("hidden");
    $("compare-error").textContent = "Search failed: " + err.message;
    $("compare-error").classList.remove("hidden");
    showToast("Compare failed: " + err.message, "error");
  }
}

// ---------------------------------------------------------------------------
// Table rendering
// ---------------------------------------------------------------------------

/**
 * Build and display the dynamic comparison table.
 *
 * Columns : Anchor + up to COMPARE_LIMIT similar products
 * Fixed rows : thumbnail image, Title, Platform, Price, Similarity score
 * Dynamic rows : every unique attribute key found across ALL products
 *
 * The left label column is CSS-sticky (`.col-label`) so it stays visible
 * while the user scrolls the table horizontally.
 * Missing attribute values render as "—".
 *
 * @param {object}   anchor        - full product object for the query item
 * @param {object[]} similar       - ranked similar products for this page
 * @param {number}   page          - current page number (1-based)
 */
function renderCompareTable(anchor, similar, page) {
  $("compare-loading").classList.add("hidden");

  if (!similar || similar.length === 0) {
    $("compare-error").textContent =
      "No similar products found in this category.";
    $("compare-error").classList.remove("hidden");
    return;
  }

  const allProducts = [anchor, ...similar];

  // ── Collect every unique attribute key across all products ──────────────
  const attrKeySet = new Set();
  allProducts.forEach((p) =>
    Object.keys(p?.attributes ?? {}).forEach((k) => attrKeySet.add(k)),
  );
  const attrKeys = [...attrKeySet].sort();

  _buildThead(allProducts, anchor);
  _buildTbody(allProducts, anchor, attrKeys);

  $("compare-table").classList.remove("hidden");
  _renderPageControls(page);

  // Reveal the "Compare" breadcrumb segment
  $("bc-sep2").classList.remove("hidden");
  $("bc-compare").classList.remove("hidden");
}

// ---------------------------------------------------------------------------
// Private — thead
// ---------------------------------------------------------------------------

function _buildThead(allProducts, anchor) {
  const headRow = document.createElement("tr");

  // Sticky label column header
  const thLabel = document.createElement("th");
  thLabel.className =
    "col-label px-4 py-3 text-left text-2xs font-semibold text-content-faint uppercase tracking-widest w-36";
  thLabel.textContent = "Attribute";
  headRow.appendChild(thLabel);

  allProducts.forEach((p, i) => {
    const isAnchor = i === 0;
    const th       = document.createElement("th");
    th.className   = "px-3 py-3 text-center min-w-40 align-bottom";

    // Badge — "Anchor" pill or similarity percentage
    const badge = document.createElement("span");
    if (isAnchor) {
      badge.className =
        "inline-flex items-center px-2 py-0.5 rounded-full bg-primary-100 " +
        "text-primary-700 text-2xs font-bold uppercase tracking-wide mb-2";
      badge.textContent = "Anchor";
    } else {
      badge.className   = "sim-badge mb-2";
      badge.textContent = `${((p.similarity ?? 0) * 100).toFixed(1)}% match`;
    }

    // Thumbnail — lazy-loaded via the shared IntersectionObserver
    const img       = document.createElement("img");
    img.dataset.src = imageUrl(p.image_path);
    img.alt         = p.title ?? "";
    img.decoding    = "async";
    img.className   =
      "h-24 w-24 object-contain rounded-panel bg-surface-subtle " +
      "border border-surface-border p-1 mx-auto block";
    img.addEventListener(
      "error",
      () => { img.src = placeholderSvg(); },
      { once: true },
    );

    const wrapper = document.createElement("div");
    wrapper.className = "flex flex-col items-center gap-2";
    wrapper.appendChild(badge);
    wrapper.appendChild(img);
    th.appendChild(wrapper);
    headRow.appendChild(th);

    // Observe after the row is appended to the DOM below
    requestAnimationFrame(() => observeLazy(img));
  });

  $("compare-thead").innerHTML = "";
  $("compare-thead").appendChild(headRow);
}

// ---------------------------------------------------------------------------
// Private — tbody
// ---------------------------------------------------------------------------

function _buildTbody(allProducts, anchor, attrKeys) {
  $("compare-tbody").innerHTML = "";

  // ── Fixed rows ─────────────────────────────────────────────────────────
  _appendRow("Title", allProducts, (p) =>
    `<span class="line-clamp-3 text-xs font-medium text-content">${esc(p.title)}</span>`,
  );

  _appendRow("Platform", allProducts, (p) =>
    `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs
                  bg-primary-50 text-primary-700 font-medium">
       ${esc(p.platform ?? "—")}
     </span>`,
  );

  _appendRow("Price", allProducts, (p) =>
    p.price
      ? `<span class="font-bold text-primary-600">$${esc(p.price)}</span>`
      : `<span class="text-content-faint">—</span>`,
  );

  _appendRow("Similarity", allProducts, (p) => {
    if (p === anchor) return `<span class="text-content-faint text-xs">—</span>`;
    const pct = ((p.similarity ?? 0) * 100).toFixed(1);
    return `
      <div class="flex items-center justify-center gap-1.5">
        <div class="w-16 bg-surface-border rounded-full h-1.5 shrink-0">
          <div class="h-1.5 rounded-full bg-primary-500" style="width:${pct}%"></div>
        </div>
        <span class="text-xs font-semibold text-primary-600 tabular-nums">${pct}%</span>
      </div>`;
  });

  // ── Dynamic attribute rows ─────────────────────────────────────────────
  if (attrKeys.length > 0) {
    // Section divider spanning all columns
    const dividerTr = document.createElement("tr");
    const dividerTd = document.createElement("td");
    dividerTd.colSpan = allProducts.length + 1;
    dividerTd.className = "px-4 py-2 bg-surface-subtle";
    dividerTd.innerHTML =
      `<span class="text-2xs font-bold text-content-faint uppercase tracking-widest">
         Attributes
       </span>`;
    dividerTr.appendChild(dividerTd);
    $("compare-tbody").appendChild(dividerTr);

    attrKeys.forEach((key) => {
      _appendRow(key, allProducts, (p) => {
        const val = (p.attributes ?? {})[key];
        return val != null
          ? esc(val)
          : `<span class="text-content-faint">—</span>`;
      });
    });
  }
}

/**
 * Create and append a `<tr>` with a sticky label cell followed by one data
 * cell per product.
 *
 * @param {string}   label      - text shown in the sticky left cell
 * @param {object[]} products   - array of product objects (anchor first)
 * @param {function} cellFn     - (product) => HTML string for each data cell
 */
function _appendRow(label, products, cellFn) {
  const tr = document.createElement("tr");

  const tdLabel = document.createElement("td");
  tdLabel.className =
    "col-label px-4 py-3 text-2xs font-semibold text-content-faint uppercase tracking-widest";
  tdLabel.textContent = label;
  tr.appendChild(tdLabel);

  products.forEach((p) => {
    const td = document.createElement("td");
    td.className =
      "px-3 py-3 text-sm text-content-secondary text-center align-top";
    td.innerHTML = cellFn(p);
    tr.appendChild(td);
  });

  $("compare-tbody").appendChild(tr);
}

// ---------------------------------------------------------------------------
// Private — page controls
// ---------------------------------------------------------------------------

/**
 * Show / update the Prev / Next buttons for compare paging.
 *
 * hasPrev : page > 1
 * hasNext : the DB returned enough rows to fill at least one more page
 *           (total_fetched === page * COMPARE_LIMIT means the DB hit its limit,
 *            so another page very likely exists)
 *
 * @param {number} page
 */
function _renderPageControls(page) {
  const hasPrev = page > 1;
  const hasNext = state.compareFetched >= page * COMPARE_LIMIT;

  if (!hasPrev && !hasNext) {
    $("compare-page-controls").classList.add("hidden");
    return;
  }

  $("compare-page-controls").classList.remove("hidden");
  $("compare-page-label").textContent = `Page ${page}`;
  $("btn-compare-prev").disabled = !hasPrev;
  $("btn-compare-next").disabled = !hasNext;
}

// ---------------------------------------------------------------------------
// Event listeners
// ---------------------------------------------------------------------------

$("btn-compare").addEventListener("click", () => runCompare(1));

$("btn-compare-prev").addEventListener("click", () => {
  if (state.comparePage > 1) runCompare(state.comparePage - 1);
});

$("btn-compare-next").addEventListener("click", () => {
  runCompare(state.comparePage + 1);
});
